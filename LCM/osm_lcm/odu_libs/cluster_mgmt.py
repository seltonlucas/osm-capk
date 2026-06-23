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
import base64
import json


def gather_age_key(cluster):
    pubkey = cluster.get("age_pubkey")
    privkey = cluster.get("age_privkey")
    # return both public and private key
    return pubkey, privkey


async def create_cluster(self, op_id, op_params, content):
    self.logger.info(f"create_cluster Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]
    db_vim_account = content["vim_account"]

    workflow_template = "launcher-create-crossplane-cluster-and-bootstrap.j2"
    workflow_name = f"create-cluster-{db_cluster['_id']}"
    cluster_name = db_cluster["git_name"].lower()

    # Get age key
    public_key_new_cluster, private_key_new_cluster = gather_age_key(db_cluster)
    # self.logger.debug(f"public_key_new_cluster={public_key_new_cluster}")
    # self.logger.debug(f"private_key_new_cluster={private_key_new_cluster}")

    # Test kubectl connection
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self.logger.debug(self._kubectl._get_kubectl_version())

    # Create temporal secret with agekey
    secret_name = f"secret-age-{cluster_name}"
    secret_namespace = "osm-workflows"
    secret_key = "agekey"
    secret_value = private_key_new_cluster
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
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
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from content
    vim_account_id = db_cluster["vim_account"]
    providerconfig_name = f"{vim_account_id}-config"
    vim_type = db_vim_account["vim_type"]
    if db_cluster.get("bootstrap", True):
        skip_bootstrap = "false"
    else:
        skip_bootstrap = "true"
    # CAPK/KubeVirt clusters are provisioned by Cluster API on the OSM management
    # cluster itself (as KubeVirt VMs), not on an external cloud, so they use a
    # dedicated launcher + workflow. cluster_type is informational here.
    if vim_type == "kubevirt":
        cluster_type = "kubevirt"
        workflow_template = "launcher-create-capi-kubevirt-cluster-and-bootstrap.j2"
    elif vim_type == "azure":
        cluster_type = "aks"
    elif vim_type == "aws":
        cluster_type = "eks"
    elif vim_type == "gcp":
        cluster_type = "gke"
    else:
        raise Exception("Not suitable VIM account to create cluster")

    # Create configmap for subnet
    configmap_name = None
    data = {}
    private_subnets = op_params.get("private_subnet")
    public_subnets = op_params.get("public_subnet")
    if private_subnets or public_subnets:
        configmap_name = f"{cluster_name}-parameters"
        configmap_namespace = "managed-resources"
        data["private_subnets"] = f"{json.dumps(private_subnets)}"
        data["public_subnets"] = f"{json.dumps(public_subnets)}"
        try:
            self.logger.debug(f"Testing kubectl: {self._kubectl}")
            self.logger.debug(
                f"Testing kubectl configuration: {self._kubectl.configuration}"
            )
            self.logger.debug(
                f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
            )
            await self.create_configmap(
                configmap_name,
                configmap_namespace,
                data,
            )
        except Exception as e:
            self.logger.info(f"Cannot create configmap {configmap_name}: {e}")
            return False, f"Cannot create configmap {configmap_name}: {e}", None

    # Render workflow
    # workflow_kwargs = {
    #     "git_fleet_url": self._repo_fleet_url,
    #     "git_sw_catalogs_url": self._repo_sw_catalogs_url,
    # }
    # manifest = self.render_jinja_template(
    #     workflow_template,
    #     output_file=None,
    #     **workflow_kwargs
    # )
    if vim_type == "kubevirt":
        # CAPK launcher: KubeVirt sizing/network params, no cloud parameters.
        # CAPK-specific values are overridable per-cluster via `--config`
        # (stored in db_cluster); otherwise the workflow-template defaults apply.
        manifest = self.render_jinja_template(
            workflow_template,
            output_file=None,
            workflow_name=workflow_name,
            git_fleet_url=self._repo_fleet_url,
            git_sw_catalogs_url=self._repo_sw_catalogs_url,
            cluster_name=cluster_name,
            cluster_kustomization_name=cluster_kustomization_name,
            public_key_mgmt=self._pubkey,
            public_key_new_cluster=public_key_new_cluster,
            secret_name_private_key_new_cluster=secret_name,
            node_count=db_cluster.get("node_count", "1"),
            k8s_version=db_cluster["k8s_version"],
            osm_project_name=osm_project_name,
            skip_bootstrap=skip_bootstrap,
            control_plane_node_count=db_cluster.get("control_plane_node_count", "1"),
            control_plane_cpu_cores=db_cluster.get("control_plane_cpu_cores", "2"),
            control_plane_memory=db_cluster.get("control_plane_memory", "4Gi"),
            control_plane_ephemeral_storage=db_cluster.get(
                "control_plane_ephemeral_storage", "2Gi"
            ),
            worker_cpu_cores=db_cluster.get("worker_cpu_cores", "2"),
            worker_memory=db_cluster.get("worker_memory", "4Gi"),
            worker_ephemeral_storage=db_cluster.get("worker_ephemeral_storage", "2Gi"),
            vm_image=db_cluster.get("vm_image")
            or f"quay.io/capk/ubuntu-2204-container-disk:v{db_cluster['k8s_version']}",
            pod_cidr=db_cluster.get("pod_cidr", "10.243.0.0/16"),
            service_cidr=db_cluster.get("service_cidr", "10.95.0.0/16"),
            cluster_cni=db_cluster.get("cluster_cni", "calico"),
            capk_resources_namespace=db_cluster.get(
                "capk_resources_namespace", "default"
            ),
            workflow_debug=self._workflow_debug,
            workflow_dry_run=self._workflow_dry_run,
        )
    else:
        manifest = self.render_jinja_template(
            workflow_template,
            output_file=None,
            workflow_name=workflow_name,
            git_fleet_url=self._repo_fleet_url,
            git_sw_catalogs_url=self._repo_sw_catalogs_url,
            cluster_name=cluster_name,
            cluster_type=cluster_type,
            cluster_kustomization_name=cluster_kustomization_name,
            providerconfig_name=providerconfig_name,
            public_key_mgmt=self._pubkey,
            public_key_new_cluster=public_key_new_cluster,
            secret_name_private_key_new_cluster=secret_name,
            vm_size=db_cluster.get("node_size", "default"),
            node_count=db_cluster.get("node_count", "default"),
            k8s_version=db_cluster["k8s_version"],
            cluster_location=db_cluster["region_name"],
            configmap_name=configmap_name if configmap_name else "default",
            cluster_iam_role=db_cluster.get("iam_role", "default"),
            cluster_private_subnets_id=db_cluster.get("private_subnet", "default"),
            cluster_public_subnets_id=db_cluster.get("public_subnet", "default"),
            osm_project_name=osm_project_name,
            rg_name=db_cluster.get("resource_group", "''"),
            preemptible_nodes=db_cluster.get("preemptible_nodes", "false"),
            skip_bootstrap=skip_bootstrap,
            workflow_debug=self._workflow_debug,
            workflow_dry_run=self._workflow_dry_run,
        )
    # self.logger.debug(f"Workflow manifest: {manifest}")

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def update_cluster(self, op_id, op_params, content):
    self.logger.info(f"update_cluster Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]
    db_vim_account = content["vim_account"]
    cluster_name = db_cluster["git_name"].lower()

    workflow_template = "launcher-update-crossplane-cluster.j2"
    workflow_name = f"update-cluster-{op_id}"
    # cluster_name = db_cluster["name"].lower()

    # Get age key
    public_key_cluster, private_key_cluster = gather_age_key(db_cluster)
    self.logger.debug(f"public_key_new_cluster={public_key_cluster}")
    self.logger.debug(f"private_key_new_cluster={private_key_cluster}")

    # Create secret with agekey
    secret_name = f"secret-age-{cluster_name}"
    secret_namespace = "osm-workflows"
    secret_key = "agekey"
    secret_value = private_key_cluster
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
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
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from db_cluster
    vim_account_id = db_cluster["vim_account"]
    providerconfig_name = f"{vim_account_id}-config"
    vim_type = db_vim_account["vim_type"]
    vm_size = op_params.get("node_size", db_cluster["node_size"])
    node_count = op_params.get("node_count", db_cluster["node_count"])
    k8s_version = op_params.get("k8s_version", db_cluster["k8s_version"])
    if vim_type == "kubevirt":
        cluster_type = "kubevirt"
        workflow_template = "launcher-update-capi-kubevirt-cluster.j2"
    elif vim_type == "azure":
        cluster_type = "aks"
    elif vim_type == "aws":
        cluster_type = "eks"
    elif vim_type == "gcp":
        cluster_type = "gke"
    else:
        raise Exception("Not suitable VIM account to update cluster")

    # Render workflow
    if vim_type == "kubevirt":
        # Day-2 for CAPK: op_params override the stored values (scale node_count,
        # change k8s_version, resize VMs); fall back to the cluster's current spec.
        manifest = self.render_jinja_template(
            workflow_template,
            output_file=None,
            workflow_name=workflow_name,
            git_fleet_url=self._repo_fleet_url,
            git_sw_catalogs_url=self._repo_sw_catalogs_url,
            cluster_name=cluster_name,
            cluster_kustomization_name=cluster_kustomization_name,
            public_key_mgmt=self._pubkey,
            public_key_new_cluster=public_key_cluster,
            secret_name_private_key_new_cluster=secret_name,
            node_count=node_count,
            k8s_version=k8s_version,
            osm_project_name=osm_project_name,
            control_plane_node_count=op_params.get(
                "control_plane_node_count",
                db_cluster.get("control_plane_node_count", "1"),
            ),
            control_plane_cpu_cores=op_params.get(
                "control_plane_cpu_cores", db_cluster.get("control_plane_cpu_cores", "2")
            ),
            control_plane_memory=op_params.get(
                "control_plane_memory", db_cluster.get("control_plane_memory", "4Gi")
            ),
            control_plane_ephemeral_storage=op_params.get(
                "control_plane_ephemeral_storage",
                db_cluster.get("control_plane_ephemeral_storage", "2Gi"),
            ),
            worker_cpu_cores=op_params.get(
                "worker_cpu_cores", db_cluster.get("worker_cpu_cores", "2")
            ),
            worker_memory=op_params.get(
                "worker_memory", db_cluster.get("worker_memory", "4Gi")
            ),
            worker_ephemeral_storage=op_params.get(
                "worker_ephemeral_storage",
                db_cluster.get("worker_ephemeral_storage", "2Gi"),
            ),
            vm_image=op_params.get("vm_image")
            or db_cluster.get("vm_image")
            or f"quay.io/capk/ubuntu-2204-container-disk:v{k8s_version}",
            pod_cidr=db_cluster.get("pod_cidr", "10.243.0.0/16"),
            service_cidr=db_cluster.get("service_cidr", "10.95.0.0/16"),
            cluster_cni=db_cluster.get("cluster_cni", "calico"),
            capk_resources_namespace=db_cluster.get(
                "capk_resources_namespace", "default"
            ),
            workflow_debug=self._workflow_debug,
            workflow_dry_run=self._workflow_dry_run,
        )
    else:
        manifest = self.render_jinja_template(
            workflow_template,
            output_file=None,
            workflow_name=workflow_name,
            git_fleet_url=self._repo_fleet_url,
            git_sw_catalogs_url=self._repo_sw_catalogs_url,
            cluster_name=cluster_name,
            cluster_type=cluster_type,
            cluster_kustomization_name=cluster_kustomization_name,
            providerconfig_name=providerconfig_name,
            public_key_mgmt=self._pubkey,
            public_key_new_cluster=public_key_cluster,
            secret_name_private_key_new_cluster=secret_name,
            vm_size=vm_size,
            node_count=node_count,
            k8s_version=k8s_version,
            cluster_location=db_cluster["region_name"],
            osm_project_name=osm_project_name,
            rg_name=db_cluster.get("resource_group", "''"),
            preemptible_nodes=db_cluster.get("preemptible_nodes", "false"),
            workflow_debug=self._workflow_debug,
            workflow_dry_run=self._workflow_dry_run,
        )
    # self.logger.info(manifest)

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def delete_cluster(self, op_id, op_params, content):
    self.logger.info(f"delete_cluster Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]

    workflow_template = "launcher-delete-cluster.j2"
    workflow_name = f"delete-cluster-{db_cluster['_id']}"
    # cluster_name = db_cluster["name"].lower()
    cluster_name = db_cluster["git_name"].lower()

    # Additional params for the workflow
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from DB

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        cluster_name=cluster_name,
        cluster_kustomization_name=cluster_kustomization_name,
        osm_project_name=osm_project_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    # self.logger.info(manifest)

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def register_cluster(self, op_id, op_params, content):
    self.logger.info(f"register_cluster Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]
    cluster_name = db_cluster["git_name"].lower()

    workflow_template = "launcher-bootstrap-cluster.j2"
    workflow_name = f"register-cluster-{db_cluster['_id']}"

    # Get age key
    public_key_new_cluster, private_key_new_cluster = gather_age_key(db_cluster)
    self.logger.debug(f"public_key_new_cluster={public_key_new_cluster}")
    self.logger.debug(f"private_key_new_cluster={private_key_new_cluster}")

    # Create temporal secret with agekey
    secret_name = f"secret-age-{cluster_name}"
    secret_namespace = "osm-workflows"
    secret_key = "agekey"
    secret_value = private_key_new_cluster
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
        await self.create_secret(
            secret_name,
            secret_namespace,
            secret_key,
            secret_value,
        )
    except Exception as e:
        self.logger.info(
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}"
        )
        return (
            False,
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}",
            None,
        )

    # Create secret with kubeconfig
    secret_name2 = f"kubeconfig-{cluster_name}"
    secret_namespace2 = "managed-resources"
    secret_key2 = "kubeconfig"
    secret_value2 = yaml.safe_dump(
        db_cluster["credentials"], indent=2, default_flow_style=False, sort_keys=False
    )
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
        await self.create_secret(
            secret_name2,
            secret_namespace2,
            secret_key2,
            secret_value2,
        )
    except Exception as e:
        self.logger.info(
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}"
        )
        return (
            False,
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}",
            None,
        )

    # Additional params for the workflow
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from content
    if db_cluster.get("openshift", True):
        templates_dir = "/sw-catalogs/sw-catalogs-osm/cloud-resources/flux-remote-bootstrap/cluster-base-openshift/templates"
        self.logger.info(
            "Rendering OpenShift bootstrap templates from %s", templates_dir
        )
    else:
        templates_dir = "/sw-catalogs/sw-catalogs-osm/cloud-resources/flux-remote-bootstrap/cluster-base/templates"
        self.logger.info(
            "Rendering Standard bootstrap templates from %s", templates_dir
        )

    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        cluster_name=cluster_name,
        cluster_kustomization_name=cluster_kustomization_name,
        public_key_mgmt=self._pubkey,
        public_key_new_cluster=public_key_new_cluster,
        secret_name_private_key_new_cluster=secret_name,
        osm_project_name=osm_project_name,
        templates_dir=templates_dir,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    # self.logger.debug(f"Workflow manifest: {manifest}")

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def deregister_cluster(self, op_id, op_params, content):
    self.logger.info(
        f"deregister_cluster Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]
    cluster_name = db_cluster["git_name"].lower()

    workflow_template = "launcher-disconnect-flux-remote-cluster.j2"
    workflow_name = f"deregister-cluster-{db_cluster['_id']}"

    # Create secret with kubeconfig
    secret_name = f"kubeconfig-{cluster_name}"
    secret_namespace = "osm-workflows"
    secret_key = "kubeconfig"
    secret_value = yaml.safe_dump(
        db_cluster["credentials"], indent=2, default_flow_style=False, sort_keys=False
    )
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
        await self.create_secret(
            secret_name,
            secret_namespace,
            secret_key,
            secret_value,
        )
    except Exception as e:
        self.logger.info(
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}"
        )
        return (
            False,
            f"Cannot create secret {secret_name} in namespace {secret_namespace}: {e}",
            None,
        )

    # Additional params for the workflow
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from DB

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        cluster_kustomization_name=cluster_kustomization_name,
        osm_project_name=osm_project_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    # self.logger.info(manifest)

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def purge_cluster(self, op_id, op_params, content):
    self.logger.info(f"purge_cluster Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    db_cluster = content["cluster"]
    cluster_name = db_cluster["git_name"].lower()

    workflow_template = "launcher-purge-delete-cluster.yaml.j2"
    workflow_name = f"purge-cluster-{db_cluster['_id']}"

    # Create secret with kubeconfig
    temp_kubeconfig_secret_name = f"kubeconfig-{cluster_name}"

    # Additional params for the workflow
    cluster_kustomization_name = cluster_name
    osm_project_name = "osm_admin"  # TODO: get project name from DB

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        cluster_kustomization_name=cluster_kustomization_name,
        osm_project_name=osm_project_name,
        temp_kubeconfig_secret_name=temp_kubeconfig_secret_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    # self.logger.info(manifest)

    # Submit workflow
    self.logger.debug(f"Testing kubectl: {self._kubectl}")
    self.logger.debug(f"Testing kubectl configuration: {self._kubectl.configuration}")
    self.logger.debug(
        f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
    )
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def get_cluster_credentials(self, db_cluster):
    """
    returns the kubeconfig file of a K8s cluster in a dictionary
    """
    self.logger.info("get_cluster_credentials Enter")
    # self.logger.debug(f"Content: {db_cluster}")

    secret_name = f"kubeconfig-{db_cluster['git_name'].lower()}"
    secret_namespace = "managed-resources"
    secret_key = "kubeconfig"

    self.logger.info(f"Checking content of secret {secret_name} ...")
    try:
        returned_secret_data = await self._kubectl.get_secret_content(
            name=secret_name,
            namespace=secret_namespace,
        )
        returned_secret_value = base64.b64decode(
            returned_secret_data[secret_key]
        ).decode("utf-8")
        return True, yaml.safe_load(returned_secret_value)
    except Exception as e:
        message = f"Not possible to get the credentials of the cluster. Exception: {e}"
        self.logger.critical(message)
        return False, message


async def clean_items_cluster_create(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cluster_create Enter. Operation {op_id}. Params: {op_params}"
    )
    self.logger.debug(f"Content: {content}")
    items = {
        "secrets": [
            {
                "name": f"secret-age-{content['cluster']['git_name'].lower()}",
                "namespace": "osm-workflows",
            }
        ],
        # "configmaps": [
        #    {
        #        "name": f"{content['cluster']['name']}-parameters",
        #        "namespace": "managed-resources",
        #    }
        # ],
    }
    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_cluster_update(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cluster_update Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")
    return await self.clean_items_cluster_create(op_id, op_params, content)


async def clean_items_cluster_register(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cluster_register Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")
    # Clean secrets
    cluster_name = content["cluster"]["git_name"].lower()
    items = {
        "secrets": [
            {
                "name": f"secret-age-{cluster_name}",
                "namespace": "osm-workflows",
            },
        ]
    }

    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_cluster_purge(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cluster_purge Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")
    # Clean secrets
    self.logger.info("Cleaning kubeconfig")
    cluster_name = content["cluster"]["git_name"].lower()
    items = {
        "secrets": [
            {
                "name": f"kubeconfig-{cluster_name}",
                "namespace": "osm-workflows",
            },
            {
                "name": f"kubeconfig-{cluster_name}",
                "namespace": "managed-resources",
            },
        ]
    }

    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"
