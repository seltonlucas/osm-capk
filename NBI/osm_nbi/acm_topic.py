# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pyrage import x25519
from uuid import uuid4

from http import HTTPStatus
from time import time

# from osm_common.dbbase import deep_update_rfc7396, DbException
from osm_common.msgbase import MsgException
from osm_common.dbbase import DbException
from osm_common.fsbase import FsException
from osm_nbi.base_topic import BaseTopic, EngineException
from osm_nbi.validation import ValidationError

import logging

# import random
# import string
# from yaml import safe_load, YAMLError


class ACMOperationTopic:
    def __init__(self, db, fs, msg, auth):
        self.multiproject = None  # Declare the attribute here
        self.db = db
        self.fs = fs
        self.msg = msg
        self.logger = logging.getLogger("nbi.base")
        self.auth = auth

    @staticmethod
    def format_on_operation(content, operation_type, operation_params=None):
        op_id = str(uuid4())
        now = time()
        if "operationHistory" not in content:
            content["operationHistory"] = []

        operation = {}
        operation["operationType"] = operation_type
        operation["op_id"] = op_id
        operation["result"] = None
        operation["creationDate"] = now
        operation["endDate"] = None
        operation["workflowState"] = operation["resourceState"] = operation[
            "operationState"
        ] = operation["gitOperationInfo"] = None
        operation["operationParams"] = operation_params

        content["operationHistory"].append(operation)
        return op_id

    def check_dependency(self, check, operation_type=None):
        topic_to_db_mapping = {
            "cluster": "clusters",
            "ksu": "ksus",
            "infra_controller_profiles": "k8sinfra_controller",
            "infra_config_profiles": "k8sinfra_config",
            "resource_profiles": "k8sresource",
            "app_profiles": "k8sapp",
            "oka": "okas",
        }
        for topic, _id in check.items():
            filter_q = {
                "_id": _id,
            }
            if topic == "okas":
                for oka_element in check[topic]:
                    self.check_dependency({"oka": oka_element})
            if topic not in ("okas"):
                element_content = self.db.get_one(topic_to_db_mapping[topic], filter_q)
                element_name = element_content.get("name")
                state = element_content["state"]
                if (
                    operation_type == "delete"
                    and state == "FAILED_CREATION"
                    and element_content["operatingState"] == "IDLE"
                ):
                    self.logger.info(f"Delete operation is allowed in {state} state")
                    return
                elif element_content["state"] != "CREATED":
                    raise EngineException(
                        f"State of the {element_name} {topic} is {state}",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                elif (
                    state == "CREATED"
                    and element_content["operatingState"] == "PROCESSING"
                ):
                    raise EngineException(
                        f"operatingState of the {element_name} {topic} is not IDLE",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )


class ACMTopic(BaseTopic, ACMOperationTopic):
    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        # ACMOperationTopic.__init__(db, fs, msg, auth)

    def new_profile(self, rollback, session, indata=None, kwargs=None, headers=None):
        step = "name unique check"
        try:
            self.check_unique_name(session, indata["name"])

            step = "validating input parameters"
            profile_request = self._remove_envelop(indata)
            self._update_input_with_kwargs(profile_request, kwargs)
            profile_request = self._validate_input_new(
                profile_request, session["force"]
            )
            operation_params = profile_request

            step = "filling profile details from input data"
            profile_create = self._create_profile(profile_request, session)

            step = "creating profile at database"
            self.format_on_new(
                profile_create, session["project_id"], make_public=session["public"]
            )
            profile_create["current_operation"] = None
            op_id = ACMOperationTopic.format_on_operation(
                profile_create,
                "create",
                operation_params,
            )

            _id = self.db.create(self.topic, profile_create)
            pubkey, privkey = self._generate_age_key()
            profile_create["age_pubkey"] = self.db.encrypt(
                pubkey, schema_version="1.11", salt=_id
            )
            profile_create["age_privkey"] = self.db.encrypt(
                privkey, schema_version="1.11", salt=_id
            )
            rollback.append({"topic": self.topic, "_id": _id})
            self.db.set_one(self.topic, {"_id": _id}, profile_create)
            if op_id:
                profile_create["op_id"] = op_id
            self._send_msg("profile_create", {"profile_id": _id, "operation_id": op_id})

            return _id, None
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _create_profile(self, profile_request, session):
        profile_desc = {
            "name": profile_request["name"],
            "description": profile_request["description"],
            "default": False,
            "git_name": self.create_gitname(profile_request, session),
            "state": "IN_CREATION",
            "operatingState": "IN_PROGRESS",
            "resourceState": "IN_PROGRESS.REQUEST_RECEIVED",
        }
        return profile_desc

    def default_profile(
        self, rollback, session, indata=None, kwargs=None, headers=None
    ):
        step = "validating input parameters"
        try:
            profile_request = self._remove_envelop(indata)
            self._update_input_with_kwargs(profile_request, kwargs)
            operation_params = profile_request

            step = "filling profile details from input data"
            profile_create = self._create_default_profile(profile_request, session)

            step = "creating profile at database"
            self.format_on_new(
                profile_create, session["project_id"], make_public=session["public"]
            )
            profile_create["current_operation"] = None
            ACMOperationTopic.format_on_operation(
                profile_create,
                "create",
                operation_params,
            )
            _id = self.db.create(self.topic, profile_create)
            rollback.append({"topic": self.topic, "_id": _id})
            return _id
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _create_default_profile(self, profile_request, session):
        profile_desc = {
            "name": profile_request["name"],
            "description": f"{self.topic} profile for cluster {profile_request['name']}",
            "default": True,
            "git_name": self.create_gitname(profile_request, session),
            "state": "IN_CREATION",
            "operatingState": "IN_PROGRESS",
            "resourceState": "IN_PROGRESS.REQUEST_RECEIVED",
        }
        return profile_desc

    def detach(self, session, _id, profile_type):
        # To detach the profiles from every cluster
        filter_q = {}
        existing_clusters = self.db.get_list("clusters", filter_q)
        existing_clusters_profiles = [
            profile["_id"]
            for profile in existing_clusters
            if profile.get("profile_type", _id)
        ]
        update_dict = None
        for profile in existing_clusters_profiles:
            filter_q = {"_id": profile}
            data = self.db.get_one("clusters", filter_q)
            if profile_type in data:
                profile_ids = data[profile_type]
                if _id in profile_ids:
                    profile_ids.remove(_id)
                    update_dict = {profile_type: profile_ids}
                    self.db.set_one("clusters", filter_q, update_dict)

    def _generate_age_key(self):
        ident = x25519.Identity.generate()
        # gets the public key
        pubkey = str(ident.to_public())
        # gets the private key
        privkey = str(ident)
        # return both public and private key
        return pubkey, privkey

    def common_delete(self, _id, db_content):
        if "state" in db_content:
            db_content["state"] = "IN_DELETION"
            db_content["operatingState"] = "PROCESSING"
            # self.db.set_one(self.topic, {"_id": _id}, db_content)

        db_content["current_operation"] = None
        op_id = ACMOperationTopic.format_on_operation(
            db_content,
            "delete",
            None,
        )
        self.db.set_one(self.topic, {"_id": _id}, db_content)
        return op_id

    def add_to_old_collection(self, content, session):
        item = {}
        item["name"] = content["name"]
        item["credentials"] = {}
        # item["k8s_version"] = content["k8s_version"]
        if "k8s_version" in content:
            item["k8s_version"] = content["k8s_version"]
        else:
            item["k8s_version"] = None
        vim_account_details = self.db.get_one(
            "vim_accounts", {"name": content["vim_account"]}
        )
        item["vim_account"] = vim_account_details["_id"]
        item["nets"] = {"k8s_net1": None}
        item["deployment_methods"] = {"juju-bundle": False, "helm-chart-v3": True}
        # item["description"] = content["description"]
        if "description" in content:
            item["description"] = content["description"]
        else:
            item["description"] = None
        item["namespace"] = "kube-system"
        item["osm_acm"] = True
        item["schema_version"] = "1.11"
        self.format_on_new(item, session["project_id"], make_public=session["public"])
        _id = self.db.create("k8sclusters", item)
        self.logger.info(f"_id is : {_id}")
        item_1 = self.db.get_one("k8sclusters", {"name": item["name"]})
        item_1["_admin"]["operationalState"] = "PROCESSING"

        # Create operation data
        now = time()
        operation_data = {
            "lcmOperationType": "create",  # Assuming 'create' operation here
            "operationState": "PROCESSING",
            "startTime": now,
            "statusEnteredTime": now,
            "detailed-status": "",
            "operationParams": None,  # Add parameters as needed
        }
        # create operation
        item_1["_admin"]["operations"] = [operation_data]
        item_1["_admin"]["current_operation"] = None
        self.logger.info(f"content is : {item_1}")
        self.db.set_one("k8sclusters", {"_id": item_1["_id"]}, item_1)
        return

    def cluster_unique_name_check(self, session, name):
        # First check using the method you have for unique name validation
        self.check_unique_name(session, name)
        _filter = {"name": name}
        topics = [
            "k8sclusters",
            "k8sapp",
            "k8sinfra_config",
            "k8sinfra_controller",
            "k8sresource",
        ]

        # Loop through each topic to check if the name already exists in any of them
        for item in topics:
            if self.db.get_one(item, _filter, fail_on_empty=False, fail_on_more=False):
                raise EngineException(
                    f"name '{name}' already exists in topic '{item}'",
                    HTTPStatus.CONFLICT,
                )

    def list_both(self, session, filter_q=None, api_req=False):
        """List all clusters from both new and old APIs"""
        if not filter_q:
            filter_q = {}
        if self.multiproject:
            filter_q.update(self._get_project_filter(session))
        cluster_list1 = self.db.get_list(self.topic, filter_q)
        cluster_list2 = self.db.get_list("k8sclusters", filter_q)
        list1_names = {item["name"] for item in cluster_list1}
        for item in cluster_list2:
            if item["name"] not in list1_names:
                # Complete the information for clusters from old API
                item["state"] = "N/A"
                old_state = item.get("_admin", {}).get("operationalState", "Unknown")
                item["bootstrap"] = "NO"
                item["operatingState"] = "N/A"
                item["resourceState"] = old_state
                item["created"] = "NO"
                cluster_list1.append(item)
        if api_req:
            cluster_list1 = [self.sol005_projection(inst) for inst in cluster_list1]
        return cluster_list1


class ProfileTopic(ACMTopic):
    profile_topic_map = {
        "k8sapp": "app_profiles",
        "k8sresource": "resource_profiles",
        "k8sinfra_controller": "infra_controller_profiles",
        "k8sinfra_config": "infra_config_profiles",
    }

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def edit_extra_before(self, session, _id, indata=None, kwargs=None, content=None):
        check = self.db.get_one(self.topic, {"_id": _id})
        if check["default"] is True:
            raise EngineException(
                "Cannot edit default profiles",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        if "name" in indata and check["name"] != indata["name"]:
            self.check_unique_name(session, indata["name"])
        return True

    def delete_extra_before(self, session, _id, db_content, not_send_msg=None):
        op_id = self.common_delete(_id, db_content)
        return {"profile_id": _id, "operation_id": op_id, "force": session["force"]}

    def delete_profile(self, session, _id, dry_run=False, not_send_msg=None):
        item_content = self.db.get_one(self.topic, {"_id": _id})
        if item_content.get("default", False):
            raise EngineException(
                "Cannot delete item because it is marked as default",
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        # Before deleting, detach the profile from the associated clusters.
        profile_type = self.profile_topic_map[self.topic]
        self.detach(session, _id, profile_type)
        # To delete the infra controller profile
        super().delete(session, _id, not_send_msg=not_send_msg)
        return _id
