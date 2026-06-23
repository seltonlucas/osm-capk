# -*- coding: utf-8 -*-

# Copyright 2020 TATA ELXSI
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
# contact: saikiran.k@tataelxsi.co.in
##


"""
AuthconnTacacs implements implements the connector for TACACS.
Leverages AuthconnInternal for token lifecycle management and the RBAC model.

When NBI bootstraps, it tries to create admin user with admin role associated to admin project.
Hence, the TACACS server should contain admin user.
"""

__author__ = "K Sai Kiran <saikiran.k@tataelxsi.co.in>"
__date__ = "$11-Nov-2020 11:04:00$"


from osm_nbi.authconn import Authconn, AuthException
from osm_nbi.authconn_internal import AuthconnInternal
from osm_nbi.base_topic import BaseTopic

import logging
from time import time
from http import HTTPStatus

# TACACS+ Library
from tacacs_plus.client import TACACSClient


class AuthconnTacacs(AuthconnInternal):
    token_time_window = 2
    token_delay = 1

    tacacs_def_port = 49
    tacacs_def_timeout = 10
    users_collection = "users_tacacs"
    roles_collection = "roles_tacacs"
    projects_collection = "projects_tacacs"
    tokens_collection = "tokens_tacacs"

    def __init__(self, config, db, role_permissions):
        """
        Constructor to initialize db and TACACS server attributes to members.
        """
        Authconn.__init__(self, config, db, role_permissions)
        self.logger = logging.getLogger("nbi.authenticator.tacacs")
        self.db = db
        self.tacacs_host = config["tacacs_host"]
        self.tacacs_secret = config["tacacs_secret"]
        self.tacacs_port = (
            config["tacacs_port"] if config.get("tacacs_port") else self.tacacs_def_port
        )
        self.tacacs_timeout = (
            config["tacacs_timeout"]
            if config.get("tacacs_timeout")
            else self.tacacs_def_timeout
        )
        self.tacacs_cli = TACACSClient(
            self.tacacs_host, self.tacacs_port, self.tacacs_secret, self.tacacs_timeout
        )

    def validate_user(self, user, password):
        """"""
        now = time()
        try:
            tacacs_authen = self.tacacs_cli.authenticate(user, password)
        except Exception as e:
            raise AuthException(
                "TACACS server error: {}".format(e), http_code=HTTPStatus.UNAUTHORIZED
            )
        user_content = None
        user_rows = self.db.get_list(
            self.users_collection, {BaseTopic.id_field("users", user): user}
        )
        if not tacacs_authen.valid:
            if user_rows:
                # To remove TACACS stale user from system.
                self.delete_user(user_rows[0][BaseTopic.id_field("users", user)])
            return user_content
        if user_rows:
            user_content = user_rows[0]
        else:
            new_user = {
                "username": user,
                "password": password,
                "_admin": {"created": now, "modified": now},
                "project_role_mappings": [],
            }
            user_content = self.create_user(new_user)
        return user_content

    def create_user(self, user_info):
        """
        Validates user credentials in TACACS and add user.

        :param user_info: Full user information in dict.
        :return: returns username and id if credentails are valid. Otherwise, raise exception
        """
        BaseTopic.format_on_new(user_info, make_public=False)
        try:
            authen = self.tacacs_cli.authenticate(
                user_info["username"], user_info["password"]
            )
            if authen.valid:
                user_info.pop("password")
                self.db.create(self.users_collection, user_info)
            else:
                raise AuthException(
                    "TACACS server error: Invalid credentials",
                    http_code=HTTPStatus.FORBIDDEN,
                )
        except Exception as e:
            raise AuthException(
                "TACACS server error: {}".format(e), http_code=HTTPStatus.BAD_REQUEST
            )
        return {"username": user_info["username"], "_id": user_info["_id"]}

    def update_user(self, user_info):
        """
        Updates user information, in particular for add/remove of project and role mappings.
        Does not allow change of username or password.

        :param user_info: Full user information in dict.
        :return: returns None for successful add/remove of project and role map.
        """
        if user_info.get("username"):
            raise AuthException(
                "Can not update username of this user", http_code=HTTPStatus.FORBIDDEN
            )
        if user_info.get("password"):
            raise AuthException(
                "Can not update password of this user", http_code=HTTPStatus.FORBIDDEN
            )
        super(AuthconnTacacs, self).update_user(user_info)
