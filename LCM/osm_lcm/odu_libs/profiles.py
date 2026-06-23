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


async def create_profile(self, op_id, op_params, content):
    self.logger.info(f"create_profile Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-create-profile.j2"
    workflow_name = f"create-profile-{content['_id']}"

    # Additional params for the workflow
    profile_name = content["git_name"].lower()
    profile_type = content["profile_type"]
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        profile_name=profile_name,
        profile_type=profile_type,
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
    return True, workflow_name


async def delete_profile(self, op_id, op_params, content):
    self.logger.info(f"delete_profile Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")

    workflow_template = "launcher-delete-profile.j2"
    workflow_name = f"delete-profile-{content['_id']}"

    # Additional params for the workflow
    profile_name = content["git_name"].lower()
    profile_type = content["profile_type"]
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        profile_name=profile_name,
        profile_type=profile_type,
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
    return True, workflow_name


async def attach_profile_to_cluster(self, op_id, op_params, content):
    self.logger.info(
        f"attach_profile_to_cluster Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    profile = content["profile"]
    cluster = content["cluster"]
    workflow_template = "launcher-attach-profile.j2"
    workflow_name = f"attach-profile-{op_id}"

    # Additional params for the workflow
    profile_name = profile["git_name"].lower()
    profile_type = profile["profile_type"]
    cluster_kustomization_name = cluster["git_name"].lower()
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        profile_name=profile_name,
        profile_type=profile_type,
        cluster_kustomization_name=cluster_kustomization_name,
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
    return True, workflow_name


async def detach_profile_from_cluster(self, op_id, op_params, content):
    self.logger.info(
        f"detach_profile_from_cluster Enter. Operation {op_id}. Params: {op_params}"
    )
    # self.logger.debug(f"Content: {content}")

    profile = content["profile"]
    cluster = content["cluster"]
    workflow_template = "launcher-detach-profile.j2"
    workflow_name = f"detach-profile-{op_id}"

    # Additional params for the workflow
    # Additional params for the workflow
    profile_name = profile["git_name"].lower()
    profile_type = profile["profile_type"]
    cluster_kustomization_name = cluster["git_name"].lower()
    osm_project_name = "osm_admin"  # TODO: get project name from content

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        profile_name=profile_name,
        profile_type=profile_type,
        cluster_kustomization_name=cluster_kustomization_name,
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
    return True, workflow_name
