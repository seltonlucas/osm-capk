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

import copy
import logging
import tempfile
from time import time
import traceback
from git import Repo
from osm_lcm.lcm_utils import LcmBase
from osm_lcm import odu_workflows
from osm_lcm.data_utils.list_utils import find_in_list
from osm_lcm.n2vc.kubectl import Kubectl
import yaml
from urllib.parse import quote


class GitOpsLcm(LcmBase):
    db_collection = "gitops"
    workflow_status = None
    resource_status = None

    profile_collection_mapping = {
        "infra_controller_profiles": "k8sinfra_controller",
        "infra_config_profiles": "k8sinfra_config",
        "resource_profiles": "k8sresource",
        "app_profiles": "k8sapp",
    }

    profile_type_mapping = {
        "infra-controllers": "infra_controller_profiles",
        "infra-configs": "infra_config_profiles",
        "managed-resources": "resource_profiles",
        "applications": "app_profiles",
    }

    def __init__(self, msg, lcm_tasks, config):
        self.logger = logging.getLogger("lcm.gitops")
        self.lcm_tasks = lcm_tasks
        self.odu = odu_workflows.OduWorkflow(msg, self.lcm_tasks, config)
        self._checkloop_kustomization_timeout = 900
        self._checkloop_resource_timeout = 900
        self._workflows = {}
        self.gitops_config = config["gitops"]
        self.logger.debug(f"GitOps config: {self.gitops_config}")
        self._repo_base_url = self.gitops_config.get("git_base_url")
        self._repo_user = self.gitops_config.get("user")
        self._repo_sw_catalogs_url = self.gitops_config.get(
            "sw_catalogs_repo_url",
            f"{self._repo_base_url}/{self._repo_user}/sw-catalogs-osm.git",
        )
        self._repo_password = self.gitops_config.get("password", "OUM+O61Iy1")
        self._full_repo_sw_catalogs_url = self.build_git_url_with_credentials(
            self._repo_sw_catalogs_url
        )
        super().__init__(msg, self.logger)

    def build_git_url_with_credentials(self, repo_url):
        # Build authenticated URL if credentials were provided
        if self._repo_password:
            # URL-safe escape password
            safe_user = quote(self._repo_user)
            safe_pass = quote(self._repo_password)

            # Insert credentials into the URL
            # e.g. https://username:password@github.com/org/repo.git
            auth_url = repo_url.replace("https://", f"https://{safe_user}:{safe_pass}@")
            auth_url = repo_url.replace("http://", f"https://{safe_user}:{safe_pass}@")
        else:
            auth_url = repo_url
        return auth_url

    async def check_dummy_operation(self, op_id, op_params, content):
        self.logger.info(f"Operation {op_id}. Params: {op_params}. Content: {content}")
        return True, "OK"

    def initialize_operation(self, item_id, op_id):
        db_item = self.db.get_one(self.db_collection, {"_id": item_id})
        operation = next(
            (op for op in db_item.get("operationHistory", []) if op["op_id"] == op_id),
            None,
        )
        operation["workflowState"] = "PROCESSING"
        operation["resourceState"] = "NOT_READY"
        operation["operationState"] = "IN_PROGRESS"
        operation["gitOperationInfo"] = None
        db_item["current_operation"] = operation["op_id"]
        self.db.set_one(self.db_collection, {"_id": item_id}, db_item)

    def get_operation_params(self, item, operation_id):
        operation_history = item.get("operationHistory", [])
        operation = find_in_list(
            operation_history, lambda op: op["op_id"] == operation_id
        )
        return operation.get("operationParams", {})

    def get_operation_type(self, item, operation_id):
        operation_history = item.get("operationHistory", [])
        operation = find_in_list(
            operation_history, lambda op: op["op_id"] == operation_id
        )
        return operation.get("operationType", {})

    def update_state_operation_history(
        self, content, op_id, workflow_state=None, resource_state=None
    ):
        self.logger.info(
            f"Update state of operation {op_id} in Operation History in DB"
        )
        self.logger.info(
            f"Workflow state: {workflow_state}. Resource state: {resource_state}"
        )
        self.logger.debug(f"Content: {content}")

        op_num = 0
        for operation in content["operationHistory"]:
            self.logger.debug("Operations: {}".format(operation))
            if operation["op_id"] == op_id:
                self.logger.debug("Found operation number: {}".format(op_num))
                if workflow_state is not None:
                    operation["workflowState"] = workflow_state

                if resource_state is not None:
                    operation["resourceState"] = resource_state
                break
            op_num += 1
        self.logger.debug("content: {}".format(content))

        return content

    def update_operation_history(
        self, content, op_id, workflow_status=None, resource_status=None, op_end=True
    ):
        self.logger.info(
            f"Update Operation History in DB. Workflow status: {workflow_status}. Resource status: {resource_status}"
        )
        self.logger.debug(f"Content: {content}")

        op_num = 0
        for operation in content["operationHistory"]:
            self.logger.debug("Operations: {}".format(operation))
            if operation["op_id"] == op_id:
                self.logger.debug("Found operation number: {}".format(op_num))
                if workflow_status is not None:
                    if workflow_status:
                        operation["workflowState"] = "COMPLETED"
                        operation["result"] = True
                    else:
                        operation["workflowState"] = "ERROR"
                        operation["operationState"] = "FAILED"
                        operation["result"] = False

                if resource_status is not None:
                    if resource_status:
                        operation["resourceState"] = "READY"
                        operation["operationState"] = "COMPLETED"
                        operation["result"] = True
                    else:
                        operation["resourceState"] = "NOT_READY"
                        operation["operationState"] = "FAILED"
                        operation["result"] = False

                if op_end:
                    now = time()
                    operation["endDate"] = now
                break
            op_num += 1
        self.logger.debug("content: {}".format(content))

        return content

    async def check_workflow_and_update_db(self, op_id, workflow_name, db_content):
        workflow_status, workflow_msg = await self.odu.check_workflow_status(
            op_id, workflow_name
        )
        self.logger.info(
            "Workflow Status: {} Workflow Message: {}".format(
                workflow_status, workflow_msg
            )
        )
        operation_type = self.get_operation_type(db_content, op_id)
        if operation_type == "create" and workflow_status:
            db_content["state"] = "CREATED"
        elif operation_type == "create" and not workflow_status:
            db_content["state"] = "FAILED_CREATION"
        elif operation_type == "delete" and workflow_status:
            db_content["state"] = "DELETED"
        elif operation_type == "delete" and not workflow_status:
            db_content["state"] = "FAILED_DELETION"

        if workflow_status:
            db_content["resourceState"] = "IN_PROGRESS.GIT_SYNCED"
        else:
            db_content["resourceState"] = "ERROR"

        db_content = self.update_operation_history(
            db_content, op_id, workflow_status, None
        )
        self.db.set_one(self.db_collection, {"_id": db_content["_id"]}, db_content)
        return workflow_status

    async def check_resource_and_update_db(
        self, resource_name, op_id, op_params, db_content
    ):
        workflow_status = True

        resource_status, resource_msg = await self.check_resource_status(
            resource_name, op_id, op_params, db_content
        )
        self.logger.info(
            "Resource Status: {} Resource Message: {}".format(
                resource_status, resource_msg
            )
        )

        if resource_status:
            db_content["resourceState"] = "READY"
        else:
            db_content["resourceState"] = "ERROR"

        db_content = self.update_operation_history(
            db_content, op_id, workflow_status, resource_status
        )
        db_content["operatingState"] = "IDLE"
        db_content["current_operation"] = None
        return resource_status, db_content

    async def common_check_list(
        self, op_id, checkings_list, db_collection, db_item, kubectl_obj=None
    ):
        try:
            for checking in checkings_list:
                if checking["enable"]:
                    status, message = await self.odu.readiness_loop(
                        op_id=op_id,
                        item=checking["item"],
                        name=checking["name"],
                        namespace=checking["namespace"],
                        condition=checking.get("condition"),
                        deleted=checking.get("deleted", False),
                        timeout=checking["timeout"],
                        kubectl_obj=kubectl_obj,
                    )
                    if not status:
                        error_message = "Resources not ready: "
                        error_message += checking.get("error_message", "")
                        return status, f"{error_message}: {message}"
                    else:
                        db_item["resourceState"] = checking["resourceState"]
                        db_item = self.update_state_operation_history(
                            db_item, op_id, None, checking["resourceState"]
                        )
                        self.db.set_one(db_collection, {"_id": db_item["_id"]}, db_item)
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.logger.debug(f"Exception: {e}", exc_info=True)
            return False, f"Unexpected exception: {e}"
        return True, "OK"

    async def check_resource_status(self, key, op_id, op_params, content):
        self.logger.info(
            f"Check resource status. Key: {key}. Operation: {op_id}. Params: {op_params}."
        )
        self.logger.debug(f"Check resource status. Content: {content}")
        check_resource_function = self._workflows.get(key, {}).get(
            "check_resource_function"
        )
        self.logger.info("check_resource function : {}".format(check_resource_function))
        if check_resource_function:
            return await check_resource_function(op_id, op_params, content)
        else:
            return await self.check_dummy_operation(op_id, op_params, content)

    def check_force_delete_and_delete_from_db(
        self, _id, workflow_status, resource_status, force
    ):
        self.logger.info(
            f" Force: {force} Workflow status: {workflow_status} Resource Status: {resource_status}"
        )
        if force and (not workflow_status or not resource_status):
            self.db.del_one(self.db_collection, {"_id": _id})
            return True
        return False

    def decrypt_age_keys(self, content, fields=["age_pubkey", "age_privkey"]):
        self.db.encrypt_decrypt_fields(
            content,
            "decrypt",
            fields,
            schema_version="1.11",
            salt=content["_id"],
        )

    def encrypt_age_keys(self, content, fields=["age_pubkey", "age_privkey"]):
        self.db.encrypt_decrypt_fields(
            content,
            "encrypt",
            fields,
            schema_version="1.11",
            salt=content["_id"],
        )

    def decrypted_copy(self, content, fields=["age_pubkey", "age_privkey"]):
        # This deep copy is intended to be passed to ODU workflows.
        content_copy = copy.deepcopy(content)

        # decrypting the key
        self.db.encrypt_decrypt_fields(
            content_copy,
            "decrypt",
            fields,
            schema_version="1.11",
            salt=content_copy["_id"],
        )
        return content_copy

    def delete_ksu_dependency(self, _id, data):
        used_oka = []
        existing_oka = []

        for oka_data in data["oka"]:
            if oka_data.get("_id"):
                used_oka.append(oka_data["_id"])

        all_ksu_data = self.db.get_list("ksus", {})
        for ksu_data in all_ksu_data:
            if ksu_data["_id"] != _id:
                for oka_data in ksu_data["oka"]:
                    if oka_data.get("_id"):
                        if oka_data["_id"] not in existing_oka:
                            existing_oka.append(oka_data["_id"])

        self.logger.info(f"Used OKA: {used_oka}")
        self.logger.info(f"Existing OKA: {existing_oka}")

        for oka_id in used_oka:
            if oka_id not in existing_oka:
                self.db.set_one(
                    "okas", {"_id": oka_id}, {"_admin.usageState": "NOT_IN_USE"}
                )

        return

    def delete_profile_ksu(self, _id, profile_type):
        filter_q = {"profile": {"_id": _id, "profile_type": profile_type}}
        ksu_list = self.db.get_list("ksus", filter_q)
        for ksu_data in ksu_list:
            self.delete_ksu_dependency(ksu_data["_id"], ksu_data)

        if ksu_list:
            self.db.del_list("ksus", filter_q)
        return

    def cluster_kubectl(self, db_cluster):
        cluster_kubeconfig = db_cluster["credentials"]
        kubeconfig_path = f"/tmp/{db_cluster['_id']}_kubeconfig.yaml"
        with open(kubeconfig_path, "w") as kubeconfig_file:
            yaml.safe_dump(cluster_kubeconfig, kubeconfig_file)
        return Kubectl(config_file=kubeconfig_path)

    def cloneGitRepo(self, repo_url, branch):
        self.logger.debug(f"Cloning repo {repo_url}, branch {branch}")
        tmpdir = tempfile.mkdtemp()
        self.logger.debug(f"Created temp folder {tmpdir}")
        cloned_repo = Repo.clone_from(
            repo_url,
            tmpdir,
            allow_unsafe_options=True,
            multi_options=["-c", "http.sslVerify=false"],
        )
        self.logger.debug(f"Current active branch: {cloned_repo.active_branch}")
        assert cloned_repo
        new_branch = cloned_repo.create_head(branch)  # create a new branch
        assert new_branch.checkout() == cloned_repo.active_branch
        self.logger.debug(f"Current active branch: {cloned_repo.active_branch}")
        self.logger.info(f"Repo {repo_url} cloned in {tmpdir}. New branch: {branch}")
        return tmpdir

    def createCommit(self, repo_dir, commit_msg):
        repo = Repo(repo_dir)
        self.logger.info(
            f"Creating commit '{commit_msg}' in branch '{repo.active_branch}'"
        )
        self.logger.debug(f"Current active branch: {repo.active_branch}")
        # repo.index.add('**')
        repo.git.add(all=True)
        repo.index.commit(commit_msg)
        self.logger.info(
            f"Commit '{commit_msg}' created in branch '{repo.active_branch}'"
        )
        self.logger.debug(f"Current active branch: {repo.active_branch}")
        return repo.active_branch

    def mergeGit(self, repo_dir, git_branch):
        repo = Repo(repo_dir)
        self.logger.info(f"Merging local branch '{git_branch}' into main")
        with_git = False
        if with_git:
            try:
                repo.git("checkout main")
                repo.git(f"merge {git_branch}")
                return True
            except Exception as e:
                self.logger.error(e)
                return False
        else:
            # prepare a merge
            main = repo.heads.main  # right-hand side is ahead of us, in the future
            merge_base = repo.merge_base(git_branch, main)  # three-way merge
            repo.index.merge_tree(main, base=merge_base)  # write the merge into index
            try:
                # The merge is done in the branch
                repo.index.commit(
                    f"Merged {git_branch} and main",
                    parent_commits=(git_branch.commit, main.commit),
                )
                # Now, git_branch is ahed of master. Now let master point to the recent commit
                aux_head = repo.create_head("aux")
                main.commit = aux_head.commit
                repo.delete_head(aux_head)
                assert main.checkout()
                return True
            except Exception as e:
                self.logger.error(e)
                return False

    def pushToRemote(self, repo_dir):
        repo = Repo(repo_dir)
        self.logger.info("Pushing the change to remote")
        # repo.remotes.origin.push(refspec='{}:{}'.format(local_branch, remote_branch))
        repo.remotes.origin.push()
        self.logger.info("Push done")
        return True
