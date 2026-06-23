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


async def create_ksus(self, op_id, op_params_list, content_list):
    self.logger.info(f"create_ksus Enter. Operation {op_id}. Params: {op_params_list}")
    # self.logger.debug(f"Content: {content_list}")

    if len(content_list) > 1:
        raise Exception("There is no ODU workflow yet able to manage multiple KSUs")
    db_ksu = content_list[0]
    ksu_params = op_params_list[0]
    oka_list = ksu_params["oka"]
    if len(oka_list) > 1:
        raise Exception(
            "There is no ODU workflow yet able to manage multiple OKAs for a KSU"
        )
    oka_item = oka_list[0]
    oka_params = oka_item.get("transformation", {})
    if "sw_catalog_path" in oka_item:
        oka_path = oka_item["sw_catalog_path"]
    else:
        oka_type = MAP_PROFILE[
            oka_item.get("profile_type", "infra_controller_profiles")
        ]
        oka_name = oka_item["git_name"].lower()
        oka_path = f"{oka_type}/{oka_name}/templates"

    workflow_template = "launcher-create-ksu-hr.j2"
    workflow_name = f"create-ksus-{op_id}"
    ksu_name = db_ksu["git_name"].lower()

    # Additional params for the workflow
    osm_project_name = "osm_admin"  # TODO: get project name from db_ksu
    kustomization_name = ksu_name
    helmrelease_name = ksu_name
    profile_type = ksu_params.get("profile", {}).get("profile_type")
    profile_type = MAP_PROFILE[profile_type]
    profile_name = ksu_params.get("profile", {}).get("name")
    age_public_key = ksu_params.get("profile", {}).get("age_pubkey")
    kustomization_ns = oka_params.get("kustomization_namespace", "flux-system")
    target_ns = oka_params.get("namespace", "default")
    substitute_environment = oka_params.get("substitute_environment", "true").lower()
    custom_env_vars = oka_params.get("custom_env_vars", {})
    if custom_env_vars is None:
        custom_env_vars = {}
    if "APPNAME" not in custom_env_vars:
        custom_env_vars["APPNAME"] = ksu_name
    if "TARGET_NS" not in custom_env_vars:
        custom_env_vars["TARGET_NS"] = target_ns
    if "KUSTOMIZATION_NS" not in custom_env_vars:
        custom_env_vars["KUSTOMIZATION_NS"] = kustomization_ns
    custom_env_vars_str = "|\n"
    substitution_filter_list = []
    for k, v in custom_env_vars.items():
        custom_env_vars_str += " " * 10 + f"{k}={v}\n"
        substitution_filter_list.append(f"${k}")
    substitution_filter = ",".join(substitution_filter_list)
    # TODO: add additional substitution filters
    # substitution_filter = (
    #     f"{substitution_filter},{oka_params.get('substitution_filter', '')}".strip(",")
    # )
    inline_values = oka_params.get("inline_values", "")
    if inline_values:
        yaml_string = yaml.safe_dump(
            inline_values, sort_keys=False, default_flow_style=False
        )
        inline_values = "|\n" + "\n".join(
            [" " * 8 + line for line in yaml_string.splitlines()]
        )
    else:
        inline_values = '""'
    is_preexisting_cm = "false"
    cm_values = oka_params.get("configmap_values", "")
    if cm_values:
        yaml_string = yaml.safe_dump(
            cm_values, sort_keys=False, default_flow_style=False
        )
        cm_values = "|\n" + "\n".join(
            [" " * 8 + line for line in yaml_string.splitlines()]
        )
        values_configmap_name = f"cm-{ksu_name}"
        cm_key = "values.yaml"
    else:
        values_configmap_name = ""
        cm_key = ""
        cm_values = '""'
    is_preexisting_secret = "false"
    secret_values = oka_params.get("secret_values", "")
    if secret_values:
        values_secret_name = f"secret-{ksu_name}"
        reference_secret_for_values = f"ref-secret-{ksu_name}"
        reference_key_for_values = f"ref-key-{ksu_name}"
        secret_values = yaml.safe_dump(
            secret_values, sort_keys=False, default_flow_style=False
        )
    else:
        values_secret_name = ""
        reference_secret_for_values = "this-secret-does-not-exist"
        reference_key_for_values = "this-key-does-not-exist"
    sync = "true"

    if secret_values:
        secret_namespace = "osm-workflows"
        # Create secret
        await self.create_secret(
            reference_secret_for_values,
            secret_namespace,
            reference_key_for_values,
            secret_values,
        )

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        templates_path=oka_path,
        substitute_environment=substitute_environment,
        substitution_filter=substitution_filter,
        custom_env_vars=custom_env_vars_str,
        kustomization_name=kustomization_name,
        helmrelease_name=helmrelease_name,
        inline_values=inline_values,
        is_preexisting_secret=is_preexisting_secret,
        target_ns=target_ns,
        age_public_key=age_public_key,
        values_secret_name=values_secret_name,
        reference_secret_for_values=reference_secret_for_values,
        reference_key_for_values=reference_key_for_values,
        is_preexisting_cm=is_preexisting_cm,
        values_configmap_name=values_configmap_name,
        cm_key=cm_key,
        cm_values=cm_values,
        ksu_name=ksu_name,
        profile_name=profile_name,
        profile_type=profile_type,
        osm_project_name=osm_project_name,
        sync=sync,
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


async def update_ksus(self, op_id, op_params_list, content_list):
    self.logger.info(f"update_ksus Enter. Operation {op_id}. Params: {op_params_list}")
    # self.logger.debug(f"Content: {content_list}")

    if len(content_list) > 1:
        raise Exception("There is no ODU workflow yet able to manage multiple KSUs")
    db_ksu = content_list[0]
    ksu_params = op_params_list[0]
    oka_list = ksu_params["oka"]
    if len(oka_list) > 1:
        raise Exception(
            "There is no ODU workflow yet able to manage multiple OKAs for a KSU"
        )
    oka_item = oka_list[0]
    oka_params = oka_item.get("transformation", {})
    if "sw_catalog_path" in oka_item:
        oka_path = oka_item["sw_catalog_path"]
    else:
        oka_type = MAP_PROFILE[
            oka_item.get("profile_type", "infra_controller_profiles")
        ]
        oka_name = oka_item["git_name"].lower()
        oka_path = f"{oka_type}/{oka_name}/templates"

    workflow_template = "launcher-update-ksu-hr.j2"
    workflow_name = f"update-ksus-{op_id}"
    ksu_name = db_ksu["git_name"].lower()

    # Additional params for the workflow
    osm_project_name = "osm_admin"  # TODO: get project name from db_ksu
    kustomization_name = ksu_name
    helmrelease_name = ksu_name
    profile_type = ksu_params.get("profile", {}).get("profile_type")
    profile_type = MAP_PROFILE[profile_type]
    profile_name = ksu_params.get("profile", {}).get("name")
    age_public_key = ksu_params.get("profile", {}).get("age_pubkey")
    kustomization_ns = oka_params.get("kustomization_namespace", "flux-system")
    target_ns = oka_params.get("namespace", "default")
    substitute_environment = oka_params.get("substitute_environment", "true").lower()
    custom_env_vars = oka_params.get("custom_env_vars", {})
    if custom_env_vars is None:
        custom_env_vars = {}
    if "APPNAME" not in custom_env_vars:
        custom_env_vars["APPNAME"] = ksu_name
    if "TARGET_NS" not in custom_env_vars:
        custom_env_vars["TARGET_NS"] = target_ns
    if "KUSTOMIZATION_NS" not in custom_env_vars:
        custom_env_vars["KUSTOMIZATION_NS"] = kustomization_ns
    custom_env_vars_str = "|\n"
    substitution_filter_list = []
    for k, v in custom_env_vars.items():
        custom_env_vars_str += " " * 10 + f"{k}={v}\n"
        substitution_filter_list.append(f"${k}")
    substitution_filter = ",".join(substitution_filter_list)
    # TODO: add additional substitution filters
    # substitution_filter = (
    #     f"{substitution_filter},{oka_params.get('substitution_filter', '')}".strip(",")
    # )
    inline_values = oka_params.get("inline_values", "")
    if inline_values:
        yaml_string = yaml.safe_dump(
            inline_values, sort_keys=False, default_flow_style=False
        )
        inline_values = "|\n" + "\n".join(
            [" " * 8 + line for line in yaml_string.splitlines()]
        )
    else:
        inline_values = '""'
    is_preexisting_cm = "false"
    cm_values = oka_params.get("configmap_values", "")
    if cm_values:
        yaml_string = yaml.safe_dump(
            cm_values, sort_keys=False, default_flow_style=False
        )
        cm_values = "|\n" + "\n".join(
            [" " * 8 + line for line in yaml_string.splitlines()]
        )
        values_configmap_name = f"cm-{ksu_name}"
        cm_key = "values.yaml"
    else:
        values_configmap_name = ""
        cm_key = ""
        cm_values = '""'
    is_preexisting_secret = "false"
    secret_values = oka_params.get("secret_values", "")
    if secret_values:
        values_secret_name = f"secret-{ksu_name}"
        reference_secret_for_values = f"ref-secret-{ksu_name}"
        reference_key_for_values = f"ref-key-{ksu_name}"
        secret_values = yaml.safe_dump(
            secret_values, sort_keys=False, default_flow_style=False
        )
    else:
        values_secret_name = ""
        reference_secret_for_values = "this-secret-does-not-exist"
        reference_key_for_values = "this-key-does-not-exist"

    if secret_values:
        secret_namespace = "osm-workflows"
        # Create secret
        await self.create_secret(
            reference_secret_for_values,
            secret_namespace,
            reference_key_for_values,
            secret_values,
        )

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        templates_path=oka_path,
        substitute_environment=substitute_environment,
        substitution_filter=substitution_filter,
        custom_env_vars=custom_env_vars_str,
        kustomization_name=kustomization_name,
        helmrelease_name=helmrelease_name,
        inline_values=inline_values,
        is_preexisting_secret=is_preexisting_secret,
        target_ns=target_ns,
        age_public_key=age_public_key,
        values_secret_name=values_secret_name,
        reference_secret_for_values=reference_secret_for_values,
        reference_key_for_values=reference_key_for_values,
        is_preexisting_cm=is_preexisting_cm,
        values_configmap_name=values_configmap_name,
        cm_key=cm_key,
        cm_values=cm_values,
        ksu_name=ksu_name,
        profile_name=profile_name,
        profile_type=profile_type,
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


async def delete_ksus(self, op_id, op_params_list, content_list):
    self.logger.info(f"delete_ksus Enter. Operation {op_id}. Params: {op_params_list}")
    # self.logger.debug(f"Content: {content_list}")

    if len(content_list) > 1:
        raise Exception("There is no ODU workflow yet able to manage multiple KSUs")
    db_ksu = content_list[0]
    ksu_params = op_params_list[0]

    workflow_template = "launcher-delete-ksu.j2"
    workflow_name = f"delete-ksus-{op_id}"
    ksu_name = db_ksu["git_name"].lower()

    # Additional params for the workflow
    osm_project_name = "osm_admin"  # TODO: get project name from db_ksu
    profile_name = ksu_params.get("profile", {}).get("name")
    profile_type = ksu_params.get("profile", {}).get("profile_type")
    profile_type = MAP_PROFILE[profile_type]

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        ksu_name=ksu_name,
        profile_name=profile_name,
        profile_type=profile_type,
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


async def clone_ksu(self, op_id, op_params, content):
    self.logger.info(f"clone_ksu Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")
    workflow_name = f"clone-ksu-{content['_id']}"
    return True, workflow_name, None


async def move_ksu(self, op_id, op_params, content):
    self.logger.info(f"move_ksu Enter. Operation {op_id}. Params: {op_params}")
    # self.logger.debug(f"Content: {content}")
    workflow_name = f"move-ksu-{content['_id']}"
    return True, workflow_name, None


async def clean_items_ksu_create(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_ksu_create Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    try:
        if len(content_list) > 1:
            raise Exception("There is no ODU workflow yet able to manage multiple KSUs")
        db_ksu = content_list[0]
        ksu_name = db_ksu["git_name"].lower()
        ksu_params = op_params_list[0]
        oka_list = ksu_params["oka"]
        if len(oka_list) > 1:
            raise Exception(
                "There is no ODU workflow yet able to manage multiple OKAs for a KSU"
            )
        oka_item = oka_list[0]
        oka_params = oka_item.get("transformation", {})
        secret_values = oka_params.get("secret_values", "")
        if secret_values:
            items = {
                "secrets": [
                    {
                        "name": f"ref-secret-{ksu_name}",
                        "namespace": "osm-workflows",
                    }
                ]
            }
            await self.clean_items(items)
        return True, "OK"
    except Exception as e:
        return False, f"Error while cleaning items: {e}"


async def clean_items_ksu_update(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_ksu_update Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    return await self.clean_items_ksu_create(op_id, op_params_list, content_list)


async def clean_items_ksu_delete(self, op_id, op_params_list, content_list):
    self.logger.info(
        f"clean_items_ksu_delete Enter. Operation {op_id}. Params: {op_params_list}"
    )
    # self.logger.debug(f"Content: {content_list}")
    return True, "OK"
