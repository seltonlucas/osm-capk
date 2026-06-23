#######################################################################################
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
#######################################################################################


import logging
from osm_lcm.lcm_utils import LcmBase
from osm_lcm.n2vc import kubectl
from osm_lcm.odu_libs import (
    vim_mgmt as odu_vim_mgmt,
    cluster_mgmt as odu_cluster_mgmt,
    nodegroup as odu_nodegroup,
    app as odu_app,
    ksu as odu_ksu,
    oka as odu_oka,
    profiles as odu_profiles,
    workflows,
    render as odu_render,
    common as odu_common,
)


class OduWorkflow(LcmBase):
    """
    Class to manage the workflows for the OSM Deployment Unit (ODU).
    This class is responsible for executing various workflows related to
    cluster management, profile management, and other operations.
    """

    def __init__(self, msg, lcm_tasks, config):
        """
        Init, Connect to database, filesystem storage, and messaging
        :param config: two level dictionary with configuration. Top level should contain 'database', 'storage',
        :return: None
        """

        self.logger = logging.getLogger("lcm.gitops")
        self.lcm_tasks = lcm_tasks
        self.logger.info("Msg: {} lcm_tasks: {} ".format(msg, lcm_tasks))

        # self._kubeconfig = kubeconfig  # TODO: get it from config
        self.gitops_config = config["gitops"]
        self.logger.debug(f"Gitops Config: {self.gitops_config}")
        self._odu_checkloop_retry_time = 15
        self._kubeconfig = self.gitops_config.get("mgmtcluster_kubeconfig")
        self._kubectl = kubectl.Kubectl(config_file=self._kubeconfig)
        self._repo_base_url = self.gitops_config.get("git_base_url")
        self._repo_user = self.gitops_config.get("user")
        self._repo_fleet_url = self.gitops_config.get(
            "fleet_repo_url", f"{self._repo_base_url}/{self._repo_user}/fleet-osm.git"
        )
        self._repo_sw_catalogs_url = self.gitops_config.get(
            "sw_catalogs_repo_url",
            f"{self._repo_base_url}/{self._repo_user}/sw-catalogs-osm.git",
        )
        self._pubkey = self.gitops_config["pubkey"]
        self._workflow_debug = str(self.gitops_config["workflow_debug"]).lower()
        self._workflow_dry_run = str(self.gitops_config["workflow_dry_run"]).lower()
        self._workflows = {
            "create_cluster": {
                "workflow_function": self.create_cluster,
                "clean_function": self.clean_items_cluster_create,
            },
            "update_cluster": {
                "workflow_function": self.update_cluster,
                "clean_function": self.clean_items_cluster_update,
            },
            "delete_cluster": {
                "workflow_function": self.delete_cluster,
            },
            "register_cluster": {
                "workflow_function": self.register_cluster,
                "clean_function": self.clean_items_cluster_register,
            },
            "deregister_cluster": {
                "workflow_function": self.deregister_cluster,
            },
            "purge_cluster": {
                "workflow_function": self.purge_cluster,
                "clean_function": self.clean_items_cluster_purge,
            },
            "create_profile": {
                "workflow_function": self.create_profile,
            },
            "delete_profile": {
                "workflow_function": self.delete_profile,
            },
            "attach_profile_to_cluster": {
                "workflow_function": self.attach_profile_to_cluster,
            },
            "detach_profile_from_cluster": {
                "workflow_function": self.detach_profile_from_cluster,
            },
            "create_oka": {
                "workflow_function": self.create_oka,
                "clean_function": self.clean_items_oka_create,
            },
            "update_oka": {
                "workflow_function": self.update_oka,
                "clean_function": self.clean_items_oka_update,
            },
            "delete_oka": {
                "workflow_function": self.delete_oka,
                "clean_function": self.clean_items_oka_delete,
            },
            "create_ksus": {
                "workflow_function": self.create_ksus,
                "clean_function": self.clean_items_ksu_create,
            },
            "update_ksus": {
                "workflow_function": self.update_ksus,
                "clean_function": self.clean_items_ksu_update,
            },
            "delete_ksus": {
                "workflow_function": self.delete_ksus,
            },
            "clone_ksu": {
                "workflow_function": self.clone_ksu,
            },
            "move_ksu": {
                "workflow_function": self.move_ksu,
            },
            "create_app": {
                "workflow_function": self.create_app,
                "clean_function": self.clean_items_app_launch,
            },
            "update_app": {
                "workflow_function": self.update_app,
                "clean_function": self.clean_items_app_launch,
            },
            "delete_app": {
                "workflow_function": self.delete_app,
                "clean_function": self.clean_items_app_launch,
            },
            "create_cloud_credentials": {
                "workflow_function": self.create_cloud_credentials,
                "clean_function": self.clean_items_cloud_credentials_create,
            },
            "update_cloud_credentials": {
                "workflow_function": self.update_cloud_credentials,
                "clean_function": self.clean_items_cloud_credentials_update,
            },
            "delete_cloud_credentials": {
                "workflow_function": self.delete_cloud_credentials,
            },
            "dummy_operation": {
                "workflow_function": self.dummy_operation,
            },
            "add_nodegroup": {
                "workflow_function": self.add_nodegroup,
                "clean_function": self.clean_items_nodegroup_add,
            },
            "scale_nodegroup": {
                "workflow_function": self.scale_nodegroup,
            },
            "delete_nodegroup": {
                "workflow_function": self.delete_nodegroup,
                "clean_function": self.clean_items_nodegroup_delete,
            },
        }

        super().__init__(msg, self.logger)

    @property
    def kubeconfig(self):
        return self._kubeconfig

    # Imported methods
    create_cloud_credentials = odu_vim_mgmt.create_cloud_credentials
    update_cloud_credentials = odu_vim_mgmt.update_cloud_credentials
    delete_cloud_credentials = odu_vim_mgmt.delete_cloud_credentials
    clean_items_cloud_credentials_create = (
        odu_vim_mgmt.clean_items_cloud_credentials_create
    )
    clean_items_cloud_credentials_update = (
        odu_vim_mgmt.clean_items_cloud_credentials_update
    )
    create_cluster = odu_cluster_mgmt.create_cluster
    update_cluster = odu_cluster_mgmt.update_cluster
    delete_cluster = odu_cluster_mgmt.delete_cluster
    register_cluster = odu_cluster_mgmt.register_cluster
    deregister_cluster = odu_cluster_mgmt.deregister_cluster
    purge_cluster = odu_cluster_mgmt.purge_cluster
    clean_items_cluster_create = odu_cluster_mgmt.clean_items_cluster_create
    clean_items_cluster_update = odu_cluster_mgmt.clean_items_cluster_update
    clean_items_cluster_register = odu_cluster_mgmt.clean_items_cluster_register
    clean_items_cluster_purge = odu_cluster_mgmt.clean_items_cluster_purge
    get_cluster_credentials = odu_cluster_mgmt.get_cluster_credentials
    add_nodegroup = odu_nodegroup.add_nodegroup
    scale_nodegroup = odu_nodegroup.scale_nodegroup
    delete_nodegroup = odu_nodegroup.delete_nodegroup
    clean_items_nodegroup_add = odu_nodegroup.clean_items_nodegroup_add
    clean_items_nodegroup_delete = odu_nodegroup.clean_items_nodegroup_delete
    create_ksus = odu_ksu.create_ksus
    update_ksus = odu_ksu.update_ksus
    delete_ksus = odu_ksu.delete_ksus
    clone_ksu = odu_ksu.clone_ksu
    move_ksu = odu_ksu.move_ksu
    clean_items_ksu_create = odu_ksu.clean_items_ksu_create
    clean_items_ksu_update = odu_ksu.clean_items_ksu_update
    clean_items_ksu_delete = odu_ksu.clean_items_ksu_delete
    create_oka = odu_oka.create_oka
    update_oka = odu_oka.update_oka
    delete_oka = odu_oka.delete_oka
    clean_items_oka_create = odu_oka.clean_items_oka_create
    clean_items_oka_update = odu_oka.clean_items_oka_update
    clean_items_oka_delete = odu_oka.clean_items_oka_delete
    create_profile = odu_profiles.create_profile
    delete_profile = odu_profiles.delete_profile
    attach_profile_to_cluster = odu_profiles.attach_profile_to_cluster
    detach_profile_from_cluster = odu_profiles.detach_profile_from_cluster
    check_workflow_status = workflows.check_workflow_status
    readiness_loop = workflows.readiness_loop
    render_jinja_template = odu_render.render_jinja_template
    render_yaml_template = odu_render.render_yaml_template
    create_secret = odu_common.create_secret
    delete_secret = odu_common.delete_secret
    create_configmap = odu_common.create_configmap
    delete_configmap = odu_common.delete_configmap
    create_app = odu_app.create_app
    update_app = odu_app.update_app
    delete_app = odu_app.delete_app
    launch_app = odu_app.launch_app
    clean_items_app_launch = odu_app.clean_items_app_launch

    async def launch_workflow(self, key, op_id, op_params, content):
        self.logger.info(
            f"Workflow is getting into launch. Key: {key}. Operation: {op_id}"
        )
        # self.logger.debug(f"Operation Params: {op_params}")
        # self.logger.debug(f"Content: {content}")
        workflow_function = self._workflows[key]["workflow_function"]
        self.logger.info("workflow function : {}".format(workflow_function))
        try:
            result, workflow_name, workflow_resources = await workflow_function(
                op_id, op_params, content
            )
            return result, workflow_name, workflow_resources
        except Exception as e:
            self.logger.error(f"Error launching workflow: {e}")
            return False, str(e), None

    async def dummy_clean_items(self, op_id, op_params, content):
        self.logger.info(
            f"dummy_clean_items Enter. Operation {op_id}. Params: {op_params}"
        )
        self.logger.debug(f"Content: {content}")
        return True, "OK"

    async def clean_items_workflow(self, key, op_id, op_params, content):
        self.logger.info(
            f"Cleaning items created during workflow launch. Key: {key}. Operation: {op_id}. Params: {op_params}. Content: {content}"
        )
        clean_items_function = self._workflows[key].get(
            "clean_function", self.dummy_clean_items
        )
        self.logger.info("clean items function : {}".format(clean_items_function))
        return await clean_items_function(op_id, op_params, content)

    async def dummy_operation(self, op_id, op_params, content):
        self.logger.info("Empty operation status Enter")
        self.logger.info(f"Operation {op_id}. Params: {op_params}. Content: {content}")
        return True, content["workflow_name"], None

    async def clean_items(self, items):
        # Delete pods
        for pod in items.get("pods", []):
            name = pod["name"]
            namespace = pod["namespace"]
            self.logger.info(f"Deleting pod {name} in namespace {namespace}")
            self.logger.debug(f"Testing kubectl: {self._kubectl}")
            self.logger.debug(
                f"Testing kubectl configuration: {self._kubectl.configuration}"
            )
            self.logger.debug(
                f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
            )
            await self._kubectl.delete_pod(name, namespace)
        # Delete secrets
        for secret in items.get("secrets", []):
            name = secret["name"]
            namespace = secret["namespace"]
            self.logger.info(f"Deleting secret {name} in namespace {namespace}")
            self.logger.debug(f"Testing kubectl: {self._kubectl}")
            self.logger.debug(
                f"Testing kubectl configuration: {self._kubectl.configuration}"
            )
            self.logger.debug(
                f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
            )
            self.delete_secret(name, namespace)
        # Delete pvcs
        for pvc in items.get("pvcs", []):
            name = pvc["name"]
            namespace = pvc["namespace"]
            self.logger.info(f"Deleting pvc {name} in namespace {namespace}")
            self.logger.debug(f"Testing kubectl: {self._kubectl}")
            self.logger.debug(
                f"Testing kubectl configuration: {self._kubectl.configuration}"
            )
            self.logger.debug(
                f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
            )
            await self._kubectl.delete_pvc(name, namespace)
        # Delete configmaps
        for configmap in items.get("configmaps", []):
            name = configmap["name"]
            namespace = configmap["namespace"]
            self.logger.info(f"Deleting configmap {name} in namespace {namespace}")
            self.logger.debug(f"Testing kubectl: {self._kubectl}")
            self.logger.debug(
                f"Testing kubectl configuration: {self._kubectl.configuration}"
            )
            self.logger.debug(
                f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
            )
            self.delete_configmap(name, namespace)

    async def list_object(self, api_group, api_plural, api_version):
        self.logger.info(
            f"Api group: {api_group} Api plural: {api_plural} Api version: {api_version}"
        )
        generic_object = await self._kubectl.list_generic_object(
            api_group=api_group,
            api_plural=api_plural,
            api_version=api_version,
            namespace="",
        )
        return generic_object
