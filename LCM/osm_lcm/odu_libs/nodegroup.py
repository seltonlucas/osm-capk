#######################################################################################
# Copyright ETSI Contributors and Others.
#
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


import yaml
import json


def gather_age_key(cluster):
    pubkey = cluster.get("age_pubkey")
    privkey = cluster.get("age_privkey")
    # return both public and private key
    return pubkey, privkey


async def add_nodegroup(self, op_id, op_params, content):
    self.logger.info(f"Add Nodegroup Enter. Operation {op_id}. Params: {op_params}")

    db_nodegroup = content["nodegroup"]
    db_cluster = content["cluster"]
    db_vim_account = content["vim_account"]

    workflow_template = "launcher-add-nodegroup.j2"
    workflow_name = f"add-nodegroup-{db_nodegroup['_id']}"
    nodegroup_name = db_nodegroup["git_name"].lower()
    cluster_name = db_cluster["git_name"].lower()
    configmap_name = f"{nodegroup_name}-subnet-parameters"

    # Get age key
    public_key_new_cluster, private_key_new_cluster = gather_age_key(db_cluster)

    # Test kubectl connection
    self.logger.debug(self._kubectl._get_kubectl_version())

    # Create temporal secret with agekey
    secret_name = f"secret-age-{nodegroup_name}"
    secret_namespace = "osm-workflows"
    secret_key = "agekey"
    secret_value = private_key_new_cluster
    try:
        await self.create_secret(
            secret_name,
            secret_namespace,
            secret_key,
            secret_value,
        )
    except Exception as e:
        self.logger.info(f"Cannot create secret {secret_name}: {e}")
        return False, f"Cannot create secret {secret_name}: {e}", None

    private_subnet = op_params.get("private_subnet", [])
    public_subnet = op_params.get("public_subnet", [])
    subnet = private_subnet + public_subnet
    self.logger.info(f"Subnets: {subnet}")
    formatted_subnet = f"{json.dumps(subnet)}"
    # self.logger.info(f"Formatted Subnet: {formatted_subnet}")
    # Create the ConfigMap for the subnets
    # TODO: this should be done in a declarative way, not imperative
    try:
        await self.create_configmap(
            configmap_name,
            "managed-resources",
            {"subnet": formatted_subnet},
        )
    except Exception as e:
        self.logger.info(f"Cannot create configmap {configmap_name}: {e}")
        return False, f"Cannot create configmap {configmap_name}: {e}", None

    # Additional params for the workflow
    nodegroup_kustomization_name = nodegroup_name
    osm_project_name = "osm_admin"  # TODO: get project name from content
    vim_account_id = db_cluster["vim_account"]
    providerconfig_name = f"{vim_account_id}-config"
    vim_type = db_vim_account["vim_type"]
    if db_cluster.get("bootstrap", True):
        skip_bootstrap = "false"
    else:
        skip_bootstrap = "true"
    if vim_type == "azure":
        cluster_type = "aks"
    elif vim_type == "aws":
        cluster_type = "eks"
    elif vim_type == "gcp":
        cluster_type = "gke"
    else:
        raise Exception("Not suitable VIM account to register cluster")

    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=f"{self._repo_base_url}/{self._repo_user}/fleet-osm.git",
        git_sw_catalogs_url=f"{self._repo_base_url}/{self._repo_user}/sw-catalogs-osm.git",
        nodegroup_name=nodegroup_name,
        nodegroup_kustomization_name=nodegroup_kustomization_name,
        cluster_name=cluster_name,
        cluster_type=cluster_type,
        role=db_nodegroup.get("iam_role", "default"),
        providerconfig_name=providerconfig_name,
        public_key_mgmt=self._pubkey,
        public_key_new_cluster=public_key_new_cluster,
        secret_name_private_key_new_cluster=secret_name,
        configmap_name=configmap_name,
        vm_size=db_nodegroup["node_size"],
        node_count=db_nodegroup["node_count"],
        cluster_location=db_cluster["region_name"],
        osm_project_name=osm_project_name,
        rg_name=db_cluster.get("resource_group", "''"),
        preemptible_nodes=db_cluster.get("preemptible_nodes", "false"),
        skip_bootstrap=skip_bootstrap,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.debug(f"Workflow manifest: {manifest}")

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def scale_nodegroup(self, op_id, op_params, content):
    self.logger.info(f"Scale nodegroup Enter. Operation {op_id}. Params: {op_params}")

    db_nodegroup = content["nodegroup"]
    db_cluster = content["cluster"]
    db_vim_account = content["vim_account"]

    workflow_template = "launcher-scale-nodegroup.j2"
    workflow_name = f"scale-nodegroup-{db_nodegroup['_id']}"
    nodegroup_name = db_nodegroup["git_name"].lower()
    cluster_name = db_cluster["git_name"].lower()

    # Get age key
    public_key_new_cluster, private_key_new_cluster = gather_age_key(db_cluster)

    # Test kubectl connection
    self.logger.debug(self._kubectl._get_kubectl_version())

    # Create temporal secret with agekey
    secret_name = f"secret-age-{nodegroup_name}"
    secret_namespace = "osm-workflows"
    secret_key = "agekey"
    secret_value = private_key_new_cluster
    try:
        await self.create_secret(
            secret_name,
            secret_namespace,
            secret_key,
            secret_value,
        )
    except Exception as e:
        self.logger.info(f"Cannot create secret {secret_name}: {e}")
        return False, f"Cannot create secret {secret_name}: {e}", None

    # Additional params for the workflow
    nodegroup_kustomization_name = nodegroup_name
    osm_project_name = "osm_admin"  # TODO: get project name from content
    vim_type = db_vim_account["vim_type"]
    if vim_type == "azure":
        cluster_type = "aks"
    elif vim_type == "aws":
        cluster_type = "eks"
    elif vim_type == "gcp":
        cluster_type = "gke"
    else:
        raise Exception("Not suitable VIM account to register cluster")

    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=f"{self._repo_base_url}/{self._repo_user}/fleet-osm.git",
        git_sw_catalogs_url=f"{self._repo_base_url}/{self._repo_user}/sw-catalogs-osm.git",
        nodegroup_name=nodegroup_name,
        nodegroup_kustomization_name=nodegroup_kustomization_name,
        cluster_name=cluster_name,
        cluster_type=cluster_type,
        node_count=op_params["node_count"],
        public_key_mgmt=self._pubkey,
        public_key_new_cluster=public_key_new_cluster,
        secret_name_private_key_new_cluster=secret_name,
        osm_project_name=osm_project_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.debug(f"Workflow manifest: {manifest}")

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def delete_nodegroup(self, op_id, op_params, content):
    self.logger.info(f"Delete nodegroup Enter. Operation {op_id}. Params: {op_params}")

    db_nodegroup = content["nodegroup"]
    db_cluster = content["cluster"]

    workflow_template = "launcher-delete-nodegroup.j2"
    workflow_name = f"delete-nodegroup-{db_nodegroup['_id']}"
    nodegroup_name = db_nodegroup["git_name"].lower()

    # Additional params for the workflow
    nodegroup_kustomization_name = nodegroup_name
    osm_project_name = "osm_admin"  # TODO: get project name from DB

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=f"{self._repo_base_url}/{self._repo_user}/fleet-osm.git",
        git_sw_catalogs_url=f"{self._repo_base_url}/{self._repo_user}/sw-catalogs-osm.git",
        nodegroup_name=nodegroup_name,
        cluster_name=db_cluster["name"],
        nodegroup_kustomization_name=nodegroup_kustomization_name,
        osm_project_name=osm_project_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.info(f"Workflow Manifest: {manifest}")

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def clean_items_nodegroup_add(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_nodegroup_add Enter. Operation {op_id}. Params: {op_params}"
    )
    items = {
        "secrets": [
            {
                "name": f"secret-age-{content['nodegroup']['git_name'].lower()}",
                "namespace": "osm-workflows",
            }
        ],
    }
    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_nodegroup_delete(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_nodegroup_delete Enter. Operation {op_id}. Params: {op_params}"
    )
    self.logger.info(
        f"clean_items_nodegroup_delete Enter. Operation {op_id}. Params: {op_params}"
    )
    self.logger.debug(f"Content: {content}")
    items = {
        "configmaps": [
            {
                "name": f"{content['nodegroup']['git_name'].lower()}-subnet-parameters",
                "namespace": "managed-resources",
            }
        ],
    }
    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"
