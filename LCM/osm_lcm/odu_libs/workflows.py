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


import asyncio
from math import ceil
from jsonpath_ng.ext import parse


async def check_workflow_status(self, op_id, workflow_name):
    self.logger.info(f"Op {op_id}, check_workflow_status Enter: {workflow_name}")
    if not workflow_name:
        return False, "Workflow was not launched"
    try:
        # First check if the workflow ends successfully
        completed, message = await self.readiness_loop(
            op_id,
            item="workflow",
            name=workflow_name,
            namespace="osm-workflows",
            condition={
                "jsonpath_filter": "status.conditions[?(@.type=='Completed')].status",
                "value": "True",
            },
            deleted=False,
            timeout=300,
        )
        if completed:
            # Then check if the workflow has a failed task
            return await self.readiness_loop(
                op_id,
                item="workflow",
                name=workflow_name,
                namespace="osm-workflows",
                condition={
                    "jsonpath_filter": "status.phase",
                    "value": "Succeeded",
                },
                deleted=False,
                timeout=0,
            )
        else:
            return False, f"Workflow was not completed: {message}"
    except Exception as e:
        return False, f"Workflow could not be completed. Unexpected exception: {e}"


async def readiness_loop(
    self, op_id, item, name, namespace, condition, deleted, timeout, kubectl_obj=None
):
    if kubectl_obj is None:
        kubectl_obj = self._kubectl
    self.logger.info("readiness_loop Enter")
    self.logger.info(
        f"Op {op_id}. {item} {name}. Namespace: '{namespace}'. Condition: {condition}. Deleted: {deleted}. Timeout: {timeout}"
    )
    item_api_map = {
        "workflow": {
            "api_group": "argoproj.io",
            "api_plural": "workflows",
            "api_version": "v1alpha1",
        },
        "kustomization": {
            "api_group": "kustomize.toolkit.fluxcd.io",
            "api_plural": "kustomizations",
            "api_version": "v1",
        },
        "cluster_aws": {
            "api_group": "eks.aws.upbound.io",
            "api_plural": "clusters",
            "api_version": "v1beta1",
        },
        "cluster_azure": {
            "api_group": "containerservice.azure.upbound.io",
            "api_plural": "kubernetesclusters",
            "api_version": "v1beta1",
        },
        "cluster_gcp": {
            "api_group": "container.gcp.upbound.io",
            "api_plural": "clusters",
            "api_version": "v1beta2",
        },
        "nodegroup_aws": {
            "api_group": "eks.aws.upbound.io",
            "api_plural": "nodegroups",
            "api_version": "v1beta1",
        },
        "nodegroup_gcp": {
            "api_group": "container.gcp.upbound.io",
            "api_plural": "nodepools",
            "api_version": "v1beta2",
        },
    }
    counter = 1
    retry_time = self._odu_checkloop_retry_time
    max_iterations = ceil(timeout / retry_time)
    if max_iterations < 1:
        max_iterations = 1
    api_group = item_api_map[item]["api_group"]
    api_plural = item_api_map[item]["api_plural"]
    api_version = item_api_map[item]["api_version"]

    while counter <= max_iterations:
        iteration_prefix = f"Op {op_id}. Iteration {counter}/{max_iterations}"
        try:
            self.logger.info(f"Op {op_id}. Iteration {counter}/{max_iterations}")
            generic_object = await kubectl_obj.get_generic_object(
                api_group=api_group,
                api_plural=api_plural,
                api_version=api_version,
                namespace=namespace,
                name=name,
            )
            if deleted:
                if generic_object:
                    self.logger.info(
                        f"{iteration_prefix}. Found {api_plural}. Name: {name}. Namespace: '{namespace}'. API: {api_group}/{api_version}"
                    )
                else:
                    self.logger.info(
                        f"{iteration_prefix}. {item} {name} deleted after {counter} iterations (aprox {counter*retry_time} seconds)"
                    )
                    return True, "COMPLETED"
            else:
                if not condition:
                    return True, "Nothing to check"
                if generic_object:
                    # If there is object, conditions must be checked
                    # self.logger.debug(f"{yaml.safe_dump(generic_object)}")
                    conditions = generic_object.get("status", {}).get("conditions", [])
                    self.logger.info(
                        f"{iteration_prefix}. Object found: {item} status conditions: {conditions}"
                    )
                    jsonpath_expr = parse(condition["jsonpath_filter"])
                    match = jsonpath_expr.find(generic_object)
                    if match:
                        value = str(match[0].value)
                        condition_function = condition.get(
                            "function", lambda x, y: x == y
                        )
                        if condition_function(condition["value"], value):
                            self.logger.info(
                                f"{iteration_prefix}. {item} {name} met the condition {condition} with {value} in {counter} iterations (aprox {counter*retry_time} seconds)"
                            )
                            return True, "COMPLETED"
                        else:
                            self.logger.info(
                                f"{iteration_prefix}. {item} {name} did not meet the condition {condition} with value {value}"
                            )
                    else:
                        self.logger.info(
                            f"{iteration_prefix}. No match for filter {condition.get('jsonpath_filter', '-')} in {item} {name}"
                        )
                else:
                    self.logger.info(
                        f"{iteration_prefix}. Could not find {api_plural}. Name: {name}. Namespace: '{namespace}'. API: {api_group}/{api_version}"
                    )
        except Exception as e:
            self.logger.error(f"Exception: {e}")
        if counter < max_iterations:
            await asyncio.sleep(retry_time)
        counter += 1
    return (
        False,
        f"Op {op_id}. {item} {name} was not ready after {max_iterations} iterations (aprox {timeout} seconds)",
    )
