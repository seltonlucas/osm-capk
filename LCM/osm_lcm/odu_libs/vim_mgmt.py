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


import base64
import json
import yaml
from osm_lcm.lcm_utils import LcmException


async def create_cloud_credentials(self, op_id, op_params, content):
    self.logger.info(
        f"create_cloud_credentials Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-create-providerconfig.j2"
    workflow_name = f"create-providerconfig-{content['_id']}"
    # vim_name = content["name"].lower()
    vim_name = content.get("git_name", content["name"]).lower()
    # workflow_name = f"{op_id}-create-credentials-{vim_name}"

    # Test kubectl connection
    self.logger.debug(self._kubectl._get_kubectl_version())

    # Create secret with creds
    secret_name = workflow_name
    secret_namespace = "osm-workflows"
    secret_key = "creds"
    cloud_config = content.get("config", {})
    if "credentials_base64" in cloud_config:
        secret_value = base64.b64decode(cloud_config["credentials_base64"]).decode(
            "utf-8"
        )
    elif "credentials" in cloud_config:
        secret_value = json.dumps(cloud_config["credentials"], indent=2)
    else:
        raise LcmException("No credentials in VIM/cloud config")
    await self.create_secret(
        secret_name,
        secret_namespace,
        secret_key,
        secret_value,
    )

    # Additional params for the workflow
    providerconfig_name = f"{vim_name}-config"
    provider_type = content["vim_type"]
    osm_project_name = "osm_admin"  # TODO: get project name from content
    if provider_type == "gcp":
        vim_tenant = content["vim_tenant_name"]
    else:
        vim_tenant = ""

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        providerconfig_name=providerconfig_name,
        provider_type=provider_type,
        cred_secret_name=vim_name,
        temp_cred_secret_name=secret_name,
        public_key_mgmt=self._pubkey,
        osm_project_name=osm_project_name,
        target_gcp_project=vim_tenant,
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
    return True, workflow_name


async def delete_cloud_credentials(self, op_id, op_params, content):
    self.logger.info(
        f"delete_cloud_credentials Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-delete-providerconfig.j2"
    workflow_name = f"delete-providerconfig-{content['_id']}"
    # vim_name = content["name"].lower()
    vim_name = content.get("git_name", content["name"]).lower()
    # workflow_name = f"{op_id}-delete-credentials-{vim_name}"

    # Additional params for the workflow
    providerconfig_name = f"{vim_name}-config"
    provider_type = content["vim_type"]
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        providerconfig_name=providerconfig_name,
        provider_type=provider_type,
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
    return True, workflow_name


async def update_cloud_credentials(self, op_id, op_params, content):
    self.logger.info(
        f"update_cloud_credentials Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-update-providerconfig.j2"
    workflow_name = f"update-providerconfig-{content['_id']}"
    # vim_name = content["name"].lower()
    vim_name = content.get("git_name", content["name"]).lower()
    # workflow_name = f"{op_id}-update-credentials-{vim_name}"

    # Create secret with creds
    secret_name = workflow_name
    secret_namespace = "osm-workflows"
    secret_key = "creds"
    cloud_config = content.get("config", {})
    if "credentials_base64" in cloud_config:
        secret_value = base64.b64decode(cloud_config["credentials_base64"]).decode(
            "utf-8"
        )
    elif "credentials" in cloud_config:
        secret_value = json.dumps(cloud_config["credentials"], indent=2)
    else:
        raise LcmException("No credentials in VIM/cloud config")
    await self.create_secret(
        secret_name,
        secret_namespace,
        secret_key,
        secret_value,
    )

    # Additional params for the workflow
    providerconfig_name = f"{vim_name}-config"
    provider_type = content["vim_type"]
    osm_project_name = "osm_admin"  # TODO: get project name from content
    if provider_type == "gcp":
        vim_tenant = content["vim_tenant_name"]
    else:
        vim_tenant = ""

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        providerconfig_name=providerconfig_name,
        provider_type=provider_type,
        cred_secret_name=vim_name,
        temp_cred_secret_name=secret_name,
        public_key_mgmt=self._pubkey,
        osm_project_name=osm_project_name,
        target_gcp_project=vim_tenant,
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
    return True, workflow_name


async def clean_items_cloud_credentials_create(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cloud_credentials_create Enter. Operation {op_id}. Params: {op_params}"
    )
    items = {
        "secrets": [
            {
                "name": f"create-providerconfig-{content['_id']}",
                "namespace": "osm-workflows",
            }
        ]
    }
    try:
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_cloud_credentials_update(self, op_id, op_params, content):
    self.logger.info(
        f"clean_items_cloud_credentials_update Enter. Operation {op_id}. Params: {op_params}"
    )
    return await self.clean_items_cloud_credentials_create(op_id, op_params, content)
