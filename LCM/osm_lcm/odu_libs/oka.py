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


MAP_PROFILE = {
    "infra_controller_profiles": "infra-controllers",
    "infra_config_profiles": "infra-configs",
    "resource_profiles": "managed_resources",
    "app_profiles": "apps",
}


async def create_oka(self, op_id, op_params, content):
    self.logger.info(f"create_oka Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-create-oka.j2"
    workflow_name = f"create-oka-{content['_id']}"

    # Additional params for the workflow
    oka_name = content["git_name"].lower()
    oka_type = MAP_PROFILE[content.get("profile_type", "infra_controller_profiles")]
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Get the OKA package
    oka_fs_info = content["_admin"]["storage"]
    oka_folder = f"{oka_fs_info['path']}{oka_fs_info['folder']}"
    oka_filename = oka_fs_info["zipfile"]
    self.fs.sync(oka_folder)
    self.logger.info("OKA Folder: {} OKA filename: {}".format(oka_folder, oka_filename))
    # TODO: check if file exists
    # if not self.fs.file_exists(f"{oka_folder}/{oka_filename}"):
    #     raise LcmException(message="Not able to find oka", bad_args=["oka_path"])
    self.logger.debug("Processing....")

    # Create temporary volume for the OKA package and copy the content
    temp_volume_name = f"temp-pvc-oka-{op_id}"
    await self._kubectl.create_pvc_with_content(
        name=temp_volume_name,
        namespace="osm-workflows",
        src_files=[f"{oka_folder}/{oka_filename}"],
        dest_files=[f"{oka_name}.tar.gz"],
    )

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        oka_name=oka_name,
        oka_type=oka_type,
        osm_project_name=osm_project_name,
        temp_volume_name=temp_volume_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.info(manifest)

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def update_oka(self, op_id, op_params, content):
    self.logger.info(f"update_oka Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-update-oka.j2"
    workflow_name = f"update-oka-{content['_id']}"

    # Additional params for the workflow
    oka_name = content["git_name"].lower()
    oka_type = MAP_PROFILE[content.get("profile_type", "infra_controller_profiles")]
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Get the OKA package
    oka_fs_info = content["_admin"]["storage"]
    oka_folder = (
        f"{oka_fs_info['path']}/{oka_fs_info['folder']}/{oka_fs_info['zipfile']}"
    )
    oka_filename = "package.tar.gz"
    # Sync fs?

    # Create temporary volume for the OKA package and copy the content
    temp_volume_name = f"temp-pvc-oka-{op_id}"
    await self._kubectl.create_pvc_with_content(
        name=temp_volume_name,
        namespace="osm-workflows",
        src_files=[f"{oka_folder}/{oka_filename}"],
        dest_files=[f"{oka_name}.tar.gz"],
    )

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        oka_name=oka_name,
        oka_type=oka_type,
        osm_project_name=osm_project_name,
        temp_volume_name=temp_volume_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.info(manifest)

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def delete_oka(self, op_id, op_params, content):
    self.logger.info(f"delete_oka Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-delete-oka.j2"
    workflow_name = f"delete-oka-{content['_id']}"

    # Additional params for the workflow
    oka_name = content["git_name"].lower()
    oka_type = MAP_PROFILE[content.get("profile_type", "infra_controller_profiles")]

    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        oka_name=oka_name,
        oka_type=oka_type,
        osm_project_name=osm_project_name,
        workflow_debug=self._workflow_debug,
        workflow_dry_run=self._workflow_dry_run,
    )
    self.logger.info(manifest)

    # Submit workflow
    self._kubectl.create_generic_object(
        namespace="osm-workflows",
        manifest_dict=yaml.safe_load(manifest),
        api_group="argoproj.io",
        api_plural="workflows",
        api_version="v1alpha1",
    )
    return True, workflow_name, None


async def clean_items_oka_create(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_oka_create Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    volume_name = f"temp-pvc-oka-{op_id}"
    try:
        items = {
            "pvcs": [
                {
                    "name": volume_name,
                    "namespace": "osm-workflows",
                }
            ],
        }
        await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_oka_update(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_oka_update Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    return await self.clean_items_oka_create(op_id, op_params_list, content_list)


async def clean_items_oka_delete(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_oka_delete Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    return True, "OK"
