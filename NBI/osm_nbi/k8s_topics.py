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

import logging
import yaml
import shutil
import os
from http import HTTPStatus

from time import time
from osm_nbi.base_topic import BaseTopic, EngineException
from osm_nbi.acm_topic import ACMTopic, ACMOperationTopic, ProfileTopic

from osm_nbi.descriptor_topics import DescriptorTopic
from osm_nbi.validation import (
    ValidationError,
    validate_input,
    cluster_creation_new_schema,
    cluster_edit_schema,
    cluster_update_schema,
    infra_controller_profile_create_new_schema,
    infra_config_profile_create_new_schema,
    app_profile_create_new_schema,
    resource_profile_create_new_schema,
    infra_controller_profile_create_edit_schema,
    infra_config_profile_create_edit_schema,
    app_profile_create_edit_schema,
    resource_profile_create_edit_schema,
    cluster_registration_new_schema,
    attach_dettach_profile_schema,
    ksu_schema,
    app_instance_schema,
    app_instance_edit_schema,
    app_instance_update_schema,
    oka_schema,
    node_create_new_schema,
    node_edit_schema,
)
from osm_common.dbbase import deep_update_rfc7396, DbException
from osm_common.msgbase import MsgException
from osm_common.fsbase import FsException

__author__ = (
    "Shrinithi R <shrinithi.r@tataelxsi.co.in>",
    "Shahithya Y <shahithya.y@tataelxsi.co.in>",
)


class InfraContTopic(ProfileTopic):
    topic = "k8sinfra_controller"
    topic_msg = "k8s_infra_controller"
    schema_new = infra_controller_profile_create_new_schema
    schema_edit = infra_controller_profile_create_edit_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the new infra controller profile
        return self.new_profile(rollback, session, indata, kwargs, headers)

    def default(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the default infra controller profile while creating the cluster
        return self.default_profile(rollback, session, indata, kwargs, headers)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check = {"infra_controller_profiles": _id}
        self.check_dependency(check, operation_type="delete")
        self.delete_profile(session, _id, dry_run, not_send_msg)
        return _id


class InfraConfTopic(ProfileTopic):
    topic = "k8sinfra_config"
    topic_msg = "k8s_infra_config"
    schema_new = infra_config_profile_create_new_schema
    schema_edit = infra_config_profile_create_edit_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the new infra config profile
        return self.new_profile(rollback, session, indata, kwargs, headers)

    def default(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the default infra config profile while creating the cluster
        return self.default_profile(rollback, session, indata, kwargs, headers)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check = {"infra_config_profiles": _id}
        self.check_dependency(check, operation_type="delete")
        self.delete_profile(session, _id, dry_run, not_send_msg)
        return _id


class AppProfileTopic(ProfileTopic):
    topic = "k8sapp"
    topic_msg = "k8s_app"
    schema_new = app_profile_create_new_schema
    schema_edit = app_profile_create_edit_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the new app profile
        return self.new_profile(rollback, session, indata, kwargs, headers)

    def default(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the default app profile while creating the cluster
        return self.default_profile(rollback, session, indata, kwargs, headers)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check = {"app_profiles": _id}
        self.check_dependency(check, operation_type="delete")
        self.delete_profile(session, _id, dry_run, not_send_msg)
        return _id


class ResourceTopic(ProfileTopic):
    topic = "k8sresource"
    topic_msg = "k8s_resource"
    schema_new = resource_profile_create_new_schema
    schema_edit = resource_profile_create_edit_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the new resource profile
        return self.new_profile(rollback, session, indata, kwargs, headers)

    def default(self, rollback, session, indata=None, kwargs=None, headers=None):
        # To create the default resource profile while creating the cluster
        return self.default_profile(rollback, session, indata, kwargs, headers)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check = {"resource_profiles": _id}
        self.check_dependency(check, operation_type="delete")
        self.delete_profile(session, _id, dry_run, not_send_msg)
        return _id


class ClusterTopic(ACMTopic):
    topic = "clusters"
    topic_msg = "cluster"
    schema_new = cluster_creation_new_schema
    schema_edit = attach_dettach_profile_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        self.infra_contr_topic = InfraContTopic(db, fs, msg, auth)
        self.infra_conf_topic = InfraConfTopic(db, fs, msg, auth)
        self.resource_topic = ResourceTopic(db, fs, msg, auth)
        self.app_topic = AppProfileTopic(db, fs, msg, auth)

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        ACMTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["current_operation"] = None

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates a new k8scluster into database.
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the k8cluster
        :param kwargs: used to override the indata
        :param headers: http request headers
        :return: the _id of k8scluster created at database. Or an exception of type
            EngineException, ValidationError, DbException, FsException, MsgException.
            Note: Exceptions are not captured on purpose. They should be captured at called
        """

        step = "checking quotas"  # first step must be defined outside try
        try:
            if self.multiproject:
                self.check_quota(session)

            content = self._remove_envelop(indata)

            step = "name unique check"
            self.cluster_unique_name_check(session, indata["name"])

            step = "validating input parameters"
            self._update_input_with_kwargs(content, kwargs)

            content = self._validate_input_new(content, session, force=session["force"])

            operation_params = indata.copy()

            self.check_conflict_on_new(session, content)
            self.format_on_new(
                content, project_id=session["project_id"], make_public=session["public"]
            )

            step = "filling cluster details from input data"
            content = self._create_cluster(
                content, rollback, session, indata, kwargs, headers
            )

            step = "creating cluster at database"
            _id = self.db.create(self.topic, content)

            op_id = self.format_on_operation(
                content,
                "create",
                operation_params,
            )

            pubkey, privkey = self._generate_age_key()
            content["age_pubkey"] = self.db.encrypt(
                pubkey, schema_version="1.11", salt=_id
            )
            content["age_privkey"] = self.db.encrypt(
                privkey, schema_version="1.11", salt=_id
            )

            # TODO: set age_pubkey and age_privkey in the default profiles
            rollback.append({"topic": self.topic, "_id": _id})
            self.db.set_one("clusters", {"_id": _id}, content)
            self._send_msg("create", {"cluster_id": _id, "operation_id": op_id})

            # To add the content in old collection "k8sclusters"
            self.add_to_old_collection(content, session)

            return _id, None
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _validate_input_new(self, content, session, force=False):
        # validating vim and checking the mandatory parameters
        vim_type = self.check_vim(session, content["vim_account"])

        # for aws
        if vim_type == "aws":
            self._aws_check(content)

        # for azure and gcp
        elif vim_type in ["azure", "gcp"]:
            self._params_check(content)

        # for kubevirt (CAPK): clusters are provisioned by Cluster API on the OSM
        # management cluster as KubeVirt VMs. The worker node_count is required,
        # like azure/gcp; control-plane count and VM sizing are optional (defaults
        # applied by LCM / the workflow template).
        elif vim_type == "kubevirt":
            self._params_check(content)

        return super()._validate_input_new(content, force=session["force"])

    def _aws_check(self, indata):
        if "node_count" in indata or "node_size" in indata:
            raise ValueError("node_count and node_size are not allowed for AWS")
        return

    def _params_check(self, indata):
        if "node_count" not in indata and "node_size" not in indata:
            raise ValueError("node_count and node_size are mandatory parameter")
        return

    def _create_cluster(self, content, rollback, session, indata, kwargs, headers):
        private_subnet = indata.get("private_subnet")
        public_subnet = indata.get("public_subnet")

        # Enforce: if private_subnet is provided, public_subnet must also be provided
        if (private_subnet and not public_subnet) or (
            public_subnet and not private_subnet
        ):
            raise ValueError(
                "'public_subnet' must be provided if 'private_subnet' is given and viceversa."
            )

        # private Subnet validation
        if private_subnet:
            count = len(private_subnet)
            if count != 2:
                raise ValueError(
                    f"private_subnet must contain exactly 2 items, got {count}"
                )

        # public Subnet validation
        public_subnet = indata.get("public_subnet")
        if public_subnet:
            count = len(public_subnet)
            if count != 1:
                raise ValueError(
                    f"public_subnet must contain exactly 1 items, got {count}"
                )

        content["infra_controller_profiles"] = [
            self._create_default_profiles(
                rollback, session, indata, kwargs, headers, self.infra_contr_topic
            )
        ]
        content["infra_config_profiles"] = [
            self._create_default_profiles(
                rollback, session, indata, kwargs, headers, self.infra_conf_topic
            )
        ]
        content["resource_profiles"] = [
            self._create_default_profiles(
                rollback, session, indata, kwargs, headers, self.resource_topic
            )
        ]
        content["app_profiles"] = [
            self._create_default_profiles(
                rollback, session, indata, kwargs, headers, self.app_topic
            )
        ]
        content["created"] = "true"
        content["state"] = "IN_CREATION"
        content["operatingState"] = "PROCESSING"
        content["git_name"] = self.create_gitname(content, session)
        content["resourceState"] = "IN_PROGRESS.REQUEST_RECEIVED"

        # Get the vim_account details
        vim_account_details = self.db.get_one(
            "vim_accounts", {"name": content["vim_account"]}
        )

        # Add optional fields if they don't exist in the request
        if "region_name" not in indata:
            region_name = vim_account_details.get("config", {}).get("region_name")
            if region_name:
                content["region_name"] = region_name

        if "resource_group" not in indata:
            resource_group = vim_account_details.get("config", {}).get("resource_group")
            if resource_group:
                content["resource_group"] = resource_group

        version = "k8s_version" in content
        if not version:
            content["k8s_version"] = "1.32"
        # Additional cluster information, specific for each cluster type
        content["config"] = indata.get("config", {})
        content["node_count"] = indata.get("node_count", 0)
        content["ksu_count"] = 0
        self.logger.info(f"content is : {content}")
        return content

    def check_vim(self, session, name):
        try:
            vim_account_details = self.db.get_one("vim_accounts", {"name": name})
            if vim_account_details is not None:
                return vim_account_details["vim_type"]
        except ValidationError as e:
            raise EngineException(
                e,
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    def _create_default_profiles(
        self, rollback, session, indata, kwargs, headers, topic
    ):
        topic = self.to_select_topic(topic)
        default_profiles = topic.default(rollback, session, indata, kwargs, headers)
        return default_profiles

    def to_select_topic(self, topic):
        if topic == "infra_controller_profiles":
            topic = self.infra_contr_topic
        elif topic == "infra_config_profiles":
            topic = self.infra_conf_topic
        elif topic == "resource_profiles":
            topic = self.resource_topic
        elif topic == "app_profiles":
            topic = self.app_topic
        return topic

    def show_one(self, session, _id, profile, filter_q=None, api_req=False):
        try:
            filter_q = self._get_project_filter(session)
            filter_q[self.id_field(self.topic, _id)] = _id
            content = self.db.get_one(self.topic, filter_q)
            existing_profiles = []
            topic = None
            topic = self.to_select_topic(profile)
            for profile_id in content[profile]:
                data = topic.show(session, profile_id, filter_q, api_req)
                existing_profiles.append(data)
            return existing_profiles
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def state_check(self, profile_id, session, topic):
        topic = self.to_select_topic(topic)
        content = topic.show(session, profile_id, filter_q=None, api_req=False)
        state = content["state"]
        if state == "CREATED":
            return
        else:
            raise EngineException(
                f" {profile_id}  is not in created state",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    def edit(self, session, _id, item, indata=None, kwargs=None):
        if item not in (
            "infra_controller_profiles",
            "infra_config_profiles",
            "app_profiles",
            "resource_profiles",
        ):
            self.schema_edit = cluster_edit_schema
            super().edit(session, _id, indata=item, kwargs=kwargs, content=None)
        else:
            indata = self._remove_envelop(indata)
            indata = self._validate_input_edit(
                indata, content=None, force=session["force"]
            )
            if indata.get("add_profile"):
                self.add_profile(session, _id, item, indata)
            elif indata.get("remove_profile"):
                self.remove_profile(session, _id, item, indata)
            else:
                error_msg = "Add / remove operation is only applicable"
                raise EngineException(error_msg, HTTPStatus.UNPROCESSABLE_ENTITY)

    def edit_extra_before(self, session, _id, indata=None, kwargs=None, content=None):
        check_dict = self.db.get_one(self.topic, {"_id": _id})
        if "name" in indata and check_dict["name"] != indata["name"]:
            self.check_unique_name(session, indata["name"])
            _filter = {"name": indata["name"]}
            topic_list = [
                "k8sclusters",
                "k8sinfra_controller",
                "k8sinfra_config",
                "k8sapp",
                "k8sresource",
            ]
            # Check unique name for k8scluster and profiles
            for topic in topic_list:
                if self.db.get_one(
                    topic, _filter, fail_on_empty=False, fail_on_more=False
                ):
                    raise EngineException(
                        "name '{}' already exists for {}".format(indata["name"], topic),
                        HTTPStatus.CONFLICT,
                    )
            # Replace name in k8scluster and profiles
            for topic in topic_list:
                data = self.db.get_one(topic, {"name": check_dict["name"]})
                data["name"] = indata["name"]
                self.db.replace(topic, data["_id"], data)
        return True

    def add_profile(self, session, _id, item, indata=None):
        check = {"cluster": _id, item: indata["add_profile"][0]["id"]}
        self.check_dependency(check)
        indata = self._remove_envelop(indata)
        operation_params = indata
        profile_id = indata["add_profile"][0]["id"]
        # check state
        self.state_check(profile_id, session, item)
        filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        content = self.db.get_one(self.topic, filter_q)
        profile_list = content[item]

        if profile_id not in profile_list:
            content["operatingState"] = "PROCESSING"
            op_id = self.format_on_operation(
                content,
                "add",
                operation_params,
            )
            self.db.set_one("clusters", {"_id": content["_id"]}, content)
            self._send_msg(
                "add",
                {
                    "cluster_id": _id,
                    "profile_id": profile_id,
                    "profile_type": item,
                    "operation_id": op_id,
                },
            )
        else:
            raise EngineException(
                f"{item} {profile_id} already exists", HTTPStatus.UNPROCESSABLE_ENTITY
            )

    def _get_default_profiles(self, session, topic):
        topic = self.to_select_topic(topic)
        existing_profiles = topic.list(session, filter_q=None, api_req=False)
        default_profiles = [
            profile["_id"]
            for profile in existing_profiles
            if profile.get("default", False)
        ]
        return default_profiles

    def remove_profile(self, session, _id, item, indata):
        check = {"cluster": _id, item: indata["remove_profile"][0]["id"]}
        self.check_dependency(check)
        indata = self._remove_envelop(indata)
        operation_params = indata
        profile_id = indata["remove_profile"][0]["id"]
        filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        content = self.db.get_one(self.topic, filter_q)
        profile_list = content[item]

        default_profiles = self._get_default_profiles(session, item)

        if profile_id in default_profiles:
            raise EngineException(
                "Cannot remove default profile", HTTPStatus.UNPROCESSABLE_ENTITY
            )
        if profile_id in profile_list:
            op_id = self.format_on_operation(
                content,
                "remove",
                operation_params,
            )
            self.db.set_one("clusters", {"_id": content["_id"]}, content)
            self._send_msg(
                "remove",
                {
                    "cluster_id": _id,
                    "profile_id": profile_id,
                    "profile_type": item,
                    "operation_id": op_id,
                },
            )
        else:
            raise EngineException(
                f"{item} {profile_id} does'nt exists", HTTPStatus.UNPROCESSABLE_ENTITY
            )

    def get_cluster_creds(self, session, _id, item):
        if not self.multiproject:
            filter_db = {}
        else:
            filter_db = self._get_project_filter(session)
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id
        operation_params = None
        data = self.db.get_one(self.topic, filter_db)
        op_id = self.format_on_operation(data, item, operation_params)
        self.db.set_one(self.topic, {"_id": data["_id"]}, data)
        self._send_msg("get_creds", {"cluster_id": _id, "operation_id": op_id})
        return op_id

    def get_cluster_creds_file(self, session, _id, item, op_id):
        if not self.multiproject:
            filter_db = {}
        else:
            filter_db = self._get_project_filter(session)
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id

        data = self.db.get_one(self.topic, filter_db)
        creds_flag = None
        for operations in data["operationHistory"]:
            if operations["op_id"] == op_id:
                creds_flag = operations["result"]
        self.logger.info("Creds Flag: {}".format(creds_flag))

        if creds_flag is True:
            credentials = data["credentials"]

            file_pkg = None
            current_path = _id

            self.fs.file_delete(current_path, ignore_non_exist=True)
            self.fs.mkdir(current_path)
            filename = "credentials.yaml"
            file_path = (current_path, filename)
            self.logger.info("File path: {}".format(file_path))
            file_pkg = self.fs.file_open(file_path, "a+b")

            credentials_yaml = yaml.safe_dump(
                credentials, indent=4, default_flow_style=False
            )
            file_pkg.write(credentials_yaml.encode(encoding="utf-8"))

            if file_pkg:
                file_pkg.close()
            file_pkg = None
            self.fs.sync(from_path=current_path)

            return (
                self.fs.file_open((current_path, filename), "rb"),
                "text/plain",
            )
        else:
            raise EngineException(
                "Not possible to get the credentials of the cluster",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    def update_item(self, session, _id, item, indata):
        if not self.multiproject:
            filter_db = {}
        else:
            filter_db = self._get_project_filter(session)
        # To allow project&user addressing by name AS WELL AS _id
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id
        validate_input(indata, cluster_update_schema)
        data = self.db.get_one(self.topic, filter_db)
        operation_params = {}
        data["operatingState"] = "PROCESSING"
        data["resourceState"] = "IN_PROGRESS"
        operation_params = indata
        op_id = self.format_on_operation(
            data,
            item,
            operation_params,
        )
        self.db.set_one(self.topic, {"_id": _id}, data)
        data = {"cluster_id": _id, "operation_id": op_id}
        self._send_msg(item, data)
        return op_id

    def delete_extra_before(self, session, _id, db_content, not_send_msg=None):
        op_id = self.common_delete(_id, db_content)
        return {"cluster_id": _id, "operation_id": op_id, "force": session["force"]}

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check_dict = {"cluster": _id}
        self.check_dependency(check_dict, operation_type="delete")
        filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        check_dict = self.db.get_one(self.topic, filter_q)
        op_id = check_dict["current_operation"]
        if check_dict["created"] == "false":
            raise EngineException(
                "Cannot delete registered cluster. Please deregister.",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        super().delete(session, _id, dry_run, not_send_msg)
        return op_id


class NodeGroupTopic(ACMTopic):
    topic = "nodegroups"
    topic_msg = "nodegroup"
    schema_new = node_create_new_schema
    schema_edit = node_edit_schema

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["current_operation"] = None
        content["state"] = "IN_CREATION"
        content["operatingState"] = "PROCESSING"
        content["resourceState"] = "IN_PROGRESS"

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        self.logger.info(f"Indata: {indata}")
        self.check_unique_name(session, indata["name"])

        indata = self._remove_envelop(indata)
        self._update_input_with_kwargs(indata, kwargs)
        if not indata.get("private_subnet") and not indata.get("public_subnet"):
            raise EngineException(
                "Please provide atleast one subnet",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        content = self._validate_input_new(indata, session["force"])

        self.logger.info(f"Indata: {indata}")
        self.logger.info(f"Content: {content}")
        cluster_id = content["cluster_id"]
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})
        private_subnet = db_cluster.get("private_subnet")
        public_subnet = db_cluster.get("public_subnet")
        if content.get("private_subnet"):
            for subnet in content["private_subnet"]:
                if subnet not in private_subnet:
                    raise EngineException(
                        "No External subnet is used to add nodegroup",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
        if content.get("public_subnet"):
            for subnet in content["public_subnet"]:
                if subnet not in public_subnet:
                    raise EngineException(
                        "No External subnet is used to add nodegroup",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

        operation_params = {}
        for content_key, content_value in content.items():
            operation_params[content_key] = content_value
        self.format_on_new(
            content, session["project_id"], make_public=session["public"]
        )
        content["git_name"] = self.create_gitname(content, session)
        self.logger.info(f"Operation Params: {operation_params}")
        op_id = self.format_on_operation(
            content,
            "create",
            operation_params,
        )
        node_count = db_cluster.get("node_count")
        new_node_count = node_count + 1
        self.logger.info(f"New Node count: {new_node_count}")
        db_cluster["node_count"] = new_node_count
        self.db.set_one("clusters", {"_id": cluster_id}, db_cluster)
        _id = self.db.create(self.topic, content)
        self._send_msg("add_nodegroup", {"nodegroup_id": _id, "operation_id": op_id})
        return _id, op_id

    def list(self, session, filter_q=None, api_req=False):
        db_filter = {}
        if filter_q.get("cluster_id"):
            db_filter["cluster_id"] = filter_q.get("cluster_id")
        data_list = self.db.get_list(self.topic, db_filter)
        cluster_data = self.db.get_one("clusters", {"_id": db_filter["cluster_id"]})
        self.logger.info(f"Cluster Data: {cluster_data}")
        self.logger.info(f"Data: {data_list}")
        if filter_q.get("cluster_id"):
            outdata = {}
            outdata["count"] = cluster_data["node_count"]
            outdata["data"] = data_list
            self.logger.info(f"Outdata: {outdata}")
            return outdata
        if api_req:
            data_list = [self.sol005_projection(inst) for inst in data_list]
        return data_list

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        if not self.multiproject:
            filter_q = {}
        else:
            filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        item_content = self.db.get_one(self.topic, filter_q)
        item_content["state"] = "IN_DELETION"
        item_content["operatingState"] = "PROCESSING"
        item_content["resourceState"] = "IN_PROGRESS"
        self.check_conflict_on_del(session, _id, item_content)
        op_id = self.format_on_operation(
            item_content,
            "delete",
            None,
        )
        self.db.set_one(self.topic, {"_id": item_content["_id"]}, item_content)
        self._send_msg(
            "delete_nodegroup",
            {"nodegroup_id": _id, "operation_id": op_id},
            not_send_msg=not_send_msg,
        )
        return op_id

    def update_item(self, session, _id, item, indata):
        content = None
        try:
            if not content:
                content = self.db.get_one(self.topic, {"_id": _id})
            indata = self._validate_input_edit(indata, content, force=session["force"])
            _id = content.get("_id") or _id

            content = self.check_conflict_on_edit(session, content, indata, _id=_id)
            op_id = self.format_on_edit(content, indata)
            op_id = ACMTopic.format_on_operation(
                content,
                "scale",
                indata,
            )
            self.logger.info(f"op_id: {op_id}")
            content["operatingState"] = "PROCESSING"
            content["resourceState"] = "IN_PROGRESS"
            self.db.replace(self.topic, _id, content)
            self._send_msg(
                "scale_nodegroup", {"nodegroup_id": _id, "operation_id": op_id}
            )
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def edit(self, session, _id, indata, kwargs):
        content = None

        # Override descriptor with query string kwargs
        if kwargs:
            self._update_input_with_kwargs(indata, kwargs)
        try:
            if indata and session.get("set_project"):
                raise EngineException(
                    "Cannot edit content and set to project (query string SET_PROJECT) at same time",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            # TODO self._check_edition(session, indata, _id, force)
            if not content:
                content = self.db.get_one(self.topic, {"_id": _id})

            indata = self._validate_input_edit(indata, content, force=session["force"])
            self.logger.info(f"Indata: {indata}")

            # To allow project addressing by name AS WELL AS _id. Get the _id, just in case the provided one is a name
            _id = content.get("_id") or _id

            content = self.check_conflict_on_edit(session, content, indata, _id=_id)
            if "name" in indata and "description" in indata:
                content["name"] = indata["name"]
                content["description"] = indata["description"]
            elif "name" in indata:
                content["name"] = indata["name"]
            elif "description" in indata:
                content["description"] = indata["description"]
            op_id = self.format_on_edit(content, indata)
            self.db.set_one(self.topic, {"_id": _id}, content)
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)


class ClusterOpsTopic(ACMTopic):
    topic = "clusters"
    topic_msg = "cluster"
    schema_new = cluster_registration_new_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        self.infra_contr_topic = InfraContTopic(db, fs, msg, auth)
        self.infra_conf_topic = InfraConfTopic(db, fs, msg, auth)
        self.resource_topic = ResourceTopic(db, fs, msg, auth)
        self.app_topic = AppProfileTopic(db, fs, msg, auth)

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        ACMTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["current_operation"] = None

    def add(self, rollback, session, indata, kwargs=None, headers=None):
        step = "checking quotas"
        try:
            self.check_quota(session)
            step = "name unique check"
            self.cluster_unique_name_check(session, indata["name"])
            # self.check_unique_name(session, indata["name"])
            step = "validating input parameters"
            cls_add_request = self._remove_envelop(indata)
            self._update_input_with_kwargs(cls_add_request, kwargs)
            cls_add_request = self._validate_input_new(
                cls_add_request, session["force"]
            )
            operation_params = cls_add_request

            step = "filling cluster details from input data"
            cls_add_request = self._add_cluster(
                cls_add_request, rollback, session, indata, kwargs, headers
            )

            step = "registering the cluster at database"
            self.format_on_new(
                cls_add_request, session["project_id"], make_public=session["public"]
            )
            op_id = self.format_on_operation(
                cls_add_request,
                "register",
                operation_params,
            )
            _id = self.db.create(self.topic, cls_add_request)
            pubkey, privkey = self._generate_age_key()
            cls_add_request["age_pubkey"] = self.db.encrypt(
                pubkey, schema_version="1.11", salt=_id
            )
            cls_add_request["age_privkey"] = self.db.encrypt(
                privkey, schema_version="1.11", salt=_id
            )
            # TODO: set age_pubkey and age_privkey in the default profiles
            self.db.set_one(self.topic, {"_id": _id}, cls_add_request)
            rollback.append({"topic": self.topic, "_id": _id})
            self._send_msg("register", {"cluster_id": _id, "operation_id": op_id})

            # To add the content in old collection "k8sclusters"
            self.add_to_old_collection(cls_add_request, session)

            return _id, None
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _add_cluster(self, cls_add_request, rollback, session, indata, kwargs, headers):
        cls_add = {
            "name": cls_add_request["name"],
            "credentials": cls_add_request["credentials"],
            "vim_account": cls_add_request["vim_account"],
            "bootstrap": cls_add_request["bootstrap"],
            "openshift": cls_add_request.get("openshift", False),
            "infra_controller_profiles": [
                self._create_default_profiles(
                    rollback, session, indata, kwargs, headers, self.infra_contr_topic
                )
            ],
            "infra_config_profiles": [
                self._create_default_profiles(
                    rollback, session, indata, kwargs, headers, self.infra_conf_topic
                )
            ],
            "resource_profiles": [
                self._create_default_profiles(
                    rollback, session, indata, kwargs, headers, self.resource_topic
                )
            ],
            "app_profiles": [
                self._create_default_profiles(
                    rollback, session, indata, kwargs, headers, self.app_topic
                )
            ],
            "created": "false",
            "state": "IN_CREATION",
            "operatingState": "PROCESSING",
            "git_name": self.create_gitname(cls_add_request, session),
            "resourceState": "IN_PROGRESS.REQUEST_RECEIVED",
        }
        # Add optional fields if they exist in the request
        if "description" in cls_add_request:
            cls_add["description"] = cls_add_request["description"]
        return cls_add

    def check_vim(self, session, name):
        try:
            vim_account_details = self.db.get_one("vim_accounts", {"name": name})
            if vim_account_details is not None:
                return name
        except ValidationError as e:
            raise EngineException(
                e,
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    def _create_default_profiles(
        self, rollback, session, indata, kwargs, headers, topic
    ):
        topic = self.to_select_topic(topic)
        default_profiles = topic.default(rollback, session, indata, kwargs, headers)
        return default_profiles

    def to_select_topic(self, topic):
        if topic == "infra_controller_profiles":
            topic = self.infra_contr_topic
        elif topic == "infra_config_profiles":
            topic = self.infra_conf_topic
        elif topic == "resource_profiles":
            topic = self.resource_topic
        elif topic == "app_profiles":
            topic = self.app_topic
        return topic

    def remove(self, session, _id, dry_run=False, not_send_msg=None):
        """
        Delete item by its internal _id
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param dry_run: make checking but do not delete
        :param not_send_msg: To not send message (False) or store content (list) instead
        :return: operation id (None if there is not operation), raise exception if error or not found, conflict, ...
        """

        # To allow addressing projects and users by name AS WELL AS by _id
        if not self.multiproject:
            filter_q = {}
        else:
            filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        item_content = self.db.get_one(self.topic, filter_q)

        op_id = self.format_on_operation(
            item_content,
            "deregister",
            None,
        )
        self.db.set_one(self.topic, {"_id": _id}, item_content)

        self.check_conflict_on_del(session, _id, item_content)
        if dry_run:
            return None

        if self.multiproject and session["project_id"]:
            # remove reference from project_read if there are more projects referencing it. If it last one,
            # do not remove reference, but delete
            other_projects_referencing = next(
                (
                    p
                    for p in item_content["_admin"]["projects_read"]
                    if p not in session["project_id"] and p != "ANY"
                ),
                None,
            )

            # check if there are projects referencing it (apart from ANY, that means, public)....
            if other_projects_referencing:
                # remove references but not delete
                update_dict_pull = {
                    "_admin.projects_read": session["project_id"],
                    "_admin.projects_write": session["project_id"],
                }
                self.db.set_one(
                    self.topic, filter_q, update_dict=None, pull_list=update_dict_pull
                )
                return None
            else:
                can_write = next(
                    (
                        p
                        for p in item_content["_admin"]["projects_write"]
                        if p == "ANY" or p in session["project_id"]
                    ),
                    None,
                )
                if not can_write:
                    raise EngineException(
                        "You have not write permission to delete it",
                        http_code=HTTPStatus.UNAUTHORIZED,
                    )

        # delete
        self._send_msg(
            "deregister",
            {"cluster_id": _id, "operation_id": op_id},
            not_send_msg=not_send_msg,
        )
        return _id


class KsusTopic(ACMTopic):
    topic = "ksus"
    okapkg_topic = "okas"
    topic_msg = "ksu"
    schema_new = ksu_schema
    schema_edit = ksu_schema
    MAP_PROFILE = {
        "infra_controller_profiles": "infra-controllers",
        "infra_config_profiles": "infra-configs",
        "resource_profiles": "managed_resources",
        "app_profiles": "apps",
    }

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        self.logger = logging.getLogger("nbi.ksus")

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["current_operation"] = None
        content["state"] = "IN_CREATION"
        content["operatingState"] = "PROCESSING"
        content["resourceState"] = "IN_PROGRESS"

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        _id_list = []
        for content in indata["ksus"]:
            check_dict = {content["profile"]["profile_type"]: content["profile"]["_id"]}
            check_dict["okas"] = []

            for okas in content["oka"]:
                if "_id" in okas and "sw_catalog_path" in okas:
                    raise EngineException(
                        "Cannot create ksu with both OKA and SW catalog path",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                elif "_id" not in okas and "sw_catalog_path" not in okas:
                    raise EngineException(
                        "Cannot create ksu. Either oka id or SW catalog path is required for all OKA in a KSU",
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                elif "_id" in okas:
                    check_dict["okas"].append(okas["_id"])
            self.check_dependency(check_dict)

            # Override descriptor with query string kwargs
            content = self._remove_envelop(content)
            self._update_input_with_kwargs(content, kwargs)
            content = self._validate_input_new(input=content, force=session["force"])

            # Check for unique name
            self.check_unique_name(session, content["name"])

            self.check_conflict_on_new(session, content)

            operation_params = {}
            for content_key, content_value in content.items():
                operation_params[content_key] = content_value
            self.format_on_new(
                content, project_id=session["project_id"], make_public=session["public"]
            )
            op_id = self.format_on_operation(
                content,
                operation_type="create",
                operation_params=operation_params,
            )
            content["git_name"] = self.create_gitname(content, session)

            # Update Oka_package usage state
            for okas in content["oka"]:
                if "_id" in okas.keys():
                    self.update_usage_state(session, okas)

            profile_id = content["profile"].get("_id")
            profile_type = content["profile"].get("profile_type")
            db_cluster_list = self.db.get_list("clusters")
            for db_cluster in db_cluster_list:
                if db_cluster.get("created") == "true":
                    profile_list = db_cluster[profile_type]
                    if profile_id in profile_list:
                        ksu_count = db_cluster.get("ksu_count")
                        new_ksu_count = ksu_count + 1
                        self.logger.info(f"New KSU count: {new_ksu_count}")
                        db_cluster["ksu_count"] = new_ksu_count
                        self.db.set_one(
                            "clusters", {"_id": db_cluster["_id"]}, db_cluster
                        )

            _id = self.db.create(self.topic, content)
            rollback.append({"topic": self.topic, "_id": _id})
            _id_list.append(_id)
        data = {"ksus_list": _id_list, "operation_id": op_id}
        self._send_msg("create", data)
        return _id_list, op_id

    def clone(self, rollback, session, _id, indata, kwargs, headers):
        check_dict = {
            "ksu": _id,
            indata["profile"]["profile_type"]: indata["profile"]["_id"],
        }
        self.check_dependency(check_dict)
        filter_db = self._get_project_filter(session)
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id
        data = self.db.get_one(self.topic, filter_db)

        op_id = self.format_on_operation(
            data,
            "clone",
            indata,
        )
        self.db.set_one(self.topic, {"_id": data["_id"]}, data)
        self._send_msg("clone", {"ksus_list": [data["_id"]], "operation_id": op_id})
        return op_id

    def update_usage_state(self, session, oka_content):
        _id = oka_content["_id"]
        filter_db = self._get_project_filter(session)
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id

        data = self.db.get_one(self.okapkg_topic, filter_db)
        if data["_admin"]["usageState"] == "NOT_IN_USE":
            usage_state_update = {
                "_admin.usageState": "IN_USE",
            }
            self.db.set_one(
                self.okapkg_topic, {"_id": _id}, update_dict=usage_state_update
            )

    def move_ksu(self, session, _id, indata=None, kwargs=None, content=None):
        check_dict = {
            "ksu": _id,
            indata["profile"]["profile_type"]: indata["profile"]["_id"],
        }
        self.check_dependency(check_dict)
        indata = self._remove_envelop(indata)

        # Override descriptor with query string kwargs
        if kwargs:
            self._update_input_with_kwargs(indata, kwargs)
        try:
            if indata and session.get("set_project"):
                raise EngineException(
                    "Cannot edit content and set to project (query string SET_PROJECT) at same time",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            # TODO self._check_edition(session, indata, _id, force)
            if not content:
                content = self.show(session, _id)
            indata = self._validate_input_edit(
                input=indata, content=content, force=session["force"]
            )
            operation_params = indata
            deep_update_rfc7396(content, indata)

            # To allow project addressing by name AS WELL AS _id. Get the _id, just in case the provided one is a name
            _id = content.get("_id") or _id
            op_id = self.format_on_operation(
                content,
                "move",
                operation_params,
            )
            if content.get("_admin"):
                now = time()
                content["_admin"]["modified"] = now
            content["operatingState"] = "PROCESSING"
            content["resourceState"] = "IN_PROGRESS"

            self.db.replace(self.topic, _id, content)
            data = {"ksus_list": [content["_id"]], "operation_id": op_id}
            self._send_msg("move", data)
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        if final_content["name"] != edit_content["name"]:
            self.check_unique_name(session, edit_content["name"])
        return final_content

    @staticmethod
    def format_on_edit(final_content, edit_content):
        op_id = ACMTopic.format_on_operation(
            final_content,
            "update",
            edit_content,
        )
        final_content["operatingState"] = "PROCESSING"
        final_content["resourceState"] = "IN_PROGRESS"
        if final_content.get("_admin"):
            now = time()
            final_content["_admin"]["modified"] = now
        return op_id

    def edit(self, session, _id, indata, kwargs):
        _id_list = []
        if _id == "update":
            for ksus in indata["ksus"]:
                content = ksus
                _id = content["_id"]
                _id_list.append(_id)
                content.pop("_id")
                op_id = self.edit_ksu(session, _id, content, kwargs)
        else:
            content = indata
            _id_list.append(_id)
            op_id = self.edit_ksu(session, _id, content, kwargs)

        data = {"ksus_list": _id_list, "operation_id": op_id}
        self._send_msg("edit", data)

    def cluster_list_ksu(self, session, filter_q=None, api_req=None):
        db_filter = {}
        if filter_q.get("cluster_id"):
            db_filter["_id"] = filter_q.get("cluster_id")
        ksu_data_list = []

        cluster_data = self.db.get_one("clusters", db_filter)
        profiles_list = [
            "infra_controller_profiles",
            "infra_config_profiles",
            "app_profiles",
            "resource_profiles",
        ]
        for profile in profiles_list:
            data_list = []
            for profile_id in cluster_data[profile]:
                filter_q = {"profile": {"_id": profile_id, "profile_type": profile}}
                data_list = self.db.get_list(self.topic, filter_q)
            for ksu_data in data_list:
                ksu_data["package_name"] = []
                ksu_data["package_path"] = []
                for okas in ksu_data["operationHistory"][0]["operationParams"]["oka"]:
                    sw_catalog_path = okas.get("sw_catalog_path")
                    if sw_catalog_path:
                        parts = sw_catalog_path.rsplit("/", 2)
                        self.logger.info(f"Parts: {parts}")
                        ksu_data["package_name"].append(parts[-2])
                        ksu_data["package_path"].append("/".join(parts[:-1]))
                    else:
                        oka_id = okas["_id"]
                        db_oka = self.db.get_one("okas", {"_id": oka_id})
                        oka_type = self.MAP_PROFILE[
                            db_oka.get("profile_type", "infra_controller_profiles")
                        ]
                        ksu_data["package_name"].append(db_oka["git_name"].lower())
                        ksu_data["package_path"].append(
                            f"{oka_type}/{db_oka['git_name'].lower()}"
                        )
                ksu_data_list.append(ksu_data)

        outdata = {}
        outdata["count"] = cluster_data["ksu_count"]
        outdata["data"] = ksu_data_list
        self.logger.info(f"Outdata: {outdata}")
        return outdata

    def edit_ksu(self, session, _id, indata, kwargs):
        check_dict = {
            "ksu": _id,
        }
        if indata.get("profile"):
            check_dict[indata["profile"]["profile_type"]] = indata["profile"]["_id"]
        if indata.get("oka"):
            check_dict["okas"] = []
            for oka in indata["oka"]:
                if oka.get("_id") is not None:
                    check_dict["okas"].append(oka["_id"])

        self.check_dependency(check_dict)
        content = None
        indata = self._remove_envelop(indata)

        # Override descriptor with query string kwargs
        if kwargs:
            self._update_input_with_kwargs(indata, kwargs)
        try:
            if indata and session.get("set_project"):
                raise EngineException(
                    "Cannot edit content and set to project (query string SET_PROJECT) at same time",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            # TODO self._check_edition(session, indata, _id, force)
            if not content:
                content = self.show(session, _id)

            for okas in indata["oka"]:
                if not okas["_id"]:
                    okas.pop("_id")
                if not okas["sw_catalog_path"]:
                    okas.pop("sw_catalog_path")

            indata = self._validate_input_edit(indata, content, force=session["force"])

            # To allow project addressing by name AS WELL AS _id. Get the _id, just in case the provided one is a name
            _id = content.get("_id") or _id

            content = self.check_conflict_on_edit(session, content, indata, _id=_id)
            op_id = self.format_on_edit(content, indata)
            self.db.replace(self.topic, _id, content)
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def delete_ksu(self, session, _id, indata, dry_run=False, not_send_msg=None):
        _id_list = []
        if _id == "delete":
            for ksus in indata["ksus"]:
                content = ksus
                _id = content["_id"]
                content.pop("_id")
                op_id, not_send_msg_ksu = self.delete(session, _id)
                if not not_send_msg_ksu:
                    _id_list.append(_id)
        else:
            op_id, not_send_msg_ksu = self.delete(session, _id)
            if not not_send_msg_ksu:
                _id_list.append(_id)

        if _id_list:
            data = {
                "ksus_list": _id_list,
                "operation_id": op_id,
                "force": session["force"],
            }
            self._send_msg("delete", data, not_send_msg)
        return op_id

    def delete(self, session, _id):
        if not self.multiproject:
            filter_q = {}
        else:
            filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        item_content = self.db.get_one(self.topic, filter_q)

        check = {
            "ksu": _id,
            item_content["profile"]["profile_type"]: item_content["profile"]["_id"],
        }
        self.check_dependency(check, operation_type="delete")

        item_content["state"] = "IN_DELETION"
        item_content["operatingState"] = "PROCESSING"
        item_content["resourceState"] = "IN_PROGRESS"
        op_id = self.format_on_operation(
            item_content,
            "delete",
            None,
        )
        self.db.set_one(self.topic, {"_id": item_content["_id"]}, item_content)

        # Check if the profile exists. If it doesn't, no message should be sent to Kafka
        not_send_msg = None
        profile_id = item_content["profile"]["_id"]
        profile_type = item_content["profile"]["profile_type"]
        profile_collection_map = {
            "app_profiles": "k8sapp",
            "resource_profiles": "k8sresource",
            "infra_controller_profiles": "k8sinfra_controller",
            "infra_config_profiles": "k8sinfra_config",
        }
        profile_collection = profile_collection_map[profile_type]
        profile_content = self.db.get_one(
            profile_collection, {"_id": profile_id}, fail_on_empty=False
        )
        if not profile_content:
            self.db.del_one(self.topic, filter_q)
            not_send_msg = True
        return op_id, not_send_msg


class AppInstanceTopic(ACMTopic):
    topic = "appinstances"
    okapkg_topic = "okas"
    topic_msg = "appinstance"
    schema_new = app_instance_schema
    schema_edit = app_instance_edit_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        self.logger = logging.getLogger("nbi.appinstances")

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["current_operation"] = None
        content["state"] = "IN_CREATION"
        content["operatingState"] = "PROCESSING"
        content["resourceState"] = "IN_PROGRESS"

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        if indata.get("oka") and indata.get("sw_catalog_path"):
            raise EngineException(
                "Cannot create app instance with both OKA and SW catalog path",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        # Override descriptor with query string kwargs
        content = self._remove_envelop(indata)
        self._update_input_with_kwargs(content, kwargs)
        content = self._validate_input_new(input=content, force=session["force"])

        # Check for unique name
        self.check_unique_name(session, content["name"])

        self.check_conflict_on_new(session, content)

        operation_params = {}
        for content_key, content_value in content.items():
            operation_params[content_key] = content_value
        self.format_on_new(
            content, project_id=session["project_id"], make_public=session["public"]
        )
        op_id = self.format_on_operation(
            content,
            operation_type="create",
            operation_params=operation_params,
        )
        content["git_name"] = self.create_gitname(content, session)

        oka_id = content.get("oka")
        if oka_id:
            self.update_oka_usage_state(session, oka_id)

        _id = self.db.create(self.topic, content)
        rollback.append({"topic": self.topic, "_id": _id})
        self._send_msg("create", {"appinstance": _id, "operation_id": op_id})
        return _id, op_id

    def update_oka_usage_state(self, session, oka_id):
        filter_db = self._get_project_filter(session)
        filter_db[BaseTopic.id_field(self.topic, oka_id)] = oka_id

        data = self.db.get_one(self.okapkg_topic, filter_db)
        if data["_admin"]["usageState"] == "NOT_IN_USE":
            usage_state_update = {
                "_admin.usageState": "IN_USE",
            }
            self.db.set_one(
                self.okapkg_topic, {"_id": oka_id}, update_dict=usage_state_update
            )

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        if final_content["name"] != edit_content["name"]:
            self.check_unique_name(session, edit_content["name"])
        return final_content

    @staticmethod
    def format_on_edit(final_content, edit_content):
        op_id = ACMTopic.format_on_operation(
            final_content,
            "update",
            edit_content,
        )
        final_content["operatingState"] = "PROCESSING"
        final_content["resourceState"] = "IN_PROGRESS"
        if final_content.get("_admin"):
            now = time()
            final_content["_admin"]["modified"] = now
        return op_id

    def edit(self, session, _id, indata, kwargs):
        content = None
        indata = self._remove_envelop(indata)

        # Override descriptor with query string kwargs
        if kwargs:
            self._update_input_with_kwargs(indata, kwargs)
        try:
            if indata and session.get("set_project"):
                raise EngineException(
                    "Cannot edit content and set to project (query string SET_PROJECT) at same time",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            # TODO self._check_edition(session, indata, _id, force)
            if not content:
                content = self.show(session, _id)

            indata = self._validate_input_edit(indata, content, force=session["force"])

            # To allow project addressing by name AS WELL AS _id. Get the _id, just in case the provided one is a name
            _id = content.get("_id") or _id

            content = self.check_conflict_on_edit(session, content, indata, _id=_id)
            op_id = self.format_on_edit(content, indata)
            self.db.replace(self.topic, _id, content)
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def update_item(self, session, _id, item, indata):
        if not self.multiproject:
            filter_db = {}
        else:
            filter_db = self._get_project_filter(session)
        # To allow project&user addressing by name AS WELL AS _id
        filter_db[BaseTopic.id_field(self.topic, _id)] = _id
        self.logger.info(f"Item: {item}")
        self.logger.info(f"Indata before validation: {indata}")
        validate_input(indata, app_instance_update_schema)
        self.logger.info(f"Indata after validation: {indata}")
        data = self.db.get_one(self.topic, filter_db)
        operation_params = {}
        data["operatingState"] = "PROCESSING"
        data["resourceState"] = "IN_PROGRESS"
        operation_params = indata
        self.logger.info(f"Operation params: {operation_params}")
        op_id = self.format_on_operation(
            data,
            "update",
            operation_params,
        )
        self.db.set_one(self.topic, {"_id": _id}, data)
        self._send_msg("update", {"appinstance": _id, "operation_id": op_id})
        return op_id

    def delete(self, session, _id, not_send_msg=None):
        if not self.multiproject:
            filter_q = {}
        else:
            filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        item_content = self.db.get_one(self.topic, filter_q)
        item_content["state"] = "IN_DELETION"
        item_content["operatingState"] = "PROCESSING"
        item_content["resourceState"] = "IN_PROGRESS"
        op_id = self.format_on_operation(
            item_content,
            "delete",
            None,
        )
        self.db.set_one(self.topic, {"_id": item_content["_id"]}, item_content)

        # Check if the profile exists. If it doesn't, no message should be sent to Kafka
        not_send_msg2 = not_send_msg
        profile_id = item_content["profile"]
        profile_type = item_content["profile_type"]
        profile_collection_map = {
            "app_profiles": "k8sapp",
            "resource_profiles": "k8sresource",
            "infra_controller_profiles": "k8sinfra_controller",
            "infra_config_profiles": "k8sinfra_config",
        }
        profile_collection = profile_collection_map[profile_type]
        profile_content = self.db.get_one(
            profile_collection, {"_id": profile_id}, fail_on_empty=False
        )
        if not profile_content:
            self.db.del_one(self.topic, filter_q)
            not_send_msg2 = True
        self._send_msg(
            "delete",
            {"appinstance": _id, "operation_id": op_id, "force": session["force"]},
            not_send_msg=not_send_msg2,
        )
        return op_id


class OkaTopic(DescriptorTopic, ACMOperationTopic):
    topic = "okas"
    topic_msg = "oka"
    schema_new = oka_schema
    schema_edit = oka_schema

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)
        self.logger = logging.getLogger("nbi.oka")

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        DescriptorTopic.format_on_new(
            content, project_id=project_id, make_public=make_public
        )
        content["current_operation"] = None
        content["state"] = "PENDING_CONTENT"
        content["operatingState"] = "PROCESSING"
        content["resourceState"] = "IN_PROGRESS"

    def check_conflict_on_del(self, session, _id, db_content):
        usage_state = db_content["_admin"]["usageState"]
        if usage_state == "IN_USE":
            raise EngineException(
                "There is a KSU using this package",
                http_code=HTTPStatus.CONFLICT,
            )

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        if "name" in edit_content:
            if final_content["name"] == edit_content["name"]:
                name = edit_content["name"]
                raise EngineException(
                    f"No update, new name for the OKA is the same: {name}",
                    http_code=HTTPStatus.CONFLICT,
                )
            else:
                self.check_unique_name(session, edit_content["name"])
        elif (
            "description" in edit_content
            and final_content["description"] == edit_content["description"]
        ):
            description = edit_content["description"]
            raise EngineException(
                f"No update, new description for the OKA is the same: {description}",
                http_code=HTTPStatus.CONFLICT,
            )
        return final_content

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        indata = self._remove_envelop(indata)

        # Override descriptor with query string kwargs
        if kwargs:
            self._update_input_with_kwargs(indata, kwargs)
        try:
            if indata and session.get("set_project"):
                raise EngineException(
                    "Cannot edit content and set to project (query string SET_PROJECT) at same time",
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            # TODO self._check_edition(session, indata, _id, force)
            if not content:
                content = self.show(session, _id)

            indata = self._validate_input_edit(indata, content, force=session["force"])

            # To allow project addressing by name AS WELL AS _id. Get the _id, just in case the provided one is a name
            _id = content.get("_id") or _id

            content = self.check_conflict_on_edit(session, content, indata, _id=_id)
            op_id = self.format_on_edit(content, indata)
            deep_update_rfc7396(content, indata)

            self.db.replace(self.topic, _id, content)
            return op_id
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        check = {"oka": _id}
        self.check_dependency(check, operation_type="delete")
        if not self.multiproject:
            filter_q = {}
        else:
            filter_q = self._get_project_filter(session)
        filter_q[self.id_field(self.topic, _id)] = _id
        item_content = self.db.get_one(self.topic, filter_q)
        item_content["state"] = "IN_DELETION"
        item_content["operatingState"] = "PROCESSING"
        self.check_conflict_on_del(session, _id, item_content)
        op_id = self.format_on_operation(
            item_content,
            "delete",
            None,
        )
        self.db.set_one(self.topic, {"_id": item_content["_id"]}, item_content)
        self._send_msg(
            "delete",
            {"oka_id": _id, "operation_id": op_id, "force": session["force"]},
            not_send_msg=not_send_msg,
        )
        return op_id

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # _remove_envelop
        if indata:
            if "userDefinedData" in indata:
                indata = indata["userDefinedData"]

        content = {"_admin": {"userDefinedData": indata, "revision": 0}}

        self._update_input_with_kwargs(content, kwargs)
        content = BaseTopic._validate_input_new(
            self, input=kwargs, force=session["force"]
        )

        self.check_unique_name(session, content["name"])
        operation_params = {}
        for content_key, content_value in content.items():
            operation_params[content_key] = content_value
        self.format_on_new(
            content, session["project_id"], make_public=session["public"]
        )
        op_id = self.format_on_operation(
            content,
            operation_type="create",
            operation_params=operation_params,
        )
        content["git_name"] = self.create_gitname(content, session)
        _id = self.db.create(self.topic, content)
        rollback.append({"topic": self.topic, "_id": _id})
        return _id, op_id

    def upload_content(self, session, _id, indata, kwargs, headers):
        if headers["Method"] in ("PUT", "PATCH"):
            check = {"oka": _id}
            self.check_dependency(check)
        current_desc = self.show(session, _id)

        compressed = None
        content_type = headers.get("Content-Type")
        if (
            content_type
            and "application/gzip" in content_type
            or "application/x-gzip" in content_type
        ):
            compressed = "gzip"
        if content_type and "application/zip" in content_type:
            compressed = "zip"
        filename = headers.get("Content-Filename")
        if not filename and compressed:
            filename = "package.tar.gz" if compressed == "gzip" else "package.zip"
        elif not filename:
            filename = "package"

        revision = 1
        if "revision" in current_desc["_admin"]:
            revision = current_desc["_admin"]["revision"] + 1

        file_pkg = None
        fs_rollback = []

        try:
            start = 0
            # Rather than using a temp folder, we will store the package in a folder based on
            # the current revision.
            proposed_revision_path = _id + ":" + str(revision)
            # all the content is upload here and if ok, it is rename from id_ to is folder

            if start:
                if not self.fs.file_exists(proposed_revision_path, "dir"):
                    raise EngineException(
                        "invalid Transaction-Id header", HTTPStatus.NOT_FOUND
                    )
            else:
                self.fs.file_delete(proposed_revision_path, ignore_non_exist=True)
                self.fs.mkdir(proposed_revision_path)
                fs_rollback.append(proposed_revision_path)

            storage = self.fs.get_params()
            storage["folder"] = proposed_revision_path
            storage["zipfile"] = filename

            file_path = (proposed_revision_path, filename)
            file_pkg = self.fs.file_open(file_path, "a+b")

            if isinstance(indata, dict):
                indata_text = yaml.safe_dump(indata, indent=4, default_flow_style=False)
                file_pkg.write(indata_text.encode(encoding="utf-8"))
            else:
                indata_len = 0
                indata = indata.file
                while True:
                    indata_text = indata.read(4096)
                    indata_len += len(indata_text)
                    if not indata_text:
                        break
                    file_pkg.write(indata_text)

            # Need to close the file package here so it can be copied from the
            # revision to the current, unrevisioned record
            if file_pkg:
                file_pkg.close()
            file_pkg = None

            # Fetch both the incoming, proposed revision and the original revision so we
            # can call a validate method to compare them
            current_revision_path = _id + "/"
            self.fs.sync(from_path=current_revision_path)
            self.fs.sync(from_path=proposed_revision_path)

            # Is this required?
            if revision > 1:
                try:
                    self._validate_descriptor_changes(
                        _id,
                        filename,
                        current_revision_path,
                        proposed_revision_path,
                    )
                except Exception as e:
                    shutil.rmtree(
                        self.fs.path + current_revision_path, ignore_errors=True
                    )
                    shutil.rmtree(
                        self.fs.path + proposed_revision_path, ignore_errors=True
                    )
                    # Only delete the new revision.  We need to keep the original version in place
                    # as it has not been changed.
                    self.fs.file_delete(proposed_revision_path, ignore_non_exist=True)
                    raise e

            indata = self._remove_envelop(indata)

            # Override descriptor with query string kwargs
            if kwargs:
                self._update_input_with_kwargs(indata, kwargs)

            current_desc["_admin"]["storage"] = storage
            current_desc["_admin"]["onboardingState"] = "ONBOARDED"
            current_desc["_admin"]["operationalState"] = "ENABLED"
            current_desc["_admin"]["modified"] = time()
            current_desc["_admin"]["revision"] = revision

            deep_update_rfc7396(current_desc, indata)

            # Copy the revision to the active package name by its original id
            shutil.rmtree(self.fs.path + current_revision_path, ignore_errors=True)
            os.rename(
                self.fs.path + proposed_revision_path,
                self.fs.path + current_revision_path,
            )
            self.fs.file_delete(current_revision_path, ignore_non_exist=True)
            self.fs.mkdir(current_revision_path)
            self.fs.reverse_sync(from_path=current_revision_path)

            shutil.rmtree(self.fs.path + _id)
            kwargs = {}
            kwargs["package"] = filename
            if headers["Method"] == "POST":
                current_desc["state"] = "IN_CREATION"
                op_id = current_desc.get("operationHistory", [{"op_id": None}])[-1].get(
                    "op_id"
                )
            elif headers["Method"] in ("PUT", "PATCH"):
                op_id = self.format_on_operation(
                    current_desc,
                    "update",
                    kwargs,
                )
                current_desc["operatingState"] = "PROCESSING"
                current_desc["resourceState"] = "IN_PROGRESS"

            self.db.replace(self.topic, _id, current_desc)

            #  Store a copy of the package as a point in time revision
            revision_desc = dict(current_desc)
            revision_desc["_id"] = _id + ":" + str(revision_desc["_admin"]["revision"])
            self.db.create(self.topic + "_revisions", revision_desc)
            fs_rollback = []

            if headers["Method"] == "POST":
                self._send_msg("create", {"oka_id": _id, "operation_id": op_id})
            elif headers["Method"] == "PUT" or "PATCH":
                self._send_msg("edit", {"oka_id": _id, "operation_id": op_id})

            return True

        except EngineException:
            raise
        finally:
            if file_pkg:
                file_pkg.close()
            for file in fs_rollback:
                self.fs.file_delete(file, ignore_non_exist=True)
