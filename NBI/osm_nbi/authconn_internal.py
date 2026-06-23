# -*- coding: utf-8 -*-

# Copyright 2018 Telefonica S.A.
# Copyright 2018 ALTRAN Innovación S.L.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact: esousa@whitestack.com or glavado@whitestack.com
##

"""
AuthconnInternal implements implements the connector for
OSM Internal Authentication Backend and leverages the RBAC model
"""

__author__ = (
    "Pedro de la Cruz Ramos <pdelacruzramos@altran.com>, "
    "Alfonso Tierno <alfonso.tiernosepulveda@telefoncia.com"
)
__date__ = "$06-jun-2019 11:16:08$"

import logging
import re
import secrets
from osm_nbi.authconn import (
    Authconn,
    AuthException,
    AuthconnConflictException,
)  # , AuthconnOperationException
from osm_common.dbbase import DbException
from osm_nbi.base_topic import BaseTopic
from osm_nbi.utils import cef_event, cef_event_builder
from osm_nbi.password_utils import (
    hash_password,
    verify_password,
    verify_password_sha256,
)
from osm_nbi.validation import is_valid_uuid, email_schema
from time import time, sleep
from http import HTTPStatus
from uuid import uuid4
from copy import deepcopy
import smtplib
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class AuthconnInternal(Authconn):
    token_time_window = 2  # seconds
    token_delay = 1  # seconds to wait upon second request within time window

    users_collection = "users"
    roles_collection = "roles"
    projects_collection = "projects"
    tokens_collection = "tokens"

    def __init__(self, config, db, role_permissions):
        Authconn.__init__(self, config, db, role_permissions)
        self.logger = logging.getLogger("nbi.authenticator.internal")

        self.db = db
        # self.msg = msg
        # self.token_cache = token_cache

        # To be Confirmed
        self.sess = None
        self.cef_logger = cef_event_builder(config)

    def validate_token(self, token):
        """
        Check if the token is valid.

        :param token: token to validate
        :return: dictionary with information associated with the token:
            "_id": token id
            "project_id": project id
            "project_name": project name
            "user_id": user id
            "username": user name
            "roles": list with dict containing {name, id}
            "expires": expiration date
        If the token is not valid an exception is raised.
        """

        try:
            if not token:
                raise AuthException(
                    "Needed a token or Authorization HTTP header",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )

            now = time()

            # get from database if not in cache
            # if not token_info:
            token_info = self.db.get_one(self.tokens_collection, {"_id": token})
            if token_info["expires"] < now:
                raise AuthException(
                    "Expired Token or Authorization HTTP header",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )

            return token_info

        except DbException as e:
            if e.http_code == HTTPStatus.NOT_FOUND:
                raise AuthException(
                    "Invalid Token or Authorization HTTP header",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )
            else:
                raise
        except AuthException:
            raise
        except Exception:
            self.logger.exception(
                "Error during token validation using internal backend"
            )
            raise AuthException(
                "Error during token validation using internal backend",
                http_code=HTTPStatus.UNAUTHORIZED,
            )

    def revoke_token(self, token):
        """
        Invalidate a token.

        :param token: token to be revoked
        """
        try:
            # self.token_cache.pop(token, None)
            self.db.del_one(self.tokens_collection, {"_id": token})
            return True
        except DbException as e:
            if e.http_code == HTTPStatus.NOT_FOUND:
                raise AuthException(
                    "Token '{}' not found".format(token), http_code=HTTPStatus.NOT_FOUND
                )
            else:
                # raise
                exmsg = "Error during token revocation using internal backend"
                self.logger.exception(exmsg)
                raise AuthException(exmsg, http_code=HTTPStatus.UNAUTHORIZED)

    def validate_user(self, user, password, otp=None):
        """
        Validate username and password via appropriate backend.
        :param user: username of the user.
        :param password: password to be validated.
        """
        user_rows = self.db.get_list(
            self.users_collection, {BaseTopic.id_field("users", user): user}
        )
        now = time()
        user_content = None
        if user:
            user_rows = self.db.get_list(
                self.users_collection,
                {BaseTopic.id_field(self.users_collection, user): user},
            )
            if user_rows:
                user_content = user_rows[0]
                # Updating user_status for every system_admin id role login
                mapped_roles = user_content.get("project_role_mappings")
                for role in mapped_roles:
                    role_id = role.get("role")
                    role_assigned = self.db.get_one(
                        self.roles_collection,
                        {BaseTopic.id_field(self.roles_collection, role_id): role_id},
                    )

                    if role_assigned.get("permissions")["admin"]:
                        if role_assigned.get("permissions")["default"]:
                            if self.config.get("user_management"):
                                filt = {}
                                users = self.db.get_list(self.users_collection, filt)
                                for user_info in users:
                                    if not user_info.get("username") == "admin":
                                        if not user_info.get("_admin").get(
                                            "account_expire_time"
                                        ):
                                            expire = now + 86400 * self.config.get(
                                                "account_expire_days"
                                            )
                                            self.db.set_one(
                                                self.users_collection,
                                                {"_id": user_info["_id"]},
                                                {"_admin.account_expire_time": expire},
                                            )
                                        else:
                                            if now > user_info.get("_admin").get(
                                                "account_expire_time"
                                            ):
                                                self.db.set_one(
                                                    self.users_collection,
                                                    {"_id": user_info["_id"]},
                                                    {"_admin.user_status": "expired"},
                                                )
                                break

                # To add "admin" user_status key while upgrading osm setup with feature enabled
                if user_content.get("username") == "admin":
                    if self.config.get("user_management"):
                        self.db.set_one(
                            self.users_collection,
                            {"_id": user_content["_id"]},
                            {"_admin.user_status": "always-active"},
                        )

                if not user_content.get("username") == "admin":
                    if self.config.get("user_management"):
                        if not user_content.get("_admin").get("account_expire_time"):
                            account_expire_time = now + 86400 * self.config.get(
                                "account_expire_days"
                            )
                            self.db.set_one(
                                self.users_collection,
                                {"_id": user_content["_id"]},
                                {"_admin.account_expire_time": account_expire_time},
                            )
                        else:
                            account_expire_time = user_content.get("_admin").get(
                                "account_expire_time"
                            )

                        if now > account_expire_time:
                            self.db.set_one(
                                self.users_collection,
                                {"_id": user_content["_id"]},
                                {"_admin.user_status": "expired"},
                            )
                            raise AuthException(
                                "Account expired", http_code=HTTPStatus.UNAUTHORIZED
                            )

                        if user_content.get("_admin").get("user_status") == "locked":
                            raise AuthException(
                                "Failed to login as the account is locked due to MANY FAILED ATTEMPTS"
                            )
                        elif user_content.get("_admin").get("user_status") == "expired":
                            raise AuthException(
                                "Failed to login as the account is expired"
                            )
                if otp:
                    return user_content
                correct_pwd = False
                if user_content.get("hashing_function") == "bcrypt":
                    correct_pwd = verify_password(
                        password=password, hashed_password_hex=user_content["password"]
                    )
                else:
                    correct_pwd = verify_password_sha256(
                        password=password,
                        hashed_password_hex=user_content["password"],
                        salt=user_content["_admin"]["salt"],
                    )
                if not correct_pwd:
                    count = 1
                    if user_content.get("_admin").get("retry_count") >= 0:
                        count += user_content.get("_admin").get("retry_count")
                        self.db.set_one(
                            self.users_collection,
                            {"_id": user_content["_id"]},
                            {"_admin.retry_count": count},
                        )
                        self.logger.debug(
                            "Failed Authentications count: {}".format(count)
                        )

                    if user_content.get("username") == "admin":
                        user_content = None
                    else:
                        if not self.config.get("user_management"):
                            user_content = None
                        else:
                            if (
                                user_content.get("_admin").get("retry_count")
                                >= self.config["max_pwd_attempt"] - 1
                            ):
                                self.db.set_one(
                                    self.users_collection,
                                    {"_id": user_content["_id"]},
                                    {"_admin.user_status": "locked"},
                                )
                                raise AuthException(
                                    "Failed to login as the account is locked due to MANY FAILED ATTEMPTS"
                                )
                            else:
                                user_content = None
                elif correct_pwd and user_content.get("hashing_function") != "bcrypt":
                    # Update the database using a more secure hashing function to store the password
                    user_content["password"] = hash_password(
                        password=password,
                        rounds=self.config.get("password_rounds", 12),
                    )
                    user_content["hashing_function"] = "bcrypt"
                    user_content["_admin"]["password_history_sha256"] = user_content[
                        "_admin"
                    ]["password_history"]
                    user_content["_admin"]["password_history"] = [
                        user_content["password"]
                    ]
                    del user_content["_admin"]["salt"]

                    uid = user_content["_id"]
                    idf = BaseTopic.id_field("users", uid)
                    self.db.set_one(self.users_collection, {idf: uid}, user_content)
        return user_content

    def authenticate(self, credentials, token_info=None):
        """
        Authenticate a user using username/password or previous token_info plus project; its creates a new token

        :param credentials: dictionary that contains:
            username: name, id or None
            password: password or None
            project_id: name, id, or None. If None first found project will be used to get an scope token
            other items are allowed and ignored
        :param token_info: previous token_info to obtain authorization
        :return: the scoped token info or raises an exception. The token is a dictionary with:
            _id:  token string id,
            username: username,
            project_id: scoped_token project_id,
            project_name: scoped_token project_name,
            expires: epoch time when it expires,
        """

        now = time()
        user_content = None
        user = credentials.get("username")
        password = credentials.get("password")
        project = credentials.get("project_id")
        otp_validation = credentials.get("otp")

        # Try using username/password
        if otp_validation:
            user_content = self.validate_user(user, password=None, otp=otp_validation)
        elif user:
            user_content = self.validate_user(user, password)
            if not user_content:
                cef_event(
                    self.cef_logger,
                    {
                        "name": "User login",
                        "sourceUserName": user,
                        "message": "Invalid username/password Project={} Outcome=Failure".format(
                            project
                        ),
                        "severity": "3",
                    },
                )
                self.logger.exception("{}".format(self.cef_logger))
                raise AuthException(
                    "Invalid username/password", http_code=HTTPStatus.UNAUTHORIZED
                )
            if not user_content.get("_admin", None):
                raise AuthException(
                    "No default project for this user.",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )
        elif token_info:
            user_rows = self.db.get_list(
                self.users_collection, {"username": token_info["username"]}
            )
            if user_rows:
                user_content = user_rows[0]
            else:
                raise AuthException("Invalid token", http_code=HTTPStatus.UNAUTHORIZED)
        else:
            raise AuthException(
                "Provide credentials: username/password or Authorization Bearer token",
                http_code=HTTPStatus.UNAUTHORIZED,
            )
        # Delay upon second request within time window
        if (
            now - user_content["_admin"].get("last_token_time", 0)
            < self.token_time_window
        ):
            sleep(self.token_delay)
        # user_content["_admin"]["last_token_time"] = now
        # self.db.replace("users", user_content["_id"], user_content)   # might cause race conditions
        user_data = {
            "_admin.last_token_time": now,
            "_admin.retry_count": 0,
        }
        self.db.set_one(
            self.users_collection,
            {"_id": user_content["_id"]},
            user_data,
        )

        # Generate a secure random 32 byte array base64 encoded for use in URLs
        token_id = secrets.token_urlsafe(32)

        # projects = user_content.get("projects", [])
        prm_list = user_content.get("project_role_mappings", [])

        if not project:
            project = prm_list[0]["project"] if prm_list else None
        if not project:
            raise AuthException(
                "can't find a default project for this user",
                http_code=HTTPStatus.UNAUTHORIZED,
            )

        projects = [prm["project"] for prm in prm_list]

        proj = self.db.get_one(
            self.projects_collection, {BaseTopic.id_field("projects", project): project}
        )
        project_name = proj["name"]
        project_id = proj["_id"]
        if project_name not in projects and project_id not in projects:
            raise AuthException(
                "project {} not allowed for this user".format(project),
                http_code=HTTPStatus.UNAUTHORIZED,
            )

        # TODO remove admin, this vill be used by roles RBAC
        if project_name == "admin":
            token_admin = True
        else:
            token_admin = proj.get("admin", False)

        # add token roles
        roles = []
        roles_list = []
        for prm in prm_list:
            if prm["project"] in [project_id, project_name]:
                role = self.db.get_one(
                    self.roles_collection,
                    {BaseTopic.id_field("roles", prm["role"]): prm["role"]},
                )
                rid = role["_id"]
                if rid not in roles:
                    rnm = role["name"]
                    roles.append(rid)
                    roles_list.append({"name": rnm, "id": rid})
        if not roles_list:
            rid = self.db.get_one(self.roles_collection, {"name": "project_admin"})[
                "_id"
            ]
            roles_list = [{"name": "project_admin", "id": rid}]

        login_count = user_content.get("_admin").get("retry_count")
        last_token_time = user_content.get("_admin").get("last_token_time")

        admin_show = False
        user_show = False
        if self.config.get("user_management"):
            for role in roles_list:
                role_id = role.get("id")
                permission = self.db.get_one(
                    self.roles_collection,
                    {BaseTopic.id_field(self.roles_collection, role_id): role_id},
                )
                if permission.get("permissions")["admin"]:
                    if permission.get("permissions")["default"]:
                        admin_show = True
                        break
            else:
                user_show = True
        new_token = {
            "issued_at": now,
            "expires": now + 3600,
            "_id": token_id,
            "id": token_id,
            "project_id": proj["_id"],
            "project_name": proj["name"],
            "username": user_content["username"],
            "user_id": user_content["_id"],
            "admin": token_admin,
            "roles": roles_list,
            "login_count": login_count,
            "last_login": last_token_time,
            "admin_show": admin_show,
            "user_show": user_show,
        }

        self.db.create(self.tokens_collection, new_token)
        return deepcopy(new_token)

    def get_role_list(self, filter_q={}):
        """
        Get role list.

        :return: returns the list of roles.
        """
        return self.db.get_list(self.roles_collection, filter_q)

    def create_role(self, role_info):
        """
        Create a role.

        :param role_info: full role info.
        :return: returns the role id.
        :raises AuthconnOperationException: if role creation failed.
        """
        # TODO: Check that role name does not exist ?
        rid = str(uuid4())
        role_info["_id"] = rid
        rid = self.db.create(self.roles_collection, role_info)
        return rid

    def delete_role(self, role_id):
        """
        Delete a role.

        :param role_id: role identifier.
        :raises AuthconnOperationException: if role deletion failed.
        """
        rc = self.db.del_one(self.roles_collection, {"_id": role_id})
        self.db.del_list(self.tokens_collection, {"roles.id": role_id})
        return rc

    def update_role(self, role_info):
        """
        Update a role.

        :param role_info: full role info.
        :return: returns the role name and id.
        :raises AuthconnOperationException: if user creation failed.
        """
        rid = role_info["_id"]
        self.db.set_one(self.roles_collection, {"_id": rid}, role_info)
        return {"_id": rid, "name": role_info["name"]}

    def create_user(self, user_info):
        """
        Create a user.

        :param user_info: full user info.
        :return: returns the username and id of the user.
        """
        BaseTopic.format_on_new(user_info, make_public=False)
        user_info["_admin"]["user_status"] = "active"
        present = time()
        if not user_info["username"] == "admin":
            if self.config.get("user_management"):
                user_info["_admin"]["modified"] = present
                user_info["_admin"]["password_expire_time"] = present
                account_expire_time = present + 86400 * self.config.get(
                    "account_expire_days"
                )
                user_info["_admin"]["account_expire_time"] = account_expire_time

        user_info["_admin"]["retry_count"] = 0
        user_info["_admin"]["last_token_time"] = present
        if "password" in user_info:
            user_info["password"] = hash_password(
                password=user_info["password"],
                rounds=self.config.get("password_rounds", 12),
            )
            user_info["hashing_function"] = "bcrypt"
            user_info["_admin"]["password_history"] = [user_info["password"]]
        # "projects" are not stored any more
        if "projects" in user_info:
            del user_info["projects"]
        self.db.create(self.users_collection, user_info)
        return {"username": user_info["username"], "_id": user_info["_id"]}

    def update_user(self, user_info):
        """
        Change the user name and/or password.

        :param user_info: user info modifications
        """
        uid = user_info["_id"]
        old_pwd = user_info.get("old_password")
        unlock = user_info.get("unlock")
        renew = user_info.get("renew")
        permission_id = user_info.get("system_admin_id")
        now = time()

        user_data = self.db.get_one(
            self.users_collection, {BaseTopic.id_field("users", uid): uid}
        )
        if old_pwd:
            correct_pwd = False
            if user_data.get("hashing_function") == "bcrypt":
                correct_pwd = verify_password(
                    password=old_pwd, hashed_password_hex=user_data["password"]
                )
            else:
                correct_pwd = verify_password_sha256(
                    password=old_pwd,
                    hashed_password_hex=user_data["password"],
                    salt=user_data["salt"],
                )
            if not correct_pwd:
                raise AuthconnConflictException(
                    "Incorrect password", http_code=HTTPStatus.CONFLICT
                )
        # Unlocking the user
        if unlock:
            system_user = None
            unlock_state = False
            if not permission_id:
                raise AuthconnConflictException(
                    "system_admin_id is the required field to unlock the user",
                    http_code=HTTPStatus.CONFLICT,
                )
            else:
                system_user = self.db.get_one(
                    self.users_collection,
                    {
                        BaseTopic.id_field(
                            self.users_collection, permission_id
                        ): permission_id
                    },
                )
                mapped_roles = system_user.get("project_role_mappings")
                for role in mapped_roles:
                    role_id = role.get("role")
                    role_assigned = self.db.get_one(
                        self.roles_collection,
                        {BaseTopic.id_field(self.roles_collection, role_id): role_id},
                    )
                    if role_assigned.get("permissions")["admin"]:
                        if role_assigned.get("permissions")["default"]:
                            user_data["_admin"]["retry_count"] = 0
                            if now > user_data["_admin"]["account_expire_time"]:
                                user_data["_admin"]["user_status"] = "expired"
                            else:
                                user_data["_admin"]["user_status"] = "active"
                            unlock_state = True
                            break
                if not unlock_state:
                    raise AuthconnConflictException(
                        "User '{}' does not have the privilege to unlock the user".format(
                            permission_id
                        ),
                        http_code=HTTPStatus.CONFLICT,
                    )
        # Renewing the user
        if renew:
            system_user = None
            renew_state = False
            if not permission_id:
                raise AuthconnConflictException(
                    "system_admin_id is the required field to renew the user",
                    http_code=HTTPStatus.CONFLICT,
                )
            else:
                system_user = self.db.get_one(
                    self.users_collection,
                    {
                        BaseTopic.id_field(
                            self.users_collection, permission_id
                        ): permission_id
                    },
                )
                mapped_roles = system_user.get("project_role_mappings")
                for role in mapped_roles:
                    role_id = role.get("role")
                    role_assigned = self.db.get_one(
                        self.roles_collection,
                        {BaseTopic.id_field(self.roles_collection, role_id): role_id},
                    )
                    if role_assigned.get("permissions")["admin"]:
                        if role_assigned.get("permissions")["default"]:
                            present = time()
                            account_expire = (
                                present + 86400 * self.config["account_expire_days"]
                            )
                            user_data["_admin"]["modified"] = present
                            user_data["_admin"]["account_expire_time"] = account_expire
                            if (
                                user_data["_admin"]["retry_count"]
                                >= self.config["max_pwd_attempt"]
                            ):
                                user_data["_admin"]["user_status"] = "locked"
                            else:
                                user_data["_admin"]["user_status"] = "active"
                            renew_state = True
                            break
                if not renew_state:
                    raise AuthconnConflictException(
                        "User '{}' does not have the privilege to renew the user".format(
                            permission_id
                        ),
                        http_code=HTTPStatus.CONFLICT,
                    )
        BaseTopic.format_on_edit(user_data, user_info)
        # User Name
        usnm = user_info.get("username")
        email_id = user_info.get("email_id")
        if usnm:
            user_data["username"] = usnm
        if email_id:
            user_data["email_id"] = email_id
        # If password is given and is not already encripted
        pswd = user_info.get("password")
        if pswd and (
            len(pswd) != 64 or not re.match("[a-fA-F0-9]*", pswd)
        ):  # TODO: Improve check?
            cef_event(
                self.cef_logger,
                {
                    "name": "Change Password",
                    "sourceUserName": user_data["username"],
                    "message": "User {} changing Password for user {}, Outcome=Success".format(
                        user_info.get("session_user"), user_data["username"]
                    ),
                    "severity": "2",
                },
            )
            self.logger.info("{}".format(self.cef_logger))
            if "_admin" not in user_data:
                user_data["_admin"] = {}
            if user_data.get("_admin").get("password_history"):
                old_pwds = user_data.get("_admin").get("password_history")
            else:
                old_pwds = []
            for v in old_pwds:
                if verify_password(password=pswd, hashed_password_hex=v):
                    raise AuthconnConflictException(
                        "Password is used before", http_code=HTTPStatus.CONFLICT
                    )

            # Backwards compatibility for SHA256 hashed passwords
            if user_data.get("_admin").get("password_history_sha256"):
                old_pwds_sha256 = user_data.get("_admin").get("password_history_sha256")
            else:
                old_pwds_sha256 = {}
            for k, v in old_pwds_sha256.items():
                if verify_password_sha256(password=pswd, hashed_password_hex=v, salt=k):
                    raise AuthconnConflictException(
                        "Password is used before", http_code=HTTPStatus.CONFLICT
                    )

            # Finally, hash the password to be updated
            user_data["password"] = hash_password(
                password=pswd, rounds=self.config.get("password_rounds", 12)
            )
            user_data["hashing_function"] = "bcrypt"

            if len(old_pwds) >= 3:
                old_pwds.pop(list(old_pwds.keys())[0])
            old_pwds.append([user_data["password"]])
            user_data["_admin"]["password_history"] = old_pwds
            if not user_data["username"] == "admin":
                if self.config.get("user_management"):
                    present = time()
                    if self.config.get("pwd_expire_days"):
                        expire = present + 86400 * self.config.get("pwd_expire_days")
                        user_data["_admin"]["modified"] = present
                        user_data["_admin"]["password_expire_time"] = expire
        # Project-Role Mappings
        # TODO: Check that user_info NEVER includes "project_role_mappings"
        if "project_role_mappings" not in user_data:
            user_data["project_role_mappings"] = []
        for prm in user_info.get("add_project_role_mappings", []):
            user_data["project_role_mappings"].append(prm)
        for prm in user_info.get("remove_project_role_mappings", []):
            for pidf in ["project", "project_name"]:
                for ridf in ["role", "role_name"]:
                    try:
                        user_data["project_role_mappings"].remove(
                            {"role": prm[ridf], "project": prm[pidf]}
                        )
                    except KeyError:
                        pass
                    except ValueError:
                        pass
        idf = BaseTopic.id_field("users", uid)
        self.db.set_one(self.users_collection, {idf: uid}, user_data)
        if user_info.get("remove_project_role_mappings"):
            idf = "user_id" if idf == "_id" else idf
            if not user_data.get("project_role_mappings") or user_info.get(
                "remove_session_project"
            ):
                self.db.del_list(self.tokens_collection, {idf: uid})

    def delete_user(self, user_id):
        """
        Delete user.

        :param user_id: user identifier.
        :raises AuthconnOperationException: if user deletion failed.
        """
        self.db.del_one(self.users_collection, {"_id": user_id})
        self.db.del_list(self.tokens_collection, {"user_id": user_id})
        return True

    def get_user_list(self, filter_q=None):
        """
        Get user list.

        :param filter_q: dictionary to filter user list by:
            name (username is also admitted).  If a user id is equal to the filter name, it is also provided
            other
        :return: returns a list of users.
        """
        filt = filter_q or {}
        if "name" in filt:  # backward compatibility
            filt["username"] = filt.pop("name")
        if filt.get("username") and is_valid_uuid(filt["username"]):
            # username cannot be a uuid. If this is the case, change from username to _id
            filt["_id"] = filt.pop("username")
        users = self.db.get_list(self.users_collection, filt)
        project_id_name = {}
        role_id_name = {}
        for user in users:
            prms = user.get("project_role_mappings")
            projects = user.get("projects")
            if prms:
                projects = []
                # add project_name and role_name. Generate projects for backward compatibility
                for prm in prms:
                    project_id = prm["project"]
                    if project_id not in project_id_name:
                        pr = self.db.get_one(
                            self.projects_collection,
                            {BaseTopic.id_field("projects", project_id): project_id},
                            fail_on_empty=False,
                        )
                        project_id_name[project_id] = pr["name"] if pr else None
                    prm["project_name"] = project_id_name[project_id]
                    if prm["project_name"] not in projects:
                        projects.append(prm["project_name"])

                    role_id = prm["role"]
                    if role_id not in role_id_name:
                        role = self.db.get_one(
                            self.roles_collection,
                            {BaseTopic.id_field("roles", role_id): role_id},
                            fail_on_empty=False,
                        )
                        role_id_name[role_id] = role["name"] if role else None
                    prm["role_name"] = role_id_name[role_id]
                user["projects"] = projects  # for backward compatibility
            elif projects:
                # user created with an old version. Create a project_role mapping with role project_admin
                user["project_role_mappings"] = []
                role = self.db.get_one(
                    self.roles_collection,
                    {BaseTopic.id_field("roles", "project_admin"): "project_admin"},
                )
                for p_id_name in projects:
                    pr = self.db.get_one(
                        self.projects_collection,
                        {BaseTopic.id_field("projects", p_id_name): p_id_name},
                    )
                    prm = {
                        "project": pr["_id"],
                        "project_name": pr["name"],
                        "role_name": "project_admin",
                        "role": role["_id"],
                    }
                    user["project_role_mappings"].append(prm)
            else:
                user["projects"] = []
                user["project_role_mappings"] = []

        return users

    def get_project_list(self, filter_q={}):
        """
        Get role list.

        :return: returns the list of projects.
        """
        return self.db.get_list(self.projects_collection, filter_q)

    def create_project(self, project_info):
        """
        Create a project.

        :param project: full project info.
        :return: the internal id of the created project
        :raises AuthconnOperationException: if project creation failed.
        """
        pid = self.db.create(self.projects_collection, project_info)
        return pid

    def delete_project(self, project_id):
        """
        Delete a project.

        :param project_id: project identifier.
        :raises AuthconnOperationException: if project deletion failed.
        """
        idf = BaseTopic.id_field("projects", project_id)
        r = self.db.del_one(self.projects_collection, {idf: project_id})
        idf = "project_id" if idf == "_id" else "project_name"
        self.db.del_list(self.tokens_collection, {idf: project_id})
        return r

    def update_project(self, project_id, project_info):
        """
        Change the name of a project

        :param project_id: project to be changed
        :param project_info: full project info
        :return: None
        :raises AuthconnOperationException: if project update failed.
        """
        self.db.set_one(
            self.projects_collection,
            {BaseTopic.id_field("projects", project_id): project_id},
            project_info,
        )

    def generate_otp(self):
        otp = "".join(str(secrets.randbelow(10)) for i in range(0, 4))
        return otp

    def send_email(self, indata):
        user = indata.get("username")
        user_rows = self.db.get_list(self.users_collection, {"username": user})
        sender_password = None
        otp_expiry_time = self.config.get("otp_expiry_time", 300)
        if not re.match(email_schema["pattern"], indata.get("email_id")):
            raise AuthException(
                "Invalid email-id",
                http_code=HTTPStatus.BAD_REQUEST,
            )
        if self.config.get("sender_email"):
            sender_email = self.config["sender_email"]
        else:
            raise AuthException(
                "sender_email not found",
                http_code=HTTPStatus.NOT_FOUND,
            )
        if self.config.get("smtp_server"):
            smtp_server = self.config["smtp_server"]
        else:
            raise AuthException(
                "smtp server not found",
                http_code=HTTPStatus.NOT_FOUND,
            )
        if self.config.get("smtp_port"):
            smtp_port = self.config["smtp_port"]
        else:
            raise AuthException(
                "smtp port not found",
                http_code=HTTPStatus.NOT_FOUND,
            )
        sender_password = self.config.get("sender_password") or None
        if user_rows:
            user_data = user_rows[0]
            user_status = user_data["_admin"]["user_status"]
            if not user_data.get("project_role_mappings", None):
                raise AuthException(
                    "can't find a default project for this user",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )
            if user_status != "active" and user_status != "always-active":
                raise AuthException(
                    f"User account is {user_status}.Please contact the system administrator.",
                    http_code=HTTPStatus.UNAUTHORIZED,
                )
            if user_data.get("email_id"):
                if user_data["email_id"] == indata.get("email_id"):
                    otp = self.generate_otp()
                    encode_otp = hash_password(
                        password=otp, rounds=self.config.get("password_rounds", 12)
                    )
                    otp_field = {encode_otp: time() + otp_expiry_time, "retries": 0}
                    user_data["OTP"] = otp_field
                    uid = user_data["_id"]
                    idf = BaseTopic.id_field("users", uid)
                    reciever_email = user_data["email_id"]
                    email_template_path = self.config.get("email_template")
                    with open(email_template_path, "r") as et:
                        email_template = et.read()
                    msg = EmailMessage()
                    msg = MIMEMultipart("alternative")
                    html_content = email_template.format(
                        username=user_data["username"],
                        otp=otp,
                        validity=otp_expiry_time // 60,
                    )
                    html = MIMEText(html_content, "html")
                    msg["Subject"] = "OSM password reset request"
                    msg.attach(html)
                    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
                        smtp.starttls()
                        if sender_password:
                            smtp.login(sender_email, sender_password)
                        smtp.sendmail(sender_email, reciever_email, msg.as_string())
                        self.db.set_one(self.users_collection, {idf: uid}, user_data)
                return {"email": "sent"}
            else:
                raise AuthException(
                    "No email id is registered for this user.Please contact the system administrator.",
                    http_code=HTTPStatus.NOT_FOUND,
                )
        else:
            raise AuthException(
                "user not found",
                http_code=HTTPStatus.NOT_FOUND,
            )

    def validate_otp(self, indata):
        otp = indata.get("otp")
        user = indata.get("username")
        user_rows = self.db.get_list(self.users_collection, {"username": user})
        user_data = user_rows[0]
        uid = user_data["_id"]
        idf = BaseTopic.id_field("users", uid)
        retry_count = self.config.get("retry_count", 3)
        if user_data:
            if not user_data.get("OTP"):
                otp_field = {"retries": 1}
                user_data["OTP"] = otp_field
                self.db.set_one(self.users_collection, {idf: uid}, user_data)
                return {"retries": user_data["OTP"]["retries"]}
            for key, value in user_data["OTP"].items():
                curr_time = time()
                if (
                    verify_password(password=otp, hashed_password_hex=key)
                    and curr_time < value
                ):
                    user_data["OTP"] = {}
                    self.db.set_one(self.users_collection, {idf: uid}, user_data)
                    return {"valid": "True", "password_change": "True"}
                else:
                    user_data["OTP"]["retries"] += 1
                    self.db.set_one(self.users_collection, {idf: uid}, user_data)
                    if user_data["OTP"].get("retries") >= retry_count:
                        raise AuthException(
                            "Invalid OTP. Maximum retries exceeded",
                            http_code=HTTPStatus.TOO_MANY_REQUESTS,
                        )
                    return {"retry_count": user_data["OTP"]["retries"]}
