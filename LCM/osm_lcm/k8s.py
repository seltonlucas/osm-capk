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

__author__ = (
    "Shrinithi R <shrinithi.r@tataelxsi.co.in>",
    "Shahithya Y <shahithya.y@tataelxsi.co.in>",
)

import os
from time import time
import traceback
import yaml
from copy import deepcopy
from osm_lcm import vim_sdn
from osm_lcm.gitops import GitOpsLcm
from osm_lcm.lcm_utils import LcmException

MAP_PROFILE = {
    "infra_controller_profiles": "infra-controllers",
    "infra_config_profiles": "infra-configs",
    "resource_profiles": "managed_resources",
    "app_profiles": "apps",
}


class NodeGroupLcm(GitOpsLcm):
    db_collection = "nodegroups"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)
        self._workflows = {
            "add_nodegroup": {
                "check_resource_function": self.check_add_nodegroup,
            },
            "scale_nodegroup": {
                "check_resource_function": self.check_scale_nodegroup,
            },
            "delete_nodegroup": {
                "check_resource_function": self.check_delete_nodegroup,
            },
        }

    async def create(self, params, order_id):
        self.logger.info("Add NodeGroup Enter")

        # To get the nodegroup and op ids
        nodegroup_id = params["nodegroup_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(nodegroup_id, op_id)

        # To get the nodegroup details and control plane from DB
        db_nodegroup = self.db.get_one(self.db_collection, {"_id": nodegroup_id})
        db_cluster = self.db.get_one("clusters", {"_id": db_nodegroup["cluster_id"]})

        # To get the operation params details
        op_params = self.get_operation_params(db_nodegroup, op_id)
        self.logger.info(f"Operations Params: {op_params}")

        db_vim = self.db.get_one("vim_accounts", {"name": db_cluster["vim_account"]})

        # To copy the cluster content and decrypting fields to use in workflows
        workflow_content = {
            "nodegroup": db_nodegroup,
            "cluster": db_cluster,
            "vim_account": db_vim,
        }
        self.logger.info(f"Workflow content: {workflow_content}")

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "add_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_nodegroup
        )

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "add_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "add_nodegroup", op_id, op_params, db_nodegroup
            )
        self.db.set_one(self.db_collection, {"_id": db_nodegroup["_id"]}, db_nodegroup)
        self.logger.info(f"Add NodeGroup Exit with resource status: {resource_status}")
        return

    async def check_add_nodegroup(self, op_id, op_params, content):
        self.logger.info(f"check_add_nodegroup Operation {op_id}. Params: {op_params}.")
        self.logger.info(f"Content: {content}")
        db_nodegroup = content
        nodegroup_name = db_nodegroup["git_name"].lower()
        nodegroup_kustomization_name = nodegroup_name
        checkings_list = [
            {
                "item": "kustomization",
                "name": nodegroup_kustomization_name,
                "namespace": "managed-resources",
                "condition": {
                    "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                    "value": "True",
                },
                "timeout": self._checkloop_kustomization_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
            },
            {
                "item": "nodegroup_aws",
                "name": nodegroup_name,
                "namespace": "",
                "condition": {
                    "jsonpath_filter": "status.conditions[?(@.type=='Synced')].status",
                    "value": "True",
                },
                "timeout": self._checkloop_resource_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.RESOURCE_SYNCED.NODEGROUP",
            },
            {
                "item": "nodegroup_aws",
                "name": nodegroup_name,
                "namespace": "",
                "condition": {
                    "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                    "value": "True",
                },
                "timeout": self._checkloop_resource_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.RESOURCE_READY.NODEGROUP",
            },
        ]
        self.logger.info(f"Checking list: {checkings_list}")
        result, message = await self.common_check_list(
            op_id, checkings_list, "nodegroups", db_nodegroup
        )
        if not result:
            return False, message
        return True, "OK"

    async def scale(self, params, order_id):
        self.logger.info("Scale nodegroup Enter")

        op_id = params["operation_id"]
        nodegroup_id = params["nodegroup_id"]

        # To initialize the operation states
        self.initialize_operation(nodegroup_id, op_id)

        db_nodegroup = self.db.get_one(self.db_collection, {"_id": nodegroup_id})
        db_cluster = self.db.get_one("clusters", {"_id": db_nodegroup["cluster_id"]})
        op_params = self.get_operation_params(db_nodegroup, op_id)
        db_vim = self.db.get_one("vim_accounts", {"name": db_cluster["vim_account"]})

        workflow_content = {
            "nodegroup": db_nodegroup,
            "cluster": db_cluster,
            "vim_account": db_vim,
        }
        self.logger.info(f"Workflow content: {workflow_content}")

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "scale_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_nodegroup
        )

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "scale_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "scale_nodegroup", op_id, op_params, db_nodegroup
            )

        if resource_status:
            db_nodegroup["state"] = "READY"
            self.db.set_one(
                self.db_collection, {"_id": db_nodegroup["_id"]}, db_nodegroup
            )
        self.logger.info(
            f"Nodegroup Scale Exit with resource status: {resource_status}"
        )
        return

    async def check_scale_nodegroup(self, op_id, op_params, content):
        self.logger.info(
            f"check_scale_nodegroup Operation {op_id}. Params: {op_params}."
        )
        self.logger.debug(f"Content: {content}")
        db_nodegroup = content
        nodegroup_name = db_nodegroup["git_name"].lower()
        nodegroup_kustomization_name = nodegroup_name
        checkings_list = [
            {
                "item": "kustomization",
                "name": nodegroup_kustomization_name,
                "namespace": "managed-resources",
                "condition": {
                    "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                    "value": "True",
                },
                "timeout": self._checkloop_kustomization_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
            },
            {
                "item": "nodegroup_aws",
                "name": nodegroup_name,
                "namespace": "",
                "condition": {
                    "jsonpath_filter": "status.atProvider.scalingConfig[0].desiredSize",
                    "value": f"{op_params['node_count']}",
                },
                "timeout": self._checkloop_resource_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.RESOURCE_SYNCED.NODEGROUP",
            },
        ]
        self.logger.info(f"Checking list: {checkings_list}")
        return await self.common_check_list(
            op_id, checkings_list, "nodegroups", db_nodegroup
        )

    async def delete(self, params, order_id):
        self.logger.info("Delete nodegroup Enter")

        op_id = params["operation_id"]
        nodegroup_id = params["nodegroup_id"]

        # To initialize the operation states
        self.initialize_operation(nodegroup_id, op_id)

        db_nodegroup = self.db.get_one(self.db_collection, {"_id": nodegroup_id})
        db_cluster = self.db.get_one("clusters", {"_id": db_nodegroup["cluster_id"]})
        op_params = self.get_operation_params(db_nodegroup, op_id)

        workflow_content = {"nodegroup": db_nodegroup, "cluster": db_cluster}

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_nodegroup
        )

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "delete_nodegroup", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "delete_nodegroup", op_id, op_params, db_nodegroup
            )

        if resource_status:
            node_count = db_cluster.get("node_count")
            new_node_count = node_count - 1
            self.logger.info(f"New Node count: {new_node_count}")
            db_cluster["node_count"] = new_node_count
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            db_nodegroup["state"] = "DELETED"
            self.db.set_one(
                self.db_collection, {"_id": db_nodegroup["_id"]}, db_nodegroup
            )
            self.db.del_one(self.db_collection, {"_id": db_nodegroup["_id"]})
        self.logger.info(
            f"Nodegroup Delete Exit with resource status: {resource_status}"
        )
        return

    async def check_delete_nodegroup(self, op_id, op_params, content):
        self.logger.info(
            f"check_delete_nodegroup Operation {op_id}. Params: {op_params}."
        )
        db_nodegroup = content
        nodegroup_name = db_nodegroup["git_name"].lower()
        nodegroup_kustomization_name = nodegroup_name
        checkings_list = [
            {
                "item": "kustomization",
                "name": nodegroup_kustomization_name,
                "namespace": "managed-resources",
                "deleted": True,
                "timeout": self._checkloop_kustomization_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.KUSTOMIZATION_DELETED",
            },
            {
                "item": "nodegroup_aws",
                "name": nodegroup_name,
                "namespace": "",
                "deleted": True,
                "timeout": self._checkloop_resource_timeout,
                "enable": True,
                "resourceState": "IN_PROGRESS.RESOURCE_DELETED.NODEGROUP",
            },
        ]
        self.logger.info(f"Checking list: {checkings_list}")
        return await self.common_check_list(
            op_id, checkings_list, "nodegroups", db_nodegroup
        )


class ClusterLcm(GitOpsLcm):
    db_collection = "clusters"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)
        self._workflows = {
            "create_cluster": {
                "check_resource_function": self.check_create_cluster,
            },
            "register_cluster": {
                "check_resource_function": self.check_register_cluster,
            },
            "update_cluster": {
                "check_resource_function": self.check_update_cluster,
            },
            "delete_cluster": {
                "check_resource_function": self.check_delete_cluster,
            },
        }
        self.regist = vim_sdn.K8sClusterLcm(msg, self.lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("cluster Create Enter")
        workflow_status = None
        resource_status = None

        # To get the cluster and op ids
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(cluster_id, op_id)

        # To get the cluster
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        db_cluster_copy = self.decrypted_copy(db_cluster)
        workflow_content = {
            "cluster": db_cluster_copy,
        }

        # To get the vim account details
        db_vim = self.db.get_one("vim_accounts", {"name": db_cluster["vim_account"]})
        workflow_content["vim_account"] = db_vim

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["state"] = "FAILED_CREATION"
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            # Clean items used in the workflow, no matter if the workflow succeeded
            clean_status, clean_msg = await self.odu.clean_items_workflow(
                "create_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
            )
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["state"] = "CREATED"
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["state"] = "FAILED_CREATION"
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "create_cluster", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "create_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster["operatingState"] = "IDLE"
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        db_cluster["current_operation"] = None

        # Retrieve credentials and subnets and register the cluster in k8sclusters collection
        cluster_creds = None
        db_register = self.db.get_one("k8sclusters", {"name": db_cluster["name"]})
        if db_cluster["resourceState"] == "READY" and db_cluster["state"] == "CREATED":
            # Retrieve credentials
            result, cluster_creds = await self.odu.get_cluster_credentials(db_cluster)
            # TODO: manage the case where the credentials are not available
            if result:
                db_cluster["credentials"] = cluster_creds

            # Retrieve subnets
            if op_params.get("private_subnet") and op_params.get("public_subnet"):
                db_cluster["private_subnet"] = op_params["private_subnet"]
                db_cluster["public_subnet"] = op_params["public_subnet"]
            else:
                if db_vim["vim_type"] == "aws":
                    generic_object = await self.odu.list_object(
                        api_group="ec2.aws.upbound.io",
                        api_plural="subnets",
                        api_version="v1beta1",
                    )
                    private_subnet = []
                    public_subnet = []
                    for subnet in generic_object:
                        labels = subnet.get("metadata", {}).get("labels", {})
                        status = subnet.get("status", {}).get("atProvider", {})
                        # Extract relevant label values
                        cluster_label = labels.get("cluster")
                        access_label = labels.get("access")
                        subnet_id = status.get("id")
                        # Apply filtering
                        if cluster_label == db_cluster["name"] and subnet_id:
                            if access_label == "private":
                                private_subnet.append(subnet_id)
                            elif access_label == "public":
                                public_subnet.append(subnet_id)
                    # Update db_cluster
                    db_cluster["private_subnet"] = private_subnet
                    db_cluster["public_subnet"] = public_subnet
                    self.logger.info("DB cluster: {}".format(db_cluster))

            # Register the cluster in k8sclusters collection
            db_register["credentials"] = cluster_creds
            # To call the lcm.py for registering the cluster in k8scluster lcm.
            self.db.set_one("k8sclusters", {"_id": db_register["_id"]}, db_register)
            register = await self.regist.create(db_register, order_id)
            self.logger.debug(f"Register is : {register}")
        else:
            db_register["_admin"]["operationalState"] = "ERROR"
            self.db.set_one("k8sclusters", {"_id": db_register["_id"]}, db_register)

        # Update db_cluster
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
        self.update_default_profile_agekeys(db_cluster_copy)
        self.update_profile_state(db_cluster, workflow_status, resource_status)

        return

    async def check_create_cluster(self, op_id, op_params, content):
        self.logger.info(
            f"check_create_cluster Operation {op_id}. Params: {op_params}."
        )
        db_cluster = content["cluster"]
        cluster_name = db_cluster["git_name"].lower()
        cluster_kustomization_name = cluster_name
        db_vim_account = content["vim_account"]
        cloud_type = db_vim_account["vim_type"]
        nodegroup_name = ""
        if cloud_type == "aws":
            nodegroup_name = f"{cluster_name}-nodegroup"
            cluster_name = f"{cluster_name}-cluster"
        elif cloud_type == "gcp":
            nodegroup_name = f"nodepool-{cluster_name}"
        bootstrap = op_params.get("bootstrap", True)
        if cloud_type in ("azure", "gcp", "aws"):
            checkings_list = [
                {
                    "item": "kustomization",
                    "name": cluster_kustomization_name,
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": 1500,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
                },
                {
                    "item": f"cluster_{cloud_type}",
                    "name": cluster_name,
                    "namespace": "",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Synced')].status",
                        "value": "True",
                    },
                    "timeout": self._checkloop_resource_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.RESOURCE_SYNCED.CLUSTER",
                },
                {
                    "item": f"cluster_{cloud_type}",
                    "name": cluster_name,
                    "namespace": "",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": self._checkloop_resource_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.RESOURCE_READY.CLUSTER",
                },
                {
                    "item": "kustomization",
                    "name": f"{cluster_kustomization_name}-bstrp-fluxctrl",
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": self._checkloop_resource_timeout,
                    "enable": bootstrap,
                    "resourceState": "IN_PROGRESS.BOOTSTRAP_OK",
                },
            ]
        elif cloud_type == "kubevirt":
            # CAPK (Cluster API + KubeVirt): the workload cluster provisions
            # asynchronously (kubeadm + CNI take ~10-15 min). The cni/postinstall
            # Kustomizations only reach Ready once the workload API is reachable
            # and the manifests apply, so waiting on them makes this check wait
            # for the cluster to be genuinely up instead of returning immediately.
            checkings_list = [
                {
                    "item": "kustomization",
                    "name": cluster_kustomization_name,
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": 1500,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
                },
                {
                    "item": "kustomization",
                    "name": f"{cluster_kustomization_name}-cni",
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": 1500,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.CNI_READY",
                },
                {
                    "item": "kustomization",
                    "name": f"{cluster_kustomization_name}-postinstall",
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": 1500,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.POSTINSTALL_READY",
                },
                {
                    "item": "kustomization",
                    "name": f"{cluster_kustomization_name}-bstrp-fluxctrl",
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": 1500,
                    "enable": bootstrap,
                    "resourceState": "IN_PROGRESS.BOOTSTRAP_OK",
                },
            ]
        else:
            return False, "Not suitable VIM account to check cluster status"
        if cloud_type != "aws":
            if nodegroup_name:
                nodegroup_check = {
                    "item": f"nodegroup_{cloud_type}",
                    "name": nodegroup_name,
                    "namespace": "",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": self._checkloop_resource_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.RESOURCE_READY.NODEGROUP",
                }
                checkings_list.insert(3, nodegroup_check)
        return await self.common_check_list(
            op_id, checkings_list, "clusters", db_cluster
        )

    def update_default_profile_agekeys(self, db_cluster):
        profiles = [
            "infra_controller_profiles",
            "infra_config_profiles",
            "app_profiles",
            "resource_profiles",
        ]
        self.logger.debug("the db_cluster is :{}".format(db_cluster))
        for profile_type in profiles:
            profile_id = db_cluster[profile_type]
            db_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(db_collection, {"_id": profile_id})
            db_profile["age_pubkey"] = db_cluster["age_pubkey"]
            db_profile["age_privkey"] = db_cluster["age_privkey"]
            self.encrypt_age_keys(db_profile)
            self.db.set_one(db_collection, {"_id": db_profile["_id"]}, db_profile)

    def update_profile_state(self, db_cluster, workflow_status, resource_status):
        profiles = [
            "infra_controller_profiles",
            "infra_config_profiles",
            "app_profiles",
            "resource_profiles",
        ]
        self.logger.debug("the db_cluster is :{}".format(db_cluster))
        for profile_type in profiles:
            profile_id = db_cluster[profile_type]
            db_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(db_collection, {"_id": profile_id})
            op_id = db_profile["operationHistory"][-1].get("op_id")
            db_profile["state"] = db_cluster["state"]
            db_profile["resourceState"] = db_cluster["resourceState"]
            db_profile["operatingState"] = db_cluster["operatingState"]
            db_profile = self.update_operation_history(
                db_profile, op_id, workflow_status, resource_status
            )
            self.db.set_one(db_collection, {"_id": db_profile["_id"]}, db_profile)

    async def delete(self, params, order_id):
        self.logger.info("cluster delete Enter")

        try:
            # To get the cluster and op ids
            cluster_id = params["cluster_id"]
            op_id = params["operation_id"]

            # To initialize the operation states
            self.initialize_operation(cluster_id, op_id)

            # To get the cluster
            db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

            # To get the operation params details
            op_params = self.get_operation_params(db_cluster, op_id)

            # To copy the cluster content and decrypting fields to use in workflows
            workflow_content = {
                "cluster": self.decrypted_copy(db_cluster),
            }

            # To get the vim account details
            db_vim = self.db.get_one(
                "vim_accounts", {"name": db_cluster["vim_account"]}
            )
            workflow_content["vim_account"] = db_vim
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.logger.debug(f"Exception: {e}", exc_info=True)
            raise e

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["state"] = "FAILED_DELETION"
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            # Clean items used in the workflow, no matter if the workflow succeeded
            clean_status, clean_msg = await self.odu.clean_items_workflow(
                "delete_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
            )
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["state"] = "DELETED"
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["state"] = "FAILED_DELETION"
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        # Clean items used in the workflow or in the cluster, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "delete_cluster", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "delete_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster["operatingState"] = "IDLE"
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                cluster_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        # To delete it from DB
        if db_cluster["state"] == "DELETED":
            self.delete_cluster(db_cluster)

        # To delete it from k8scluster collection
        self.db.del_one("k8sclusters", {"name": db_cluster["name"]})

        return

    async def check_delete_cluster(self, op_id, op_params, content):
        self.logger.info(
            f"check_delete_cluster Operation {op_id}. Params: {op_params}."
        )
        self.logger.debug(f"Content: {content}")
        db_cluster = content["cluster"]
        cluster_name = db_cluster["git_name"].lower()
        cluster_kustomization_name = cluster_name
        db_vim_account = content["vim_account"]
        cloud_type = db_vim_account["vim_type"]
        if cloud_type == "aws":
            cluster_name = f"{cluster_name}-cluster"
        if cloud_type in ("azure", "gcp", "aws"):
            checkings_list = [
                {
                    "item": "kustomization",
                    "name": cluster_kustomization_name,
                    "namespace": "managed-resources",
                    "deleted": True,
                    "timeout": self._checkloop_kustomization_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.KUSTOMIZATION_DELETED",
                },
                {
                    "item": f"cluster_{cloud_type}",
                    "name": cluster_name,
                    "namespace": "",
                    "deleted": True,
                    "timeout": self._checkloop_resource_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.RESOURCE_DELETED.CLUSTER",
                },
            ]
        elif cloud_type == "kubevirt":
            # CAPK delete: OSM prunes the base Kustomization, which removes the
            # CAPI Cluster and all KubeVirt VMs. Readiness = that Kustomization gone.
            checkings_list = [
                {
                    "item": "kustomization",
                    "name": cluster_kustomization_name,
                    "namespace": "managed-resources",
                    "deleted": True,
                    "timeout": self._checkloop_kustomization_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.KUSTOMIZATION_DELETED",
                },
            ]
        else:
            return False, "Not suitable VIM account to check cluster status"
        return await self.common_check_list(
            op_id, checkings_list, "clusters", db_cluster
        )

    def delete_cluster(self, db_cluster):
        # Actually, item_content is equal to db_cluster
        # detach profiles
        update_dict = None
        profiles_to_detach = [
            "infra_controller_profiles",
            "infra_config_profiles",
            "app_profiles",
            "resource_profiles",
        ]
        """
        profiles_collection = {
            "infra_controller_profiles": "k8sinfra_controller",
            "infra_config_profiles": "k8sinfra_config",
            "app_profiles": "k8sapp",
            "resource_profiles": "k8sresource",
        }
        """
        for profile_type in profiles_to_detach:
            if db_cluster.get(profile_type):
                profile_ids = db_cluster[profile_type]
                profile_ids_copy = deepcopy(profile_ids)
                for profile_id in profile_ids_copy:
                    db_collection = self.profile_collection_mapping[profile_type]
                    db_profile = self.db.get_one(db_collection, {"_id": profile_id})
                    self.logger.debug("the db_profile is :{}".format(db_profile))
                    self.logger.debug(
                        "the item_content name is :{}".format(db_cluster["name"])
                    )
                    self.logger.debug(
                        "the db_profile name is :{}".format(db_profile["name"])
                    )
                    if db_cluster["name"] == db_profile["name"]:
                        self.delete_profile_ksu(profile_id, profile_type)
                        self.db.del_one(db_collection, {"_id": profile_id})
                    else:
                        profile_ids.remove(profile_id)
                        update_dict = {profile_type: profile_ids}
                        self.db.set_one(
                            "clusters", {"_id": db_cluster["_id"]}, update_dict
                        )
        self.db.del_one("clusters", {"_id": db_cluster["_id"]})

    async def attach_profile(self, params, order_id):
        self.logger.info("profile attach Enter")

        # To get the cluster and op ids
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(cluster_id, op_id)

        # To get the cluster
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        workflow_content = {
            "cluster": self.decrypted_copy(db_cluster),
        }

        # To get the profile details
        profile_id = params["profile_id"]
        profile_type = params["profile_type"]
        profile_collection = self.profile_collection_mapping[profile_type]
        db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
        db_profile["profile_type"] = profile_type
        # content["profile"] = db_profile
        workflow_content["profile"] = db_profile

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "attach_profile_to_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["resourceState"] = "ERROR"
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "attach_profile_to_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster["operatingState"] = "IDLE"
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        profile_list = db_cluster[profile_type]
        if resource_status:
            profile_list.append(profile_id)
            db_cluster[profile_type] = profile_list
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        return

    async def detach_profile(self, params, order_id):
        self.logger.info("profile dettach Enter")

        # To get the cluster and op ids
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(cluster_id, op_id)

        # To get the cluster
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        workflow_content = {
            "cluster": self.decrypted_copy(db_cluster),
        }

        # To get the profile details
        profile_id = params["profile_id"]
        profile_type = params["profile_type"]
        profile_collection = self.profile_collection_mapping[profile_type]
        db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
        db_profile["profile_type"] = profile_type
        workflow_content["profile"] = db_profile

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "detach_profile_from_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "detach_profile_from_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster["operatingState"] = "IDLE"
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        profile_list = db_cluster[profile_type]
        self.logger.info("profile list is : {}".format(profile_list))
        if resource_status:
            profile_list.remove(profile_id)
            db_cluster[profile_type] = profile_list
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        return

    async def register(self, params, order_id):
        self.logger.info("cluster register enter")
        workflow_status = None
        resource_status = None

        # To get the cluster and op ids
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(cluster_id, op_id)

        # To get the cluster
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        db_cluster_copy = self.decrypted_copy(db_cluster)
        workflow_content = {
            "cluster": db_cluster_copy,
        }

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "register_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["state"] = "FAILED_CREATION"
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            # Clean items used in the workflow, no matter if the workflow succeeded
            clean_status, clean_msg = await self.odu.clean_items_workflow(
                "register_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
            )
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["state"] = "CREATED"
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["state"] = "FAILED_CREATION"
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "register_cluster", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "register_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster["operatingState"] = "IDLE"
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        # Update default profile agekeys and state
        self.update_default_profile_agekeys(db_cluster_copy)
        self.update_profile_state(db_cluster, workflow_status, resource_status)

        db_register = self.db.get_one("k8sclusters", {"name": db_cluster["name"]})
        db_register["credentials"] = db_cluster["credentials"]
        self.db.set_one("k8sclusters", {"_id": db_register["_id"]}, db_register)

        if db_cluster["resourceState"] == "READY" and db_cluster["state"] == "CREATED":
            # To call the lcm.py for registering the cluster in k8scluster lcm.
            register = await self.regist.create(db_register, order_id)
            self.logger.debug(f"Register is : {register}")
        else:
            db_register["_admin"]["operationalState"] = "ERROR"
            self.db.set_one("k8sclusters", {"_id": db_register["_id"]}, db_register)

        return

    async def check_register_cluster(self, op_id, op_params, content):
        self.logger.info(
            f"check_register_cluster Operation {op_id}. Params: {op_params}."
        )
        # self.logger.debug(f"Content: {content}")
        db_cluster = content["cluster"]
        cluster_name = db_cluster["git_name"].lower()
        cluster_kustomization_name = cluster_name
        bootstrap = op_params.get("bootstrap", True)
        checkings_list = [
            {
                "item": "kustomization",
                "name": f"{cluster_kustomization_name}-bstrp-fluxctrl",
                "namespace": "managed-resources",
                "condition": {
                    "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                    "value": "True",
                },
                "timeout": self._checkloop_kustomization_timeout,
                "enable": bootstrap,
                "resourceState": "IN_PROGRESS.BOOTSTRAP_OK",
            },
        ]
        return await self.common_check_list(
            op_id, checkings_list, "clusters", db_cluster
        )

    async def deregister(self, params, order_id):
        self.logger.info("cluster deregister enter")

        # To get the cluster and op ids
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]

        # To initialize the operation states
        self.initialize_operation(cluster_id, op_id)

        # To get the cluster
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        workflow_content = {
            "cluster": self.decrypted_copy(db_cluster),
        }

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "deregister_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["state"] = "FAILED_DELETION"
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            return

        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "workflow_status is: {} and workflow_msg is: {}".format(
                workflow_status, workflow_msg
            )
        )
        if workflow_status:
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["state"] = "FAILED_DELETION"
            db_cluster["resourceState"] = "ERROR"
        # has to call update_operation_history return content
        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "deregister_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "resource_status is :{} and resource_msg is :{}".format(
                    resource_status, resource_msg
                )
            )
            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, resource_status
        )
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        await self.delete(params, order_id)
        # Clean items used in the workflow or in the cluster, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "deregister_cluster", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        return

    async def get_creds(self, params, order_id):
        self.logger.info("Cluster get creds Enter")
        cluster_id = params["cluster_id"]
        op_id = params["operation_id"]
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})
        result, cluster_creds = await self.odu.get_cluster_credentials(db_cluster)
        if result:
            db_cluster["credentials"] = cluster_creds
        op_len = 0
        for operations in db_cluster["operationHistory"]:
            if operations["op_id"] == op_id:
                db_cluster["operationHistory"][op_len]["result"] = result
                db_cluster["operationHistory"][op_len]["endDate"] = time()
            op_len += 1
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
        self.logger.info("Cluster Get Creds Exit")
        return

    async def update(self, params, order_id):
        self.logger.info("Cluster update Enter")
        # To get the cluster details
        cluster_id = params["cluster_id"]
        db_cluster = self.db.get_one("clusters", {"_id": cluster_id})

        # To get the operation params details
        op_id = params["operation_id"]
        op_params = self.get_operation_params(db_cluster, op_id)

        # To copy the cluster content and decrypting fields to use in workflows
        workflow_content = {
            "cluster": self.decrypted_copy(db_cluster),
        }

        # vim account details
        db_vim = self.db.get_one("vim_accounts", {"name": db_cluster["vim_account"]})
        workflow_content["vim_account"] = db_vim

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "update_cluster", op_id, op_params, workflow_content
        )
        if not workflow_res:
            self.logger.error(f"Failed to launch workflow: {workflow_name}")
            db_cluster["resourceState"] = "ERROR"
            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status=False, resource_status=None
            )
            self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
            # Clean items used in the workflow, no matter if the workflow succeeded
            clean_status, clean_msg = await self.odu.clean_items_workflow(
                "update_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
            )
            return
        self.logger.info("workflow_name is: {}".format(workflow_name))
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "Workflow Status: {} Workflow Message: {}".format(
                workflow_status, workflow_msg
            )
        )

        if workflow_status:
            db_cluster["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_cluster["resourceState"] = "ERROR"

        db_cluster = self.update_operation_history(
            db_cluster, op_id, workflow_status, None
        )
        # self.logger.info("Db content: {}".format(db_content))
        # self.db.set_one(self.db_collection, {"_id": _id}, db_cluster)
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "update_cluster", op_id, op_params, workflow_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "update_cluster", op_id, op_params, workflow_content
            )
            self.logger.info(
                "Resource Status: {} Resource Message: {}".format(
                    resource_status, resource_msg
                )
            )

            if resource_status:
                db_cluster["resourceState"] = "READY"
            else:
                db_cluster["resourceState"] = "ERROR"

            db_cluster = self.update_operation_history(
                db_cluster, op_id, workflow_status, resource_status
            )

        db_cluster["operatingState"] = "IDLE"
        # self.logger.info("db_cluster: {}".format(db_cluster))
        # TODO: verify condition
        # For the moment, if the workflow completed successfully, then we update the db accordingly.
        if workflow_status:
            if "k8s_version" in op_params:
                db_cluster["k8s_version"] = op_params["k8s_version"]
            if "node_count" in op_params:
                db_cluster["node_count"] = op_params["node_count"]
            if "node_size" in op_params:
                db_cluster["node_count"] = op_params["node_size"]
            # self.db.set_one(self.db_collection, {"_id": _id}, db_content)
        db_cluster["current_operation"] = None
        self.db.set_one("clusters", {"_id": db_cluster["_id"]}, db_cluster)
        return

    async def check_update_cluster(self, op_id, op_params, content):
        self.logger.info(
            f"check_update_cluster Operation {op_id}. Params: {op_params}."
        )
        self.logger.debug(f"Content: {content}")
        # return await self.check_dummy_operation(op_id, op_params, content)
        db_cluster = content["cluster"]
        cluster_name = db_cluster["git_name"].lower()
        cluster_kustomization_name = cluster_name
        db_vim_account = content["vim_account"]
        cloud_type = db_vim_account["vim_type"]
        if cloud_type == "aws":
            cluster_name = f"{cluster_name}-cluster"
        if cloud_type in ("azure", "gcp", "aws"):
            checkings_list = [
                {
                    "item": "kustomization",
                    "name": cluster_kustomization_name,
                    "namespace": "managed-resources",
                    "condition": {
                        "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                        "value": "True",
                    },
                    "timeout": self._checkloop_kustomization_timeout,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
                },
            ]
        else:
            return False, "Not suitable VIM account to check cluster status"
        # Scale operation
        if "node_count" in op_params:
            if cloud_type in ("azure", "gcp"):
                checkings_list.append(
                    {
                        "item": f"cluster_{cloud_type}",
                        "name": cluster_name,
                        "namespace": "",
                        "condition": {
                            "jsonpath_filter": "status.atProvider.defaultNodePool[0].nodeCount",
                            "value": f"{op_params['node_count']}",
                        },
                        "timeout": self._checkloop_resource_timeout * 3,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.RESOURCE_READY.NODE_COUNT.CLUSTER",
                    }
                )
            elif cloud_type == "aws":
                checkings_list.append(
                    {
                        "item": f"nodegroup_{cloud_type}",
                        "name": f"{cluster_name}-nodegroup",
                        "namespace": "",
                        "condition": {
                            "jsonpath_filter": "status.atProvider.scalingConfig[0].desiredSize",
                            "value": f"{op_params['node_count']}",
                        },
                        "timeout": self._checkloop_resource_timeout * 3,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.RESOURCE_READY.NODE_COUNT.CLUSTER",
                    }
                )

        # Upgrade operation
        if "k8s_version" in op_params:
            checkings_list.append(
                {
                    "item": f"cluster_{cloud_type}",
                    "name": cluster_name,
                    "namespace": "",
                    "condition": {
                        "jsonpath_filter": "status.atProvider.defaultNodePool[0].orchestratorVersion",
                        "value": op_params["k8s_version"],
                    },
                    "timeout": self._checkloop_resource_timeout * 2,
                    "enable": True,
                    "resourceState": "IN_PROGRESS.RESOURCE_READY.K8S_VERSION.CLUSTER",
                }
            )
        return await self.common_check_list(
            op_id, checkings_list, "clusters", db_cluster
        )


class CloudCredentialsLcm(GitOpsLcm):
    db_collection = "vim_accounts"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def add(self, params, order_id):
        self.logger.info("Cloud Credentials create")
        vim_id = params["_id"]
        op_id = vim_id
        op_params = params
        db_content = self.db.get_one(self.db_collection, {"_id": vim_id})
        vim_config = db_content.get("config", {})
        self.db.encrypt_decrypt_fields(
            vim_config.get("credentials"),
            "decrypt",
            ["password", "secret"],
            schema_version=db_content["schema_version"],
            salt=vim_id,
        )

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_cloud_credentials", op_id, op_params, db_content
        )

        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )

        self.logger.info(
            "Workflow Status: {} Workflow Msg: {}".format(workflow_status, workflow_msg)
        )

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "create_cloud_credentials", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "create_cloud_credentials", op_id, op_params, db_content
            )
            self.logger.info(
                "Resource Status: {} Resource Message: {}".format(
                    resource_status, resource_msg
                )
            )

            db_content["_admin"]["operationalState"] = "ENABLED"
            for operation in db_content["_admin"]["operations"]:
                if operation["lcmOperationType"] == "create":
                    operation["operationState"] = "ENABLED"
            self.logger.info("Content : {}".format(db_content))
        self.db.set_one("vim_accounts", {"_id": db_content["_id"]}, db_content)
        return

    async def edit(self, params, order_id):
        self.logger.info("Cloud Credentials Update")
        vim_id = params["_id"]
        op_id = vim_id
        op_params = params
        db_content = self.db.get_one("vim_accounts", {"_id": vim_id})
        vim_config = db_content.get("config", {})
        self.db.encrypt_decrypt_fields(
            vim_config.get("credentials"),
            "decrypt",
            ["password", "secret"],
            schema_version=db_content["schema_version"],
            salt=vim_id,
        )

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "update_cloud_credentials", op_id, op_params, db_content
        )
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "Workflow Status: {} Workflow Msg: {}".format(workflow_status, workflow_msg)
        )

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "update_cloud_credentials", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "update_cloud_credentials", op_id, op_params, db_content
            )
            self.logger.info(
                "Resource Status: {} Resource Message: {}".format(
                    resource_status, resource_msg
                )
            )
        return

    async def remove(self, params, order_id):
        self.logger.info("Cloud Credentials remove")
        vim_id = params["_id"]
        op_id = vim_id
        op_params = params
        db_content = self.db.get_one("vim_accounts", {"_id": vim_id})

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_cloud_credentials", op_id, op_params, db_content
        )
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "Workflow Status: {} Workflow Msg: {}".format(workflow_status, workflow_msg)
        )

        if workflow_status:
            resource_status, resource_msg = await self.check_resource_status(
                "delete_cloud_credentials", op_id, op_params, db_content
            )
            self.logger.info(
                "Resource Status: {} Resource Message: {}".format(
                    resource_status, resource_msg
                )
            )
        self.db.del_one(self.db_collection, {"_id": db_content["_id"]})
        return


class K8sAppLcm(GitOpsLcm):
    db_collection = "k8sapp"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("App Profile Create Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sapp", {"_id": profile_id})
        content["profile_type"] = "applications"
        op_params = self.get_operation_params(content, op_id)
        self.db.set_one("k8sapp", {"_id": content["_id"]}, content)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "create_profile", op_id, op_params, content
            )
        self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
        self.logger.info(
            f"App Profile Create Exit with resource status: {resource_status}"
        )
        return

    async def delete(self, params, order_id):
        self.logger.info("App delete Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sapp", {"_id": profile_id})
        op_params = self.get_operation_params(content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "delete_profile", op_id, op_params, content
            )

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                profile_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        self.logger.info(f"Resource status: {resource_status}")
        if resource_status:
            content["state"] = "DELETED"
            profile_type = self.profile_type_mapping[content["profile_type"]]
            self.delete_profile_ksu(profile_id, profile_type)
            self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
            self.db.del_one(self.db_collection, {"_id": content["_id"]})
        self.logger.info(
            f"App Profile Delete Exit with resource status: {resource_status}"
        )
        return


class K8sResourceLcm(GitOpsLcm):
    db_collection = "k8sresource"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("Resource Profile Create Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sresource", {"_id": profile_id})
        content["profile_type"] = "managed-resources"
        op_params = self.get_operation_params(content, op_id)
        self.db.set_one("k8sresource", {"_id": content["_id"]}, content)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "create_profile", op_id, op_params, content
            )
        self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
        self.logger.info(
            f"Resource Create Exit with resource status: {resource_status}"
        )
        return

    async def delete(self, params, order_id):
        self.logger.info("Resource delete Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sresource", {"_id": profile_id})
        op_params = self.get_operation_params(content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "delete_profile", op_id, op_params, content
            )

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                profile_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        if resource_status:
            content["state"] = "DELETED"
            profile_type = self.profile_type_mapping[content["profile_type"]]
            self.delete_profile_ksu(profile_id, profile_type)
            self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
            self.db.del_one(self.db_collection, {"_id": content["_id"]})
        self.logger.info(
            f"Resource Delete Exit with resource status: {resource_status}"
        )
        return


class K8sInfraControllerLcm(GitOpsLcm):
    db_collection = "k8sinfra_controller"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("Infra controller Profile Create Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sinfra_controller", {"_id": profile_id})
        content["profile_type"] = "infra-controllers"
        op_params = self.get_operation_params(content, op_id)
        self.db.set_one("k8sinfra_controller", {"_id": content["_id"]}, content)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "create_profile", op_id, op_params, content
            )
        self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
        self.logger.info(
            f"Infra Controller Create Exit with resource status: {resource_status}"
        )
        return

    async def delete(self, params, order_id):
        self.logger.info("Infra controller delete Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sinfra_controller", {"_id": profile_id})
        op_params = self.get_operation_params(content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "delete_profile", op_id, op_params, content
            )

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                profile_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        if resource_status:
            content["state"] = "DELETED"
            profile_type = self.profile_type_mapping[content["profile_type"]]
            self.delete_profile_ksu(profile_id, profile_type)
            self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
            self.db.del_one(self.db_collection, {"_id": content["_id"]})
        self.logger.info(
            f"Infra Controller Delete Exit with resource status: {resource_status}"
        )
        return


class K8sInfraConfigLcm(GitOpsLcm):
    db_collection = "k8sinfra_config"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("Infra config Profile Create Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sinfra_config", {"_id": profile_id})
        content["profile_type"] = "infra-configs"
        op_params = self.get_operation_params(content, op_id)
        self.db.set_one("k8sinfra_config", {"_id": content["_id"]}, content)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "create_profile", op_id, op_params, content
            )
        self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
        self.logger.info(
            f"Infra Config Create Exit with resource status: {resource_status}"
        )
        return

    async def delete(self, params, order_id):
        self.logger.info("Infra config delete Enter")

        op_id = params["operation_id"]
        profile_id = params["profile_id"]

        # To initialize the operation states
        self.initialize_operation(profile_id, op_id)

        content = self.db.get_one("k8sinfra_config", {"_id": profile_id})
        op_params = self.get_operation_params(content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_profile", op_id, op_params, content
        )
        self.logger.info("workflow_name is: {}".format(workflow_name))

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, content
        )

        if workflow_status:
            resource_status, content = await self.check_resource_and_update_db(
                "delete_profile", op_id, op_params, content
            )

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                profile_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        if resource_status:
            content["state"] = "DELETED"
            profile_type = self.profile_type_mapping[content["profile_type"]]
            self.delete_profile_ksu(profile_id, profile_type)
            self.db.set_one(self.db_collection, {"_id": content["_id"]}, content)
            self.db.del_one(self.db_collection, {"_id": content["_id"]})
        self.logger.info(
            f"Infra Config Delete Exit with resource status: {resource_status}"
        )

        return


class OkaLcm(GitOpsLcm):
    db_collection = "okas"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)

    async def create(self, params, order_id):
        self.logger.info("OKA Create Enter")
        op_id = params["operation_id"]
        oka_id = params["oka_id"]
        self.initialize_operation(oka_id, op_id)
        db_content = self.db.get_one(self.db_collection, {"_id": oka_id})
        op_params = self.get_operation_params(db_content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_oka", op_id, op_params, db_content
        )

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_content
        )

        if workflow_status:
            resource_status, db_content = await self.check_resource_and_update_db(
                "create_oka", op_id, op_params, db_content
            )
        self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "create_oka", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        self.logger.info(f"OKA Create Exit with resource status: {resource_status}")
        return

    async def edit(self, params, order_id):
        self.logger.info("OKA Edit Enter")
        op_id = params["operation_id"]
        oka_id = params["oka_id"]
        self.initialize_operation(oka_id, op_id)
        db_content = self.db.get_one(self.db_collection, {"_id": oka_id})
        op_params = self.get_operation_params(db_content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "update_oka", op_id, op_params, db_content
        )
        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_content
        )

        if workflow_status:
            resource_status, db_content = await self.check_resource_and_update_db(
                "update_oka", op_id, op_params, db_content
            )
        self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)
        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "update_oka", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        self.logger.info(f"OKA Update Exit with resource status: {resource_status}")
        return

    async def delete(self, params, order_id):
        self.logger.info("OKA delete Enter")
        op_id = params["operation_id"]
        oka_id = params["oka_id"]
        self.initialize_operation(oka_id, op_id)
        db_content = self.db.get_one(self.db_collection, {"_id": oka_id})
        op_params = self.get_operation_params(db_content, op_id)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_oka", op_id, op_params, db_content
        )
        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_content
        )

        if workflow_status:
            resource_status, db_content = await self.check_resource_and_update_db(
                "delete_oka", op_id, op_params, db_content
            )

        force = params.get("force", False)
        if force:
            force_delete_status = self.check_force_delete_and_delete_from_db(
                oka_id, workflow_status, resource_status, force
            )
            if force_delete_status:
                return

        if resource_status:
            db_content["state"] == "DELETED"
            self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)
            self.db.del_one(self.db_collection, {"_id": db_content["_id"]})
        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "delete_oka", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        self.logger.info(f"OKA Delete Exit with resource status: {resource_status}")
        return


class KsuLcm(GitOpsLcm):
    db_collection = "ksus"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)
        self._workflows = {
            "create_ksus": {
                "check_resource_function": self.check_create_ksus,
            },
            "delete_ksus": {
                "check_resource_function": self.check_delete_ksus,
            },
        }

    def get_dbclusters_from_profile(self, profile_id, profile_type):
        cluster_list = []
        db_clusters = self.db.get_list("clusters")
        self.logger.info(f"Getting list of clusters for {profile_type} {profile_id}")
        for db_cluster in db_clusters:
            if profile_id in db_cluster.get(profile_type, []):
                self.logger.info(
                    f"Profile {profile_id} found in cluster {db_cluster['name']}"
                )
                cluster_list.append(db_cluster)
        return cluster_list

    async def create(self, params, order_id):
        self.logger.info("ksu Create Enter")
        db_content = []
        op_params = []
        op_id = params["operation_id"]
        for ksu_id in params["ksus_list"]:
            self.logger.info("Ksu ID: {}".format(ksu_id))
            self.initialize_operation(ksu_id, op_id)
            db_ksu = self.db.get_one(self.db_collection, {"_id": ksu_id})
            self.logger.info("Db KSU: {}".format(db_ksu))
            db_content.append(db_ksu)
            ksu_params = {}
            ksu_params = self.get_operation_params(db_ksu, op_id)
            self.logger.info("Operation Params: {}".format(ksu_params))
            # Update ksu_params["profile"] with profile name and age-pubkey
            profile_type = ksu_params["profile"]["profile_type"]
            profile_id = ksu_params["profile"]["_id"]
            profile_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
            # db_profile is decrypted inline
            # No need to use decrypted_copy because db_profile won't be updated.
            self.decrypt_age_keys(db_profile)
            ksu_params["profile"]["name"] = db_profile["name"]
            ksu_params["profile"]["age_pubkey"] = db_profile.get("age_pubkey", "")
            # Update ksu_params["oka"] with sw_catalog_path (when missing)
            # TODO: remove this in favor of doing it in ODU workflow
            for oka in ksu_params["oka"]:
                if "sw_catalog_path" not in oka:
                    oka_id = oka["_id"]
                    db_oka = self.db.get_one("okas", {"_id": oka_id})
                    oka_type = MAP_PROFILE[
                        db_oka.get("profile_type", "infra_controller_profiles")
                    ]
                    oka[
                        "sw_catalog_path"
                    ] = f"{oka_type}/{db_oka['git_name'].lower()}/templates"
            op_params.append(ksu_params)

        # A single workflow is launched for all KSUs
        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "create_ksus", op_id, op_params, db_content
        )
        # Update workflow status in all KSUs
        wf_status_list = []
        for db_ksu, ksu_params in zip(db_content, op_params):
            workflow_status = await self.check_workflow_and_update_db(
                op_id, workflow_name, db_ksu
            )
            wf_status_list.append(workflow_status)
        # Update resource status in all KSUs
        # TODO: Is an operation correct if n KSUs are right and 1 is not OK?
        res_status_list = []
        for db_ksu, ksu_params, wf_status in zip(db_content, op_params, wf_status_list):
            if wf_status:
                resource_status, db_ksu = await self.check_resource_and_update_db(
                    "create_ksus", op_id, ksu_params, db_ksu
                )
            else:
                resource_status = False
            res_status_list.append(resource_status)
            self.db.set_one(self.db_collection, {"_id": db_ksu["_id"]}, db_ksu)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "create_ksus", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        self.logger.info(f"KSU Create EXIT with Resource Status {res_status_list}")
        return

    async def edit(self, params, order_id):
        self.logger.info("ksu edit Enter")
        db_content = []
        op_params = []
        op_id = params["operation_id"]
        for ksu_id in params["ksus_list"]:
            self.initialize_operation(ksu_id, op_id)
            db_ksu = self.db.get_one("ksus", {"_id": ksu_id})
            db_content.append(db_ksu)
            ksu_params = {}
            ksu_params = self.get_operation_params(db_ksu, op_id)
            # Update ksu_params["profile"] with profile name and age-pubkey
            profile_type = ksu_params["profile"]["profile_type"]
            profile_id = ksu_params["profile"]["_id"]
            profile_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
            # db_profile is decrypted inline
            # No need to use decrypted_copy because db_profile won't be updated.
            self.decrypt_age_keys(db_profile)
            ksu_params["profile"]["name"] = db_profile["name"]
            ksu_params["profile"]["age_pubkey"] = db_profile.get("age_pubkey", "")
            # Update ksu_params["oka"] with sw_catalog_path (when missing)
            # TODO: remove this in favor of doing it in ODU workflow
            for oka in ksu_params["oka"]:
                if "sw_catalog_path" not in oka:
                    oka_id = oka["_id"]
                    db_oka = self.db.get_one("okas", {"_id": oka_id})
                    oka_type = MAP_PROFILE[
                        db_oka.get("profile_type", "infra_controller_profiles")
                    ]
                    oka[
                        "sw_catalog_path"
                    ] = f"{oka_type}/{db_oka['git_name']}/templates"
            op_params.append(ksu_params)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "update_ksus", op_id, op_params, db_content
        )

        for db_ksu, ksu_params in zip(db_content, op_params):
            workflow_status = await self.check_workflow_and_update_db(
                op_id, workflow_name, db_ksu
            )

            if workflow_status:
                resource_status, db_ksu = await self.check_resource_and_update_db(
                    "update_ksus", op_id, ksu_params, db_ksu
                )
                db_ksu["name"] = ksu_params["name"]
                db_ksu["description"] = ksu_params["description"]
                db_ksu["profile"]["profile_type"] = ksu_params["profile"][
                    "profile_type"
                ]
                db_ksu["profile"]["_id"] = ksu_params["profile"]["_id"]
                db_ksu["oka"] = ksu_params["oka"]
            self.db.set_one(self.db_collection, {"_id": db_ksu["_id"]}, db_ksu)

        # Clean items used in the workflow, no matter if the workflow succeeded
        clean_status, clean_msg = await self.odu.clean_items_workflow(
            "create_ksus", op_id, op_params, db_content
        )
        self.logger.info(
            f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
        )
        self.logger.info(f"KSU Update EXIT with Resource Status {resource_status}")
        return

    async def delete(self, params, order_id):
        self.logger.info("ksu delete Enter")
        db_content = []
        op_params = []
        op_id = params["operation_id"]
        for ksu_id in params["ksus_list"]:
            self.initialize_operation(ksu_id, op_id)
            db_ksu = self.db.get_one("ksus", {"_id": ksu_id})
            db_content.append(db_ksu)
            ksu_params = {}
            ksu_params["profile"] = {}
            ksu_params["profile"]["profile_type"] = db_ksu["profile"]["profile_type"]
            ksu_params["profile"]["_id"] = db_ksu["profile"]["_id"]
            # Update ksu_params["profile"] with profile name
            profile_type = ksu_params["profile"]["profile_type"]
            profile_id = ksu_params["profile"]["_id"]
            profile_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
            ksu_params["profile"]["name"] = db_profile["name"]
            op_params.append(ksu_params)

        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "delete_ksus", op_id, op_params, db_content
        )

        for db_ksu, ksu_params in zip(db_content, op_params):
            workflow_status = await self.check_workflow_and_update_db(
                op_id, workflow_name, db_ksu
            )

            if workflow_status:
                resource_status, db_ksu = await self.check_resource_and_update_db(
                    "delete_ksus", op_id, ksu_params, db_ksu
                )

            force = params.get("force", False)
            if force:
                force_delete_status = self.check_force_delete_and_delete_from_db(
                    db_ksu["_id"], workflow_status, resource_status, force
                )
                if force_delete_status:
                    return

            if resource_status:
                db_ksu["state"] == "DELETED"
                self.delete_ksu_dependency(db_ksu["_id"], db_ksu)
                self.db.set_one(self.db_collection, {"_id": db_ksu["_id"]}, db_ksu)
                self.db.del_one(self.db_collection, {"_id": db_ksu["_id"]})

        self.logger.info(f"KSU Delete Exit with resource status: {resource_status}")
        return

    async def clone(self, params, order_id):
        self.logger.info("ksu clone Enter")
        op_id = params["operation_id"]
        ksus_id = params["ksus_list"][0]
        self.initialize_operation(ksus_id, op_id)
        db_content = self.db.get_one(self.db_collection, {"_id": ksus_id})
        op_params = self.get_operation_params(db_content, op_id)
        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "clone_ksus", op_id, op_params, db_content
        )

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_content
        )

        if workflow_status:
            resource_status, db_content = await self.check_resource_and_update_db(
                "clone_ksus", op_id, op_params, db_content
            )
        self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)

        self.logger.info(f"KSU Clone Exit with resource status: {resource_status}")
        return

    async def move(self, params, order_id):
        self.logger.info("ksu move Enter")
        op_id = params["operation_id"]
        ksus_id = params["ksus_list"][0]
        self.initialize_operation(ksus_id, op_id)
        db_content = self.db.get_one(self.db_collection, {"_id": ksus_id})
        op_params = self.get_operation_params(db_content, op_id)
        workflow_res, workflow_name, _ = await self.odu.launch_workflow(
            "move_ksus", op_id, op_params, db_content
        )

        workflow_status = await self.check_workflow_and_update_db(
            op_id, workflow_name, db_content
        )

        if workflow_status:
            resource_status, db_content = await self.check_resource_and_update_db(
                "move_ksus", op_id, op_params, db_content
            )
        self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)

        self.logger.info(f"KSU Move Exit with resource status: {resource_status}")
        return

    async def check_create_ksus(self, op_id, op_params, content):
        self.logger.info(f"check_create_ksus Operation {op_id}. Params: {op_params}.")
        self.logger.debug(f"Content: {content}")
        db_ksu = content
        kustomization_name = db_ksu["git_name"].lower()
        oka_list = op_params["oka"]
        oka_item = oka_list[0]
        oka_params = oka_item.get("transformation", {})
        kustomization_ns = oka_params.get("kustomization_namespace", "flux-system")
        profile_id = op_params.get("profile", {}).get("_id")
        profile_type = op_params.get("profile", {}).get("profile_type")
        self.logger.info(
            f"Checking status of KSU {db_ksu['name']} for profile {profile_id}."
        )
        dbcluster_list = self.get_dbclusters_from_profile(profile_id, profile_type)
        if not dbcluster_list:
            self.logger.info(f"No clusters found for profile {profile_id}.")
        for db_cluster in dbcluster_list:
            try:
                self.logger.info(
                    f"Checking status of KSU {db_ksu['name']} in cluster {db_cluster['name']}."
                )
                cluster_kubectl = self.cluster_kubectl(db_cluster)
                checkings_list = [
                    {
                        "item": "kustomization",
                        "name": kustomization_name,
                        "namespace": kustomization_ns,
                        "condition": {
                            "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                            "value": "True",
                        },
                        "timeout": self._checkloop_kustomization_timeout,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
                    },
                ]
                self.logger.info(
                    f"Checking status of KSU {db_ksu['name']} for profile {profile_id}."
                )
                result, message = await self.common_check_list(
                    op_id, checkings_list, "ksus", db_ksu, kubectl_obj=cluster_kubectl
                )
                if not result:
                    return False, message
            except Exception as e:
                self.logger.error(
                    f"Error checking KSU in cluster {db_cluster['name']}."
                )
                self.logger.error(e)
                return False, f"Error checking KSU in cluster {db_cluster['name']}."
        return True, "OK"

    async def check_delete_ksus(self, op_id, op_params, content):
        self.logger.info(f"check_delete_ksus Operation {op_id}. Params: {op_params}.")
        self.logger.debug(f"Content: {content}")
        db_ksu = content
        kustomization_name = db_ksu["git_name"].lower()
        oka_list = db_ksu["oka"]
        oka_item = oka_list[0]
        oka_params = oka_item.get("transformation", {})
        kustomization_ns = oka_params.get("kustomization_namespace", "flux-system")
        profile_id = op_params.get("profile", {}).get("_id")
        profile_type = op_params.get("profile", {}).get("profile_type")
        self.logger.info(
            f"Checking status of KSU {db_ksu['name']} for profile {profile_id}."
        )
        dbcluster_list = self.get_dbclusters_from_profile(profile_id, profile_type)
        if not dbcluster_list:
            self.logger.info(f"No clusters found for profile {profile_id}.")
        for db_cluster in dbcluster_list:
            try:
                self.logger.info(
                    f"Checking status of KSU in cluster {db_cluster['name']}."
                )
                cluster_kubectl = self.cluster_kubectl(db_cluster)
                checkings_list = [
                    {
                        "item": "kustomization",
                        "name": kustomization_name,
                        "namespace": kustomization_ns,
                        "deleted": True,
                        "timeout": self._checkloop_kustomization_timeout,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.KUSTOMIZATION_DELETED",
                    },
                ]
                self.logger.info(
                    f"Checking status of KSU {db_ksu['name']} for profile {profile_id}."
                )
                result, message = await self.common_check_list(
                    op_id, checkings_list, "ksus", db_ksu, kubectl_obj=cluster_kubectl
                )
                if not result:
                    return False, message
            except Exception as e:
                self.logger.error(
                    f"Error checking KSU in cluster {db_cluster['name']}."
                )
                self.logger.error(e)
                return False, f"Error checking KSU in cluster {db_cluster['name']}."
        return True, "OK"


class AppInstanceLcm(GitOpsLcm):
    db_collection = "appinstances"

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """
        super().__init__(msg, lcm_tasks, config)
        self._workflows = {
            "create_app": {
                "check_resource_function": self.check_create_app,
            },
            "update_app": {
                "check_resource_function": self.check_update_app,
            },
            "delete_app": {
                "check_resource_function": self.check_delete_app,
            },
        }

    def get_dbclusters_from_profile(self, profile_id, profile_type):
        cluster_list = []
        db_clusters = self.db.get_list("clusters")
        self.logger.info(f"Getting list of clusters for {profile_type} {profile_id}")
        for db_cluster in db_clusters:
            if profile_id in db_cluster.get(profile_type, []):
                self.logger.info(
                    f"Profile {profile_id} found in cluster {db_cluster['name']}"
                )
                cluster_list.append(db_cluster)
        return cluster_list

    def update_app_dependency(self, app_id, db_app):
        self.logger.info(f"Updating AppInstance dependencies for AppInstance {app_id}")
        oka_id = db_app.get("oka")
        if not oka_id:
            self.logger.info(f"No OKA associated with AppInstance {app_id}")
            return

        used_oka = []
        all_apps = self.db.get_list(self.db_collection, {})
        for app in all_apps:
            if app["_id"] != app_id:
                app_oka_id = app["oka"]
                if app_oka_id not in used_oka:
                    used_oka.append(app_oka_id)
        self.logger.info(f"Used OKA: {used_oka}")

        if oka_id not in used_oka:
            self.db.set_one(
                "okas", {"_id": oka_id}, {"_admin.usageState": "NOT_IN_USE"}
            )
        return

    async def generic_operation(self, params, order_id, operation_name):
        self.logger.info(f"Generic operation. Operation name: {operation_name}")
        # self.logger.debug(f"Params: {params}")
        try:
            op_id = params["operation_id"]
            app_id = params["appinstance"]
            self.initialize_operation(app_id, op_id)
            db_app = self.db.get_one(self.db_collection, {"_id": app_id})
            # self.logger.debug("Db App: {}".format(db_app))

            # Initialize workflow_content with a copy of the db_app, decrypting fields to use in workflows
            db_app_copy = self.decrypted_copy(db_app)
            workflow_content = {
                "app": db_app_copy,
            }

            # Update workflow_content with profile info
            profile_type = db_app["profile_type"]
            profile_id = db_app["profile"]
            profile_collection = self.profile_collection_mapping[profile_type]
            db_profile = self.db.get_one(profile_collection, {"_id": profile_id})
            # db_profile is decrypted inline
            # No need to use decrypted_copy because db_profile won't be updated.
            self.decrypt_age_keys(db_profile)
            workflow_content["profile"] = db_profile

            op_params = self.get_operation_params(db_app, op_id)
            if not op_params:
                op_params = {}
            self.logger.debug("Operation Params: {}".format(op_params))

            # Get SW catalog path from op_params or from DB
            aux_dict = {}
            if operation_name == "create_app":
                aux_dict = op_params
            else:
                aux_dict = db_app
            sw_catalog_path = ""
            if "sw_catalog_path" in aux_dict:
                sw_catalog_path = aux_dict.get("sw_catalog_path", "")
            elif "oka" in aux_dict:
                oka_id = aux_dict["oka"]
                db_oka = self.db.get_one("okas", {"_id": oka_id})
                oka_type = MAP_PROFILE[
                    db_oka.get("profile_type", "infra_controller_profiles")
                ]
                sw_catalog_path = f"{oka_type}/{db_oka['git_name'].lower()}"
            else:
                self.logger.error("SW Catalog path could not be determined.")
                raise LcmException("SW Catalog path could not be determined.")
            self.logger.debug(f"SW Catalog path: {sw_catalog_path}")

            # Get model from Git repo
            # Clone the SW catalog repo
            repodir = self.cloneGitRepo(
                repo_url=self._full_repo_sw_catalogs_url, branch="main"
            )
            model_file_path = os.path.join(repodir, sw_catalog_path, "model.yaml")
            if not os.path.exists(model_file_path):
                self.logger.error(f"Model file not found at path: {model_file_path}")
                raise LcmException(f"Model file not found at path: {model_file_path}")
            # Store the model content in workflow_content
            with open(model_file_path) as model_file:
                workflow_content["model"] = yaml.safe_load(model_file.read())

            # A single workflow is launched for the App operation
            self.logger.debug("Launching workflow {}".format(operation_name))
            (
                workflow_res,
                workflow_name,
                workflow_resources,
            ) = await self.odu.launch_workflow(
                operation_name, op_id, op_params, workflow_content
            )

            if not workflow_res:
                self.logger.error(f"Failed to launch workflow: {workflow_name}")
                if operation_name == "create_app":
                    db_app["state"] = "FAILED_CREATION"
                elif operation_name == "delete_app":
                    db_app["state"] = "FAILED_DELETION"
                db_app["resourceState"] = "ERROR"
                db_app = self.update_operation_history(
                    db_app, op_id, workflow_status=False, resource_status=None
                )
                self.db.set_one(self.db_collection, {"_id": db_app["_id"]}, db_app)
                # Clean items used in the workflow, no matter if the workflow succeeded
                clean_status, clean_msg = await self.odu.clean_items_workflow(
                    operation_name, op_id, op_params, workflow_content
                )
                self.logger.info(
                    f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
                )
                return

            # Update resources created in workflow
            db_app["app_model"] = workflow_resources.get("app_model", {})

            # Update workflow status in App
            workflow_status = await self.check_workflow_and_update_db(
                op_id, workflow_name, db_app
            )
            # Update resource status in DB
            if workflow_status:
                resource_status, db_app = await self.check_resource_and_update_db(
                    operation_name, op_id, op_params, db_app
                )
            else:
                resource_status = False
            self.db.set_one(self.db_collection, {"_id": db_app["_id"]}, db_app)

            # Clean items used in the workflow, no matter if the workflow succeeded
            clean_status, clean_msg = await self.odu.clean_items_workflow(
                operation_name, op_id, op_params, workflow_content
            )
            self.logger.info(
                f"clean_status is :{clean_status} and clean_msg is :{clean_msg}"
            )

            if operation_name == "delete_app":
                force = params.get("force", False)
                if force:
                    force_delete_status = self.check_force_delete_and_delete_from_db(
                        db_app["_id"], workflow_status, resource_status, force
                    )
                    if force_delete_status:
                        return
                if resource_status:
                    db_app["state"] == "DELETED"
                    self.update_app_dependency(db_app["_id"], db_app)
                    self.db.del_one(self.db_collection, {"_id": db_app["_id"]})

            self.logger.info(
                f"Generic app operation Exit {operation_name} with resource Status {resource_status}"
            )
            return
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.logger.debug(f"Exception: {e}", exc_info=True)
            return

    async def create(self, params, order_id):
        self.logger.info("App Create Enter")
        return await self.generic_operation(params, order_id, "create_app")

    async def update(self, params, order_id):
        self.logger.info("App Edit Enter")
        return await self.generic_operation(params, order_id, "update_app")

    async def delete(self, params, order_id):
        self.logger.info("App Delete Enter")
        return await self.generic_operation(params, order_id, "delete_app")

    async def check_appinstance(self, op_id, op_params, content, deleted=False):
        self.logger.info(
            f"check_app_instance Operation {op_id}. Params: {op_params}. Deleted: {deleted}"
        )
        self.logger.debug(f"Content: {content}")
        db_app = content
        profile_id = db_app["profile"]
        profile_type = db_app["profile_type"]
        app_name = db_app["name"]
        self.logger.info(
            f"Checking status of AppInstance {app_name} for profile {profile_id}."
        )

        # TODO: read app_model and get kustomization name and namespace
        # app_model = db_app.get("app_model", {})
        kustomization_list = [
            {
                "name": f"jenkins-{app_name}",
                "namespace": "flux-system",
            }
        ]
        checkings_list = []
        if deleted:
            for kustomization in kustomization_list:
                checkings_list.append(
                    {
                        "item": "kustomization",
                        "name": kustomization["name"].lower(),
                        "namespace": kustomization["namespace"],
                        "deleted": True,
                        "timeout": self._checkloop_kustomization_timeout,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.KUSTOMIZATION_DELETED",
                    }
                )
        else:
            for kustomization in kustomization_list:
                checkings_list.append(
                    {
                        "item": "kustomization",
                        "name": kustomization["name"].lower(),
                        "namespace": kustomization["namespace"],
                        "condition": {
                            "jsonpath_filter": "status.conditions[?(@.type=='Ready')].status",
                            "value": "True",
                        },
                        "timeout": self._checkloop_kustomization_timeout,
                        "enable": True,
                        "resourceState": "IN_PROGRESS.KUSTOMIZATION_READY",
                    }
                )

        dbcluster_list = self.get_dbclusters_from_profile(profile_id, profile_type)
        if not dbcluster_list:
            self.logger.info(f"No clusters found for profile {profile_id}.")
        for db_cluster in dbcluster_list:
            try:
                self.logger.info(
                    f"Checking status of AppInstance {app_name} in cluster {db_cluster['name']}."
                )
                cluster_kubectl = self.cluster_kubectl(db_cluster)
                result, message = await self.common_check_list(
                    op_id,
                    checkings_list,
                    self.db_collection,
                    db_app,
                    kubectl_obj=cluster_kubectl,
                )
                if not result:
                    return False, message
            except Exception as e:
                self.logger.error(
                    f"Error checking AppInstance in cluster {db_cluster['name']}."
                )
                self.logger.error(e)
                return (
                    False,
                    f"Error checking AppInstance in cluster {db_cluster['name']}.",
                )
        return True, "OK"

    async def check_create_app(self, op_id, op_params, content):
        self.logger.info(f"check_update_app Operation {op_id}. Params: {op_params}.")
        # self.logger.debug(f"Content: {content}")
        return await self.check_appinstance(op_id, op_params, content)

    async def check_update_app(self, op_id, op_params, content):
        self.logger.info(f"check_update_app Operation {op_id}. Params: {op_params}.")
        # self.logger.debug(f"Content: {content}")
        return await self.check_appinstance(op_id, op_params, content)

    async def check_delete_app(self, op_id, op_params, content):
        self.logger.info(f"check_delete_app Operation {op_id}. Params: {op_params}.")
        # self.logger.debug(f"Content: {content}")
        return await self.check_appinstance(op_id, op_params, content, deleted=True)
