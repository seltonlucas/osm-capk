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
import tempfile
import os


MAP_PROFILE = {
    "infra_controller_profiles": "infra-controller-profiles",
    "infra_config_profiles": "infra-config-profiles",
    "resource_profiles": "managed-resources",
    "app_profiles": "app-profiles",
}


def merge_model(base, override):
    """Recursively merge override dictionary into base dictionary."""
    merge_model = base.copy()
    for k, v in override.get("spec", {}).items():
        if k != "ksus":
            merge_model["spec"][k] = v
    for ksu_override in override.get("spec", {}).get("ksus", []):
        for ksu_base in merge_model.get("spec", {}).get("ksus", []):
            if ksu_base.get("name") == ksu_override.get("name"):
                for k, v in ksu_override.items():
                    if k != "patterns":
                        ksu_base[k] = v
                        continue
                    for pattern_override in ksu_override.get("patterns", []):
                        for pattern_base in ksu_base.get("patterns", []):
                            if pattern_base.get("name") == pattern_override.get("name"):
                                for kp, vp in pattern_override.items():
                                    if kp != "bricks":
                                        pattern_base[kp] = vp
                                        continue
                                    for brick_override in pattern_override.get(
                                        "bricks", []
                                    ):
                                        for brick_base in pattern_base.get(
                                            "bricks", []
                                        ):
                                            if brick_base.get(
                                                "name"
                                            ) == brick_override.get("name"):
                                                for kb, vb in brick_override.items():
                                                    if kb != "hrset-values":
                                                        brick_base[kb] = vb
                                                        continue
                                                    for (
                                                        hrset_override
                                                    ) in brick_override.get(
                                                        "hrset-values", []
                                                    ):
                                                        for (
                                                            hrset_base
                                                        ) in brick_base.get(
                                                            "hrset-values", []
                                                        ):
                                                            if hrset_base.get(
                                                                "name"
                                                            ) == hrset_override.get(
                                                                "name"
                                                            ):
                                                                hrset_base |= (
                                                                    hrset_override
                                                                )
                                                                break
                                                        else:
                                                            brick_base[
                                                                "hrset-values"
                                                            ].append(hrset_override)
                                                break
                                        else:
                                            pattern_base["bricks"].append(
                                                brick_override
                                            )
                                break
                        else:
                            ksu_base["patterns"].append(pattern_override)
                break
        else:
            merge_model["spec"]["ksus"].append(ksu_override)
    return merge_model


async def launch_app(self, op_id, op_params, workflow_content, operation_type):
    self.logger.info(
        f"launch_app Enter. Operation {op_id}. Operation Type: {operation_type}"
    )
    # self.logger.debug(f"Operation Params: {op_params}")
    # self.logger.debug(f"Content: {workflow_content}")

    db_app = workflow_content["app"]
    db_profile = workflow_content.get("profile")

    profile_t = db_app.get("profile_type")
    profile_type = MAP_PROFILE[profile_t]
    profile_name = db_profile.get("git_name").lower()
    app_name = db_app["git_name"].lower()
    app_command = f"app {operation_type} $environment"
    age_public_key = db_profile.get("age_pubkey")

    sw_catalog_model = workflow_content.get("model")
    self.logger.debug(f"SW catalog model: {sw_catalog_model}")

    # Update the app model, extending it also with the model from op_params
    if operation_type == "update":
        model = op_params.get("model", db_app.get("app_model", {}))
    else:
        model = op_params.get("model", {})
    app_model = merge_model(sw_catalog_model, model)

    app_model["kind"] = "AppInstantiation"
    app_model["metadata"]["name"] = app_name
    for ksu in app_model.get("spec", {}).get("ksus", []):
        for pattern in ksu.get("patterns", []):
            for brick in pattern.get("bricks", []):
                brick["public-age-key"] = age_public_key
    self.logger.debug(f"App model: {app_model}")

    if operation_type == "update":
        params = op_params.get("params", db_app.get("params", {}))
    else:
        params = op_params.get("params", {})
    params["PROFILE_TYPE"] = profile_type
    params["PROFILE_NAME"] = profile_name
    params["APPNAME"] = app_name
    self.logger.debug(f"Params: {params}")

    if operation_type == "update":
        secret_params = op_params.get("secret_params", db_app.get("secret_params", {}))
    else:
        secret_params = op_params.get("secret_params", {})
    self.logger.debug(f"Secret Params: {secret_params}")

    # Create temporary folder for the app model and the parameters
    temp_dir = tempfile.mkdtemp(prefix=f"app-{operation_type}-{op_id}-")
    self.logger.debug(f"Temporary dir created: {temp_dir}")
    with open(f"{temp_dir}/app_instance_model.yaml", "w") as f:
        yaml.safe_dump(
            app_model, f, indent=2, default_flow_style=False, sort_keys=False
        )

    os.makedirs(f"{temp_dir}/parameters/clear", exist_ok=True)
    with open(f"{temp_dir}/parameters/clear/environment.yaml", "w") as f:
        yaml.safe_dump(params, f, indent=2, default_flow_style=False, sort_keys=False)

    # Create PVC and copy app model and parameters to PVC
    app_model_pvc = f"temp-pvc-app-{op_id}"
    src_files = [
        f"{temp_dir}/app_instance_model.yaml",
        f"{temp_dir}/parameters/clear/environment.yaml",
    ]
    dest_files = [
        "app_instance_model.yaml",
        "parameters/clear/environment.yaml",
    ]
    self.logger.debug(
        f"Copying files to PVC {app_model_pvc}: {src_files} -> {dest_files}"
    )
    await self._kubectl.create_pvc_with_content(
        name=app_model_pvc,
        namespace="osm-workflows",
        src_files=src_files,
        dest_files=dest_files,
    )

    # Create secret with secret_params
    secret_name = f"secret-app-{op_id}"
    secret_namespace = "osm-workflows"
    secret_key = "environment.yaml"
    secret_value = yaml.safe_dump(
        secret_params, indent=2, default_flow_style=False, sort_keys=False
    )
    try:
        self.logger.debug(f"Testing kubectl: {self._kubectl}")
        self.logger.debug(
            f"Testing kubectl configuration: {self._kubectl.configuration}"
        )
        self.logger.debug(
            f"Testing kubectl configuration Host: {self._kubectl.configuration.host}"
        )
        self.logger.debug(
            f"Creating secret {secret_name} in namespace {secret_namespace}"
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
        )

    # Create workflow to launch the app
    workflow_template = "launcher-app.j2"
    workflow_name = f"{operation_type}-app-{op_id}"
    # Additional params for the workflow
    osm_project_name = workflow_content.get("project_name", "osm_admin")

    # Render workflow
    manifest = self.render_jinja_template(
        workflow_template,
        output_file=None,
        workflow_name=workflow_name,
        app_command=app_command,
        app_model_pvc=app_model_pvc,
        app_secret_name=secret_name,
        git_fleet_url=self._repo_fleet_url,
        git_sw_catalogs_url=self._repo_sw_catalogs_url,
        app_name=app_name,
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
    workflow_resources = {
        "app_model": app_model,
        "secret_params": secret_params,
        "params": params,
    }
    return True, workflow_name, workflow_resources


async def create_app(self, op_id, op_params, content):
    self.logger.info(f"create_app Enter. Operation {op_id}")
    # self.logger.debug(f"Operation Params: {op_params}")
    # self.logger.debug(f"Content: {workflow_content}")
    return await self.launch_app(op_id, op_params, content, "create")


async def update_app(self, op_id, op_params, content):
    self.logger.info(f"update_app Enter. Operation {op_id}")
    # self.logger.debug(f"Operation Params: {op_params}")
    # self.logger.debug(f"Content: {workflow_content}")
    return await self.launch_app(op_id, op_params, content, "update")


async def delete_app(self, op_id, op_params, content):
    self.logger.info(f"delete_app Enter. Operation {op_id}")
    # self.logger.debug(f"Operation Params: {op_params}")
    # self.logger.debug(f"Content: {workflow_content}")
    return await self.launch_app(op_id, op_params, content, "delete")


async def clean_items_app_launch(self, op_id, op_params, workflow_content):
    self.logger.info(f"clean_items_app_launch Enter. Operation {op_id}")
    # self.logger.debug(f"Operation Params: {op_params}")
    # self.logger.debug(f"Content: {workflow_content}")
    try:
        secret_name = f"secret-app-{op_id}"
        volume_name = f"temp-pvc-app-{op_id}"
        items = {
            "secrets": [
                {
                    "name": secret_name,
                    "namespace": "osm-workflows",
                }
            ],
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
