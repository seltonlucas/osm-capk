##
# Copyright 2019 Telefonica Investigacion y Desarrollo, S.A.U.
# This file is part of OSM
# All Rights Reserved.
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
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact with: nfvlabs@tid.es
##
import abc
import asyncio
from typing import Union
from shlex import quote
import random
import time
import shlex
import shutil
import stat
import os
from uuid import uuid4
from urllib.parse import urlparse
import yaml

from osm_lcm.n2vc.config import EnvironConfig
from osm_lcm.n2vc.exceptions import K8sException
from osm_lcm.n2vc.k8s_conn import K8sConnector
from osm_lcm.n2vc.kubectl import Kubectl


class K8sHelmBaseConnector(K8sConnector):

    """
    ####################################################################################
    ################################### P U B L I C ####################################
    ####################################################################################
    """

    service_account = "osm"

    def __init__(
        self,
        fs: object,
        db: object,
        kubectl_command: str = "/usr/bin/kubectl",
        helm_command: str = "/usr/bin/helm",
        log: object = None,
        on_update_db=None,
    ):
        """

        :param fs: file system for kubernetes and helm configuration
        :param db: database object to write current operation status
        :param kubectl_command: path to kubectl executable
        :param helm_command: path to helm executable
        :param log: logger
        :param on_update_db: callback called when k8s connector updates database
        """

        # parent class
        K8sConnector.__init__(self, db=db, log=log, on_update_db=on_update_db)

        self.log.info("Initializing K8S Helm connector")

        self.config = EnvironConfig()
        # random numbers for release name generation
        random.seed(time.time())

        # the file system
        self.fs = fs

        # exception if kubectl is not installed
        self.kubectl_command = kubectl_command
        self._check_file_exists(filename=kubectl_command, exception_if_not_exists=True)

        # exception if helm is not installed
        self._helm_command = helm_command
        self._check_file_exists(filename=helm_command, exception_if_not_exists=True)

        # exception if main post renderer executable is not present
        self.main_post_renderer_path = EnvironConfig(prefixes=["OSMLCM_"]).get(
            "mainpostrendererpath"
        )
        if self.main_post_renderer_path:
            self._check_file_exists(
                filename=self.main_post_renderer_path, exception_if_not_exists=True
            )

        # exception if podLabels post renderer executable is not present
        self.podLabels_post_renderer_path = EnvironConfig(prefixes=["OSMLCM_"]).get(
            "podlabelspostrendererpath"
        )
        if self.podLabels_post_renderer_path:
            self._check_file_exists(
                filename=self.podLabels_post_renderer_path, exception_if_not_exists=True
            )

        # exception if nodeSelector post renderer executable is not present
        self.nodeSelector_post_renderer_path = EnvironConfig(prefixes=["OSMLCM_"]).get(
            "nodeselectorpostrendererpath"
        )
        if self.nodeSelector_post_renderer_path:
            self._check_file_exists(
                filename=self.nodeSelector_post_renderer_path,
                exception_if_not_exists=True,
            )

        # obtain stable repo url from config or apply default
        self._stable_repo_url = self.config.get("stablerepourl")
        if self._stable_repo_url == "None":
            self._stable_repo_url = None

        # Lock to avoid concurrent execution of helm commands
        self.cmd_lock = asyncio.Lock()

    def _get_namespace(self, cluster_uuid: str) -> str:
        """
        Obtains the namespace used by the cluster with the uuid passed by argument

        param: cluster_uuid: cluster's uuid
        """

        # first, obtain the cluster corresponding to the uuid passed by argument
        k8scluster = self.db.get_one(
            "k8sclusters", q_filter={"_id": cluster_uuid}, fail_on_empty=False
        )
        return k8scluster.get("namespace")

    async def init_env(
        self,
        k8s_creds: str,
        namespace: str = "kube-system",
        reuse_cluster_uuid=None,
        **kwargs,
    ) -> tuple[str, bool]:
        """
        It prepares a given K8s cluster environment to run Charts

        :param k8s_creds: credentials to access a given K8s cluster, i.e. a valid
            '.kube/config'
        :param namespace: optional namespace to be used for helm. By default,
            'kube-system' will be used
        :param reuse_cluster_uuid: existing cluster uuid for reuse
        :param kwargs: Additional parameters (None yet)
        :return: uuid of the K8s cluster and True if connector has installed some
            software in the cluster
        (on error, an exception will be raised)
        """

        if reuse_cluster_uuid:
            cluster_id = reuse_cluster_uuid
        else:
            cluster_id = str(uuid4())

        self.log.debug(
            "Initializing K8S Cluster {}. namespace: {}".format(cluster_id, namespace)
        )

        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )
        mode = stat.S_IRUSR | stat.S_IWUSR
        with open(paths["kube_config"], "w", mode) as f:
            f.write(k8s_creds)
        os.chmod(paths["kube_config"], 0o600)

        # Code with initialization specific of helm version
        n2vc_installed_sw = await self._cluster_init(cluster_id, namespace, paths, env)

        # sync fs with local data
        self.fs.reverse_sync(from_path=cluster_id)

        self.log.info("Cluster {} initialized".format(cluster_id))

        return cluster_id, n2vc_installed_sw

    async def repo_add(
        self,
        cluster_uuid: str,
        name: str,
        url: str,
        repo_type: str = "chart",
        cert: str = None,
        user: str = None,
        password: str = None,
        oci: bool = False,
    ):
        self.log.debug(
            "Cluster {}, adding {} repository {}. URL: {}".format(
                cluster_uuid, repo_type, name, url
            )
        )

        # init_env
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        if oci:
            if user and password:
                host_port = urlparse(url).netloc if url.startswith("oci://") else url
                # helm registry login url
                command = "env KUBECONFIG={} {} registry login {}".format(
                    paths["kube_config"], self._helm_command, quote(host_port)
                )
            else:
                self.log.debug(
                    "OCI registry login is not needed for repo: {}".format(name)
                )
                return
        else:
            # helm repo add name url
            command = "env KUBECONFIG={} {} repo add {} {}".format(
                paths["kube_config"], self._helm_command, quote(name), quote(url)
            )

        if cert:
            temp_cert_file = os.path.join(
                self.fs.path, "{}/helmcerts/".format(cluster_uuid), "temp.crt"
            )
            os.makedirs(os.path.dirname(temp_cert_file), exist_ok=True)
            with open(temp_cert_file, "w") as the_cert:
                the_cert.write(cert)
            command += " --ca-file {}".format(quote(temp_cert_file))

        if user:
            command += " --username={}".format(quote(user))

        if password:
            command += " --password={}".format(quote(password))

        self.log.debug("adding repo: {}".format(command))
        await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        if not oci:
            # helm repo update
            command = "env KUBECONFIG={} {} repo update {}".format(
                paths["kube_config"], self._helm_command, quote(name)
            )
            self.log.debug("updating repo: {}".format(command))
            await self._local_async_exec(
                command=command, raise_exception_on_error=False, env=env
            )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

    async def repo_update(self, cluster_uuid: str, name: str, repo_type: str = "chart"):
        self.log.debug(
            "Cluster {}, updating {} repository {}".format(
                cluster_uuid, repo_type, name
            )
        )

        # init_env
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # helm repo update
        command = "{} repo update {}".format(self._helm_command, quote(name))
        self.log.debug("updating repo: {}".format(command))
        await self._local_async_exec(
            command=command, raise_exception_on_error=False, env=env
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

    async def repo_list(self, cluster_uuid: str) -> list:
        """
        Get the list of registered repositories

        :return: list of registered repositories: [ (name, url) .... ]
        """

        self.log.debug("list repositories for cluster {}".format(cluster_uuid))

        # config filename
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        command = "env KUBECONFIG={} {} repo list --output yaml".format(
            paths["kube_config"], self._helm_command
        )

        # Set exception to false because if there are no repos just want an empty list
        output, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=False, env=env
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        if _rc == 0:
            if output and len(output) > 0:
                repos = yaml.load(output, Loader=yaml.SafeLoader)
                # unify format between helm2 and helm3 setting all keys lowercase
                return self._lower_keys_list(repos)
            else:
                return []
        else:
            return []

    async def repo_remove(self, cluster_uuid: str, name: str):
        self.log.debug(
            "remove {} repositories for cluster {}".format(name, cluster_uuid)
        )

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        command = "env KUBECONFIG={} {} repo remove {}".format(
            paths["kube_config"], self._helm_command, quote(name)
        )
        await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

    async def reset(
        self,
        cluster_uuid: str,
        force: bool = False,
        uninstall_sw: bool = False,
        **kwargs,
    ) -> bool:
        """Reset a cluster

        Resets the Kubernetes cluster by removing the helm deployment that represents it.

        :param cluster_uuid: The UUID of the cluster to reset
        :param force: Boolean to force the reset
        :param uninstall_sw: Boolean to force the reset
        :param kwargs: Additional parameters (None yet)
        :return: Returns True if successful or raises an exception.
        """
        namespace = self._get_namespace(cluster_uuid=cluster_uuid)
        self.log.debug(
            "Resetting K8s environment. cluster uuid: {} uninstall={}".format(
                cluster_uuid, uninstall_sw
            )
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # uninstall releases if needed.
        if uninstall_sw:
            releases = await self.instances_list(cluster_uuid=cluster_uuid)
            if len(releases) > 0:
                if force:
                    for r in releases:
                        try:
                            kdu_instance = r.get("name")
                            chart = r.get("chart")
                            self.log.debug(
                                "Uninstalling {} -> {}".format(chart, kdu_instance)
                            )
                            await self.uninstall(
                                cluster_uuid=cluster_uuid, kdu_instance=kdu_instance
                            )
                        except Exception as e:
                            # will not raise exception as it was found
                            # that in some cases of previously installed helm releases it
                            # raised an error
                            self.log.warn(
                                "Error uninstalling release {}: {}".format(
                                    kdu_instance, e
                                )
                            )
                else:
                    msg = (
                        "Cluster uuid: {} has releases and not force. Leaving K8s helm environment"
                    ).format(cluster_uuid)
                    self.log.warn(msg)
                    uninstall_sw = (
                        False  # Allow to remove k8s cluster without removing Tiller
                    )

        if uninstall_sw:
            await self._uninstall_sw(cluster_id=cluster_uuid, namespace=namespace)

        # delete cluster directory
        self.log.debug("Removing directory {}".format(cluster_uuid))
        self.fs.file_delete(cluster_uuid, ignore_non_exist=True)
        # Remove also local directorio if still exist
        direct = self.fs.path + "/" + cluster_uuid
        shutil.rmtree(direct, ignore_errors=True)

        return True

    def _is_helm_chart_a_file(self, chart_name: str):
        return chart_name.count("/") > 1

    @staticmethod
    def _is_helm_chart_a_url(chart_name: str):
        result = urlparse(chart_name)
        return all([result.scheme, result.netloc])

    async def _install_impl(
        self,
        cluster_id: str,
        kdu_model: str,
        paths: dict,
        env: dict,
        kdu_instance: str,
        atomic: bool = True,
        timeout: float = 300,
        params: dict = None,
        db_dict: dict = None,
        labels: dict = None,
        kdu_name: str = None,
        namespace: str = None,
    ):
        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        # params to str
        params_str, file_to_delete = self._params_to_file_option(
            cluster_id=cluster_id, params=params
        )

        kdu_model, version = await self._prepare_helm_chart(kdu_model, cluster_id)

        command = self._get_install_command(
            kdu_model,
            kdu_instance,
            namespace,
            labels,
            params_str,
            version,
            atomic,
            timeout,
            paths["kube_config"],
        )

        self.log.debug("installing: {}".format(command))

        if atomic:
            # exec helm in a task
            exec_task = asyncio.ensure_future(
                coro_or_future=self._local_async_exec(
                    command=command, raise_exception_on_error=False, env=env
                )
            )

            # write status in another task
            status_task = asyncio.ensure_future(
                coro_or_future=self._store_status(
                    cluster_id=cluster_id,
                    kdu_instance=kdu_instance,
                    namespace=namespace,
                    db_dict=db_dict,
                    operation="install",
                )
            )

            # wait for execution task
            await asyncio.wait([exec_task])

            # cancel status task
            status_task.cancel()

            output, rc = exec_task.result()

        else:
            output, rc = await self._local_async_exec(
                command=command, raise_exception_on_error=False, env=env
            )

        # remove temporal values yaml file
        if file_to_delete:
            os.remove(file_to_delete)

        # write final status
        await self._store_status(
            cluster_id=cluster_id,
            kdu_instance=kdu_instance,
            namespace=namespace,
            db_dict=db_dict,
            operation="install",
        )

        if rc != 0:
            msg = "Error executing command: {}\nOutput: {}".format(command, output)
            self.log.error(msg)
            raise K8sException(msg)

    async def upgrade(
        self,
        cluster_uuid: str,
        kdu_instance: str,
        kdu_model: str = None,
        atomic: bool = True,
        timeout: float = 300,
        params: dict = None,
        db_dict: dict = None,
        namespace: str = None,
        targetHostK8sLabels: dict = None,
        reset_values: bool = False,
        reuse_values: bool = True,
        reset_then_reuse_values: bool = False,
        force: bool = False,
    ):
        self.log.debug("upgrading {} in cluster {}".format(kdu_model, cluster_uuid))

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # look for instance to obtain namespace

        # set namespace
        if not namespace:
            instance_info = await self.get_instance_info(cluster_uuid, kdu_instance)
            if not instance_info:
                raise K8sException("kdu_instance {} not found".format(kdu_instance))
            namespace = instance_info["namespace"]

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # params to str
        params_str, file_to_delete = self._params_to_file_option(
            cluster_id=cluster_uuid, params=params
        )

        kdu_model, version = await self._prepare_helm_chart(kdu_model, cluster_uuid)

        labels_dict = None
        if db_dict and await self._contains_labels(
            kdu_instance, namespace, paths["kube_config"], env
        ):
            labels_dict = await self._labels_dict(db_dict, kdu_instance)

        command = self._get_upgrade_command(
            kdu_model,
            kdu_instance,
            namespace,
            params_str,
            labels_dict,
            version,
            atomic,
            timeout,
            paths["kube_config"],
            targetHostK8sLabels,
            reset_values,
            reuse_values,
            reset_then_reuse_values,
            force,
        )

        self.log.debug("upgrading: {}".format(command))

        if atomic:
            # exec helm in a task
            exec_task = asyncio.ensure_future(
                coro_or_future=self._local_async_exec(
                    command=command, raise_exception_on_error=False, env=env
                )
            )
            # write status in another task
            status_task = asyncio.ensure_future(
                coro_or_future=self._store_status(
                    cluster_id=cluster_uuid,
                    kdu_instance=kdu_instance,
                    namespace=namespace,
                    db_dict=db_dict,
                    operation="upgrade",
                )
            )

            # wait for execution task
            await asyncio.wait([exec_task])

            # cancel status task
            status_task.cancel()
            output, rc = exec_task.result()

        else:
            output, rc = await self._local_async_exec(
                command=command, raise_exception_on_error=False, env=env
            )

        # remove temporal values yaml file
        if file_to_delete:
            os.remove(file_to_delete)

        # write final status
        await self._store_status(
            cluster_id=cluster_uuid,
            kdu_instance=kdu_instance,
            namespace=namespace,
            db_dict=db_dict,
            operation="upgrade",
        )

        if rc != 0:
            msg = "Error executing command: {}\nOutput: {}".format(command, output)
            self.log.error(msg)
            raise K8sException(msg)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        # return new revision number
        instance = await self.get_instance_info(
            cluster_uuid=cluster_uuid, kdu_instance=kdu_instance
        )
        if instance:
            revision = int(instance.get("revision"))
            self.log.debug("New revision: {}".format(revision))
            return revision
        else:
            return 0

    async def scale(
        self,
        kdu_instance: str,
        scale: int,
        resource_name: str,
        total_timeout: float = 1800,
        cluster_uuid: str = None,
        kdu_model: str = None,
        atomic: bool = True,
        db_dict: dict = None,
        **kwargs,
    ):
        """Scale a resource in a Helm Chart.

        Args:
            kdu_instance: KDU instance name
            scale: Scale to which to set the resource
            resource_name: Resource name
            total_timeout: The time, in seconds, to wait
            cluster_uuid: The UUID of the cluster
            kdu_model: The chart reference
            atomic: if set, upgrade process rolls back changes made in case of failed upgrade.
                The --wait flag will be set automatically if --atomic is used
            db_dict: Dictionary for any additional data
            kwargs: Additional parameters

        Returns:
            True if successful, False otherwise
        """

        debug_mgs = "scaling {} in cluster {}".format(kdu_model, cluster_uuid)
        if resource_name:
            debug_mgs = "scaling resource {} in model {} (cluster {})".format(
                resource_name, kdu_model, cluster_uuid
            )

        self.log.debug(debug_mgs)

        # look for instance to obtain namespace
        # get_instance_info function calls the sync command
        instance_info = await self.get_instance_info(cluster_uuid, kdu_instance)
        if not instance_info:
            raise K8sException("kdu_instance {} not found".format(kdu_instance))

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # version
        kdu_model, version = await self._prepare_helm_chart(kdu_model, cluster_uuid)

        repo_url = await self._find_repo(kdu_model, cluster_uuid)

        _, replica_str = await self._get_replica_count_url(
            kdu_model, repo_url, resource_name
        )

        labels_dict = None
        if db_dict and await self._contains_labels(
            kdu_instance, instance_info["namespace"], paths["kube_config"], env
        ):
            labels_dict = await self._labels_dict(db_dict, kdu_instance)

        command = self._get_upgrade_scale_command(
            kdu_model,
            kdu_instance,
            instance_info["namespace"],
            scale,
            labels_dict,
            version,
            atomic,
            replica_str,
            total_timeout,
            resource_name,
            paths["kube_config"],
        )

        self.log.debug("scaling: {}".format(command))

        if atomic:
            # exec helm in a task
            exec_task = asyncio.ensure_future(
                coro_or_future=self._local_async_exec(
                    command=command, raise_exception_on_error=False, env=env
                )
            )
            # write status in another task
            status_task = asyncio.ensure_future(
                coro_or_future=self._store_status(
                    cluster_id=cluster_uuid,
                    kdu_instance=kdu_instance,
                    namespace=instance_info["namespace"],
                    db_dict=db_dict,
                    operation="scale",
                )
            )

            # wait for execution task
            await asyncio.wait([exec_task])

            # cancel status task
            status_task.cancel()
            output, rc = exec_task.result()

        else:
            output, rc = await self._local_async_exec(
                command=command, raise_exception_on_error=False, env=env
            )

        # write final status
        await self._store_status(
            cluster_id=cluster_uuid,
            kdu_instance=kdu_instance,
            namespace=instance_info["namespace"],
            db_dict=db_dict,
            operation="scale",
        )

        if rc != 0:
            msg = "Error executing command: {}\nOutput: {}".format(command, output)
            self.log.error(msg)
            raise K8sException(msg)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return True

    async def get_scale_count(
        self,
        resource_name: str,
        kdu_instance: str,
        cluster_uuid: str,
        kdu_model: str,
        **kwargs,
    ) -> int:
        """Get a resource scale count.

        Args:
            cluster_uuid: The UUID of the cluster
            resource_name: Resource name
            kdu_instance: KDU instance name
            kdu_model: The name or path of an Helm Chart
            kwargs: Additional parameters

        Returns:
            Resource instance count
        """

        self.log.debug(
            "getting scale count for {} in cluster {}".format(kdu_model, cluster_uuid)
        )

        # look for instance to obtain namespace
        instance_info = await self.get_instance_info(cluster_uuid, kdu_instance)
        if not instance_info:
            raise K8sException("kdu_instance {} not found".format(kdu_instance))

        # init env, paths
        paths, _ = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        replicas = await self._get_replica_count_instance(
            kdu_instance=kdu_instance,
            namespace=instance_info["namespace"],
            kubeconfig=paths["kube_config"],
            resource_name=resource_name,
        )

        self.log.debug(
            f"Number of replicas of the KDU instance {kdu_instance} and resource {resource_name} obtained: {replicas}"
        )

        # Get default value if scale count is not found from provided values
        # Important note: this piece of code shall only be executed in the first scaling operation,
        # since it is expected that the _get_replica_count_instance is able to obtain the number of
        # replicas when a scale operation was already conducted previously for this KDU/resource!
        if replicas is None:
            repo_url = await self._find_repo(
                kdu_model=kdu_model, cluster_uuid=cluster_uuid
            )
            replicas, _ = await self._get_replica_count_url(
                kdu_model=kdu_model, repo_url=repo_url, resource_name=resource_name
            )

            self.log.debug(
                f"Number of replicas of the Helm Chart package for KDU instance {kdu_instance} and resource "
                f"{resource_name} obtained: {replicas}"
            )

            if replicas is None:
                msg = "Replica count not found. Cannot be scaled"
                self.log.error(msg)
                raise K8sException(msg)

        return int(replicas)

    async def rollback(
        self, cluster_uuid: str, kdu_instance: str, revision=0, db_dict: dict = None
    ):
        self.log.debug(
            "rollback kdu_instance {} to revision {} from cluster {}".format(
                kdu_instance, revision, cluster_uuid
            )
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # look for instance to obtain namespace
        instance_info = await self.get_instance_info(cluster_uuid, kdu_instance)
        if not instance_info:
            raise K8sException("kdu_instance {} not found".format(kdu_instance))

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        command = self._get_rollback_command(
            kdu_instance, instance_info["namespace"], revision, paths["kube_config"]
        )

        self.log.debug("rolling_back: {}".format(command))

        # exec helm in a task
        exec_task = asyncio.ensure_future(
            coro_or_future=self._local_async_exec(
                command=command, raise_exception_on_error=False, env=env
            )
        )
        # write status in another task
        status_task = asyncio.ensure_future(
            coro_or_future=self._store_status(
                cluster_id=cluster_uuid,
                kdu_instance=kdu_instance,
                namespace=instance_info["namespace"],
                db_dict=db_dict,
                operation="rollback",
            )
        )

        # wait for execution task
        await asyncio.wait([exec_task])

        # cancel status task
        status_task.cancel()

        output, rc = exec_task.result()

        # write final status
        await self._store_status(
            cluster_id=cluster_uuid,
            kdu_instance=kdu_instance,
            namespace=instance_info["namespace"],
            db_dict=db_dict,
            operation="rollback",
        )

        if rc != 0:
            msg = "Error executing command: {}\nOutput: {}".format(command, output)
            self.log.error(msg)
            raise K8sException(msg)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        # return new revision number
        instance = await self.get_instance_info(
            cluster_uuid=cluster_uuid, kdu_instance=kdu_instance
        )
        if instance:
            revision = int(instance.get("revision"))
            self.log.debug("New revision: {}".format(revision))
            return revision
        else:
            return 0

    async def uninstall(self, cluster_uuid: str, kdu_instance: str, **kwargs):
        """
        Removes an existing KDU instance. It would implicitly use the `delete` or 'uninstall' call
        (this call should happen after all _terminate-config-primitive_ of the VNF
        are invoked).

        :param cluster_uuid: UUID of a K8s cluster known by OSM, or namespace:cluster_id
        :param kdu_instance: unique name for the KDU instance to be deleted
        :param kwargs: Additional parameters (None yet)
        :return: True if successful
        """

        self.log.debug(
            "uninstall kdu_instance {} from cluster {}".format(
                kdu_instance, cluster_uuid
            )
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # look for instance to obtain namespace
        instance_info = await self.get_instance_info(cluster_uuid, kdu_instance)
        if not instance_info:
            self.log.warning(("kdu_instance {} not found".format(kdu_instance)))
            return True
        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        command = self._get_uninstall_command(
            kdu_instance, instance_info["namespace"], paths["kube_config"]
        )
        output, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return self._output_to_table(output)

    async def instances_list(self, cluster_uuid: str) -> list:
        """
        returns a list of deployed releases in a cluster

        :param cluster_uuid: the 'cluster' or 'namespace:cluster'
        :return:
        """

        self.log.debug("list releases for cluster {}".format(cluster_uuid))

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # execute internal command
        result = await self._instances_list(cluster_uuid)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return result

    async def get_instance_info(self, cluster_uuid: str, kdu_instance: str):
        instances = await self.instances_list(cluster_uuid=cluster_uuid)
        for instance in instances:
            if instance.get("name") == kdu_instance:
                return instance
        self.log.debug("Instance {} not found".format(kdu_instance))
        return None

    async def upgrade_charm(
        self,
        ee_id: str = None,
        path: str = None,
        charm_id: str = None,
        charm_type: str = None,
        timeout: float = None,
    ) -> str:
        """This method upgrade charms in VNFs

        Args:
            ee_id:  Execution environment id
            path:   Local path to the charm
            charm_id:   charm-id
            charm_type: Charm type can be lxc-proxy-charm, native-charm or k8s-proxy-charm
            timeout: (Float)    Timeout for the ns update operation

        Returns:
            The output of the update operation if status equals to "completed"
        """
        raise K8sException("KDUs deployed with Helm do not support charm upgrade")

    async def exec_primitive(
        self,
        cluster_uuid: str = None,
        kdu_instance: str = None,
        primitive_name: str = None,
        timeout: float = 300,
        params: dict = None,
        db_dict: dict = None,
        **kwargs,
    ) -> str:
        """Exec primitive (Juju action)

        :param cluster_uuid: The UUID of the cluster or namespace:cluster
        :param kdu_instance: The unique name of the KDU instance
        :param primitive_name: Name of action that will be executed
        :param timeout: Timeout for action execution
        :param params: Dictionary of all the parameters needed for the action
        :db_dict: Dictionary for any additional data
        :param kwargs: Additional parameters (None yet)

        :return: Returns the output of the action
        """
        raise K8sException(
            "KDUs deployed with Helm don't support actions "
            "different from rollback, upgrade and status"
        )

    async def get_services(
        self, cluster_uuid: str, kdu_instance: str, namespace: str
    ) -> list:
        """
        Returns a list of services defined for the specified kdu instance.

        :param cluster_uuid: UUID of a K8s cluster known by OSM
        :param kdu_instance: unique name for the KDU instance
        :param namespace: K8s namespace used by the KDU instance
        :return: If successful, it will return a list of services, Each service
        can have the following data:
        - `name` of the service
        - `type` type of service in the k8 cluster
        - `ports` List of ports offered by the service, for each port includes at least
        name, port, protocol
        - `cluster_ip` Internal ip to be used inside k8s cluster
        - `external_ip` List of external ips (in case they are available)
        """

        self.log.debug(
            "get_services: cluster_uuid: {}, kdu_instance: {}".format(
                cluster_uuid, kdu_instance
            )
        )

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # get list of services names for kdu
        service_names = await self._get_services(
            cluster_uuid, kdu_instance, namespace, paths["kube_config"]
        )

        service_list = []
        for service in service_names:
            service = await self._get_service(cluster_uuid, service, namespace)
            service_list.append(service)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return service_list

    async def get_service(
        self, cluster_uuid: str, service_name: str, namespace: str
    ) -> object:
        self.log.debug(
            "get service, service_name: {}, namespace: {}, cluster_uuid: {}".format(
                service_name, namespace, cluster_uuid
            )
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        service = await self._get_service(cluster_uuid, service_name, namespace)

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return service

    async def status_kdu(
        self, cluster_uuid: str, kdu_instance: str, yaml_format: str = False, **kwargs
    ) -> Union[str, dict]:
        """
        This call would retrieve tha current state of a given KDU instance. It would be
        would allow to retrieve the _composition_ (i.e. K8s objects) and _specific
        values_ of the configuration parameters applied to a given instance. This call
        would be based on the `status` call.

        :param cluster_uuid: UUID of a K8s cluster known by OSM
        :param kdu_instance: unique name for the KDU instance
        :param kwargs: Additional parameters (None yet)
        :param yaml_format: if the return shall be returned as an YAML string or as a
                                dictionary
        :return: If successful, it will return the following vector of arguments:
        - K8s `namespace` in the cluster where the KDU lives
        - `state` of the KDU instance. It can be:
              - UNKNOWN
              - DEPLOYED
              - DELETED
              - SUPERSEDED
              - FAILED or
              - DELETING
        - List of `resources` (objects) that this release consists of, sorted by kind,
          and the status of those resources
        - Last `deployment_time`.

        """
        self.log.debug(
            "status_kdu: cluster_uuid: {}, kdu_instance: {}".format(
                cluster_uuid, kdu_instance
            )
        )

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # get instance: needed to obtain namespace
        instances = await self._instances_list(cluster_id=cluster_uuid)
        for instance in instances:
            if instance.get("name") == kdu_instance:
                break
        else:
            # instance does not exist
            raise K8sException(
                "Instance name: {} not found in cluster: {}".format(
                    kdu_instance, cluster_uuid
                )
            )

        status = await self._status_kdu(
            cluster_id=cluster_uuid,
            kdu_instance=kdu_instance,
            namespace=instance["namespace"],
            yaml_format=yaml_format,
            show_error_log=True,
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        return status

    async def get_values_kdu(
        self, kdu_instance: str, namespace: str, kubeconfig: str
    ) -> str:
        self.log.debug("get kdu_instance values {}".format(kdu_instance))

        return await self._exec_get_command(
            get_command="values",
            kdu_instance=kdu_instance,
            namespace=namespace,
            kubeconfig=kubeconfig,
        )

    async def values_kdu(self, kdu_model: str, repo_url: str = None) -> str:
        """Method to obtain the Helm Chart package's values

        Args:
            kdu_model: The name or path of an Helm Chart
            repo_url: Helm Chart repository url

        Returns:
            str: the values of the Helm Chart package
        """

        self.log.debug(
            "inspect kdu_model values {} from (optional) repo: {}".format(
                kdu_model, repo_url
            )
        )

        return await self._exec_inspect_command(
            inspect_command="values", kdu_model=kdu_model, repo_url=repo_url
        )

    async def help_kdu(self, kdu_model: str, repo_url: str = None) -> str:
        self.log.debug(
            "inspect kdu_model {} readme.md from repo: {}".format(kdu_model, repo_url)
        )

        return await self._exec_inspect_command(
            inspect_command="readme", kdu_model=kdu_model, repo_url=repo_url
        )

    async def synchronize_repos(self, cluster_uuid: str):
        self.log.debug("synchronize repos for cluster helm-id: {}".format(cluster_uuid))
        try:
            db_repo_ids = self._get_helm_chart_repos_ids(cluster_uuid)
            db_repo_dict = self._get_db_repos_dict(db_repo_ids)

            local_repo_list = await self.repo_list(cluster_uuid)
            local_repo_dict = {repo["name"]: repo["url"] for repo in local_repo_list}

            deleted_repo_list = []
            added_repo_dict = {}

            # iterate over the list of repos in the database that should be
            # added if not present
            for repo_name, db_repo in db_repo_dict.items():
                try:
                    # check if it is already present
                    curr_repo_url = local_repo_dict.get(db_repo["name"])
                    repo_id = db_repo.get("_id")
                    if curr_repo_url != db_repo["url"]:
                        if curr_repo_url:
                            self.log.debug(
                                "repo {} url changed, delete and and again".format(
                                    db_repo["url"]
                                )
                            )
                            await self.repo_remove(cluster_uuid, db_repo["name"])
                            deleted_repo_list.append(repo_id)

                        # add repo
                        self.log.debug("add repo {}".format(db_repo["name"]))
                        await self.repo_add(
                            cluster_uuid,
                            db_repo["name"],
                            db_repo["url"],
                            cert=db_repo.get("ca_cert"),
                            user=db_repo.get("user"),
                            password=db_repo.get("password"),
                            oci=db_repo.get("oci", False),
                        )
                        added_repo_dict[repo_id] = db_repo["name"]
                except Exception as e:
                    raise K8sException(
                        "Error adding repo id: {}, err_msg: {} ".format(
                            repo_id, repr(e)
                        )
                    )

            # Delete repos that are present but not in nbi_list
            for repo_name in local_repo_dict:
                if not db_repo_dict.get(repo_name) and repo_name != "stable":
                    self.log.debug("delete repo {}".format(repo_name))
                    try:
                        await self.repo_remove(cluster_uuid, repo_name)
                        deleted_repo_list.append(repo_name)
                    except Exception as e:
                        self.warning(
                            "Error deleting repo, name: {}, err_msg: {}".format(
                                repo_name, str(e)
                            )
                        )

            return deleted_repo_list, added_repo_dict

        except K8sException:
            raise
        except Exception as e:
            # Do not raise errors synchronizing repos
            self.log.error("Error synchronizing repos: {}".format(e))
            raise Exception("Error synchronizing repos: {}".format(e))

    def _get_db_repos_dict(self, repo_ids: list):
        db_repos_dict = {}
        for repo_id in repo_ids:
            db_repo = self.db.get_one("k8srepos", {"_id": repo_id})
            db_repos_dict[db_repo["name"]] = db_repo
        return db_repos_dict

    """
    ####################################################################################
    ################################### TO BE IMPLEMENTED SUBCLASSES ###################
    ####################################################################################
    """

    @abc.abstractmethod
    def _init_paths_env(self, cluster_name: str, create_if_not_exist: bool = True):
        """
        Creates and returns base cluster and kube dirs and returns them.
        Also created helm3 dirs according to new directory specification, paths are
        not returned but assigned to helm environment variables

        :param cluster_name:  cluster_name
        :return: Dictionary with config_paths and dictionary with helm environment variables
        """

    @abc.abstractmethod
    async def _cluster_init(self, cluster_id, namespace, paths, env):
        """
        Implements the helm version dependent cluster initialization
        """

    @abc.abstractmethod
    async def _instances_list(self, cluster_id):
        """
        Implements the helm version dependent helm instances list
        """

    @abc.abstractmethod
    async def _get_services(self, cluster_id, kdu_instance, namespace, kubeconfig):
        """
        Implements the helm version dependent method to obtain services from a helm instance
        """

    @abc.abstractmethod
    async def _status_kdu(
        self,
        cluster_id: str,
        kdu_instance: str,
        namespace: str = None,
        yaml_format: bool = False,
        show_error_log: bool = False,
    ) -> Union[str, dict]:
        """
        Implements the helm version dependent method to obtain status of a helm instance
        """

    @abc.abstractmethod
    def _get_install_command(
        self,
        kdu_model,
        kdu_instance,
        namespace,
        labels,
        params_str,
        version,
        atomic,
        timeout,
        kubeconfig,
    ) -> str:
        """
        Obtain command to be executed to delete the indicated instance
        """

    @abc.abstractmethod
    def _get_upgrade_scale_command(
        self,
        kdu_model,
        kdu_instance,
        namespace,
        count,
        labels,
        version,
        atomic,
        replicas,
        timeout,
        resource_name,
        kubeconfig,
    ) -> str:
        """Generates the command to scale a Helm Chart release

        Args:
            kdu_model (str): Kdu model name, corresponding to the Helm local location or repository
            kdu_instance (str): KDU instance, corresponding to the Helm Chart release in question
            namespace (str): Namespace where this KDU instance is deployed
            scale (int): Scale count
            version (str): Constraint with specific version of the Chart to use
            atomic (bool): If set, upgrade process rolls back changes made in case of failed upgrade.
                The --wait flag will be set automatically if --atomic is used
            replica_str (str): The key under resource_name key where the scale count is stored
            timeout (float): The time, in seconds, to wait
            resource_name (str): The KDU's resource to scale
            kubeconfig (str): Kubeconfig file path

        Returns:
            str: command to scale a Helm Chart release
        """

    @abc.abstractmethod
    def _get_upgrade_command(
        self,
        kdu_model,
        kdu_instance,
        namespace,
        params_str,
        labels,
        version,
        atomic,
        timeout,
        kubeconfig,
        targetHostK8sLabels,
        reset_values,
        reuse_values,
        reset_then_reuse_values,
        force,
    ) -> str:
        """Generates the command to upgrade a Helm Chart release

        Args:
            kdu_model (str): Kdu model name, corresponding to the Helm local location or repository
            kdu_instance (str): KDU instance, corresponding to the Helm Chart release in question
            namespace (str): Namespace where this KDU instance is deployed
            params_str (str): Params used to upgrade the Helm Chart release
            version (str): Constraint with specific version of the Chart to use
            atomic (bool): If set, upgrade process rolls back changes made in case of failed upgrade.
                The --wait flag will be set automatically if --atomic is used
            timeout (float): The time, in seconds, to wait
            kubeconfig (str): Kubeconfig file path
            reset_values(bool): If set, helm resets values instead of reusing previous values.
            reuse_values(bool): If set, helm reuses previous values.
            reset_then_reuse_values(bool): If set, helm resets values, then apply the last release's values
            force (bool): If set, helm forces resource updates through a replacement strategy. This may recreate pods.
        Returns:
            str: command to upgrade a Helm Chart release
        """

    @abc.abstractmethod
    def _get_rollback_command(
        self, kdu_instance, namespace, revision, kubeconfig
    ) -> str:
        """
        Obtain command to be executed to rollback the indicated instance
        """

    @abc.abstractmethod
    def _get_uninstall_command(
        self, kdu_instance: str, namespace: str, kubeconfig: str
    ) -> str:
        """
        Obtain command to be executed to delete the indicated instance
        """

    @abc.abstractmethod
    def _get_inspect_command(
        self, show_command: str, kdu_model: str, repo_str: str, version: str
    ):
        """Generates the command to obtain the information about an Helm Chart package
            (´helm show ...´ command)

        Args:
            show_command: the second part of the command (`helm show <show_command>`)
            kdu_model: The name or path of an Helm Chart
            repo_url: Helm Chart repository url
            version: constraint with specific version of the Chart to use

        Returns:
            str: the generated Helm Chart command
        """

    @abc.abstractmethod
    def _get_get_command(
        self, get_command: str, kdu_instance: str, namespace: str, kubeconfig: str
    ):
        """Obtain command to be executed to get information about the kdu instance."""

    @abc.abstractmethod
    async def _uninstall_sw(self, cluster_id: str, namespace: str):
        """
        Method call to uninstall cluster software for helm. This method is dependent
        of helm version
        For Helm v2 it will be called when Tiller must be uninstalled
        For Helm v3 it does nothing and does not need to be callled
        """

    @abc.abstractmethod
    def _get_helm_chart_repos_ids(self, cluster_uuid) -> list:
        """
        Obtains the cluster repos identifiers
        """

    """
    ####################################################################################
    ################################### P R I V A T E ##################################
    ####################################################################################
    """

    @staticmethod
    def _check_file_exists(filename: str, exception_if_not_exists: bool = False):
        if os.path.exists(filename):
            return True
        else:
            msg = "File {} does not exist".format(filename)
            if exception_if_not_exists:
                raise K8sException(msg)

    @staticmethod
    def _remove_multiple_spaces(strobj):
        strobj = strobj.strip()
        while "  " in strobj:
            strobj = strobj.replace("  ", " ")
        return strobj

    @staticmethod
    def _output_to_lines(output: str) -> list:
        output_lines = list()
        lines = output.splitlines(keepends=False)
        for line in lines:
            line = line.strip()
            if len(line) > 0:
                output_lines.append(line)
        return output_lines

    @staticmethod
    def _output_to_table(output: str) -> list:
        output_table = list()
        lines = output.splitlines(keepends=False)
        for line in lines:
            line = line.replace("\t", " ")
            line_list = list()
            output_table.append(line_list)
            cells = line.split(sep=" ")
            for cell in cells:
                cell = cell.strip()
                if len(cell) > 0:
                    line_list.append(cell)
        return output_table

    def _parse_services(self, yaml_input: str) -> list:
        """
        Parses the output of a command to extract service names.
        """

        def get_manifest_services(manifest: dict) -> list:
            """
            Extracts service names from a manifest dictionary.
            """
            manifest_services = []
            if "kind" in manifest and manifest["kind"] == "Service":
                if "metadata" in manifest and "name" in manifest["metadata"]:
                    manifest_services.append(manifest["metadata"]["name"])
            return manifest_services

        service_list = []
        self.log.debug("Parsing YAML manifests to obtain list of services...")
        manifest_generator = yaml.safe_load_all(yaml_input)
        i = 1
        while True:
            try:
                manifest = next(manifest_generator)
            except StopIteration:
                break
            except yaml.YAMLError as e:
                self.log.error("Skipping manifest %d due to YAML error: %s", i, e)
                i += 1
                continue
            if not manifest:
                continue
            manifest_services = get_manifest_services(manifest)
            if manifest_services:
                service_list.extend(manifest_services)
        return service_list

    @staticmethod
    def _get_deep(dictionary: dict, members: tuple):
        target = dictionary
        value = None
        try:
            for m in members:
                value = target.get(m)
                if not value:
                    return None
                else:
                    target = value
        except Exception:
            pass
        return value

    # find key:value in several lines
    @staticmethod
    def _find_in_lines(p_lines: list, p_key: str) -> str:
        for line in p_lines:
            try:
                if line.startswith(p_key + ":"):
                    parts = line.split(":")
                    the_value = parts[1].strip()
                    return the_value
            except Exception:
                # ignore it
                pass
        return None

    @staticmethod
    def _lower_keys_list(input_list: list):
        """
        Transform the keys in a list of dictionaries to lower case and returns a new list
        of dictionaries
        """
        new_list = []
        if input_list:
            for dictionary in input_list:
                new_dict = dict((k.lower(), v) for k, v in dictionary.items())
                new_list.append(new_dict)
        return new_list

    async def _local_async_exec(
        self,
        command: str,
        raise_exception_on_error: bool = False,
        show_error_log: bool = True,
        encode_utf8: bool = False,
        env: dict = None,
    ) -> tuple[str, int]:
        command = K8sHelmBaseConnector._remove_multiple_spaces(command)
        self.log.debug(
            "Executing async local command: {}, env: {}".format(command, env)
        )

        # split command
        command = shlex.split(command)

        environ = os.environ.copy()
        if env:
            environ.update(env)

        try:
            async with self.cmd_lock:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=environ,
                )

                # wait for command terminate
                stdout, stderr = await process.communicate()

                return_code = process.returncode

            output = ""
            if stdout:
                output = stdout.decode("utf-8").strip()
                # output = stdout.decode()
            if stderr:
                output = stderr.decode("utf-8").strip()
                # output = stderr.decode()

            if return_code != 0 and show_error_log:
                self.log.debug(
                    "Return code (FAIL): {}\nOutput:\n{}".format(return_code, output)
                )
            else:
                self.log.debug("Return code: {}".format(return_code))

            if raise_exception_on_error and return_code != 0:
                raise K8sException(output)

            if encode_utf8:
                output = output.encode("utf-8").strip()
                output = str(output).replace("\\n", "\n")

            return output, return_code

        except asyncio.CancelledError:
            # first, kill the process if it is still running
            if process.returncode is None:
                process.kill()
            raise
        except K8sException:
            raise
        except Exception as e:
            msg = "Exception executing command: {} -> {}".format(command, e)
            self.log.error(msg)
            if raise_exception_on_error:
                raise K8sException(e) from e
            else:
                return "", -1

    async def _get_service(self, cluster_id, service_name, namespace):
        """
        Obtains the data of the specified service in the k8cluster.

        :param cluster_id: id of a K8s cluster known by OSM
        :param service_name: name of the K8s service in the specified namespace
        :param namespace: K8s namespace used by the KDU instance
        :return: If successful, it will return a service with the following data:
        - `name` of the service
        - `type` type of service in the k8 cluster
        - `ports` List of ports offered by the service, for each port includes at least
        name, port, protocol
        - `cluster_ip` Internal ip to be used inside k8s cluster
        - `external_ip` List of external ips (in case they are available)
        """

        # init config, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        command = "{} --kubeconfig={} --namespace={} get service {} -o=yaml".format(
            self.kubectl_command,
            paths["kube_config"],
            quote(namespace),
            quote(service_name),
        )

        output, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        data = yaml.load(output, Loader=yaml.SafeLoader)

        service = {
            "name": service_name,
            "type": self._get_deep(data, ("spec", "type")),
            "ports": self._get_deep(data, ("spec", "ports")),
            "cluster_ip": self._get_deep(data, ("spec", "clusterIP")),
        }
        if service["type"] == "LoadBalancer":
            ip_map_list = self._get_deep(data, ("status", "loadBalancer", "ingress"))
            ip_list = [elem["ip"] for elem in ip_map_list]
            service["external_ip"] = ip_list

        return service

    async def _exec_get_command(
        self, get_command: str, kdu_instance: str, namespace: str, kubeconfig: str
    ):
        """Obtains information about the kdu instance."""

        full_command = self._get_get_command(
            get_command, kdu_instance, namespace, kubeconfig
        )

        output, _rc = await self._local_async_exec(command=full_command)

        return output

    async def _exec_inspect_command(
        self, inspect_command: str, kdu_model: str, repo_url: str = None
    ):
        """Obtains information about an Helm Chart package (´helm show´ command)

        Args:
            inspect_command: the Helm sub command (`helm show <inspect_command> ...`)
            kdu_model: The name or path of an Helm Chart
            repo_url: Helm Chart repository url

        Returns:
            str: the requested info about the Helm Chart package
        """

        repo_str = ""
        if repo_url:
            repo_str = " --repo {}".format(quote(repo_url))

            # Obtain the Chart's name and store it in the var kdu_model
            kdu_model, _ = self._split_repo(kdu_model=kdu_model)

        kdu_model, version = self._split_version(kdu_model)
        if version:
            version_str = "--version {}".format(quote(version))
        else:
            version_str = ""

        full_command = self._get_inspect_command(
            show_command=inspect_command,
            kdu_model=quote(kdu_model),
            repo_str=repo_str,
            version=version_str,
        )

        output, _ = await self._local_async_exec(command=full_command)

        return output

    async def _get_replica_count_url(
        self,
        kdu_model: str,
        repo_url: str = None,
        resource_name: str = None,
    ) -> tuple[int, str]:
        """Get the replica count value in the Helm Chart Values.

        Args:
            kdu_model: The name or path of an Helm Chart
            repo_url: Helm Chart repository url
            resource_name: Resource name

        Returns:
            A tuple with:
            - The number of replicas of the specific instance; if not found, returns None; and
            - The string corresponding to the replica count key in the Helm values
        """

        kdu_values = yaml.load(
            await self.values_kdu(kdu_model=kdu_model, repo_url=repo_url),
            Loader=yaml.SafeLoader,
        )

        self.log.debug(f"Obtained the Helm package values for the KDU: {kdu_values}")

        if not kdu_values:
            raise K8sException(
                "kdu_values not found for kdu_model {}".format(kdu_model)
            )

        if resource_name:
            kdu_values = kdu_values.get(resource_name, None)

        if not kdu_values:
            msg = "resource {} not found in the values in model {}".format(
                resource_name, kdu_model
            )
            self.log.error(msg)
            raise K8sException(msg)

        duplicate_check = False

        replica_str = ""
        replicas = None

        if kdu_values.get("replicaCount") is not None:
            replicas = kdu_values["replicaCount"]
            replica_str = "replicaCount"
        elif kdu_values.get("replicas") is not None:
            duplicate_check = True
            replicas = kdu_values["replicas"]
            replica_str = "replicas"
        else:
            if resource_name:
                msg = (
                    "replicaCount or replicas not found in the resource"
                    "{} values in model {}. Cannot be scaled".format(
                        resource_name, kdu_model
                    )
                )
            else:
                msg = (
                    "replicaCount or replicas not found in the values"
                    "in model {}. Cannot be scaled".format(kdu_model)
                )
            self.log.error(msg)
            raise K8sException(msg)

        # Control if replicas and replicaCount exists at the same time
        msg = "replicaCount and replicas are exists at the same time"
        if duplicate_check:
            if "replicaCount" in kdu_values:
                self.log.error(msg)
                raise K8sException(msg)
        else:
            if "replicas" in kdu_values:
                self.log.error(msg)
                raise K8sException(msg)

        return replicas, replica_str

    async def _get_replica_count_instance(
        self,
        kdu_instance: str,
        namespace: str,
        kubeconfig: str,
        resource_name: str = None,
    ) -> int:
        """Get the replica count value in the instance.

        Args:
            kdu_instance: The name of the KDU instance
            namespace: KDU instance namespace
            kubeconfig:
            resource_name: Resource name

        Returns:
            The number of replicas of the specific instance; if not found, returns None
        """

        kdu_values = yaml.load(
            await self.get_values_kdu(kdu_instance, namespace, kubeconfig),
            Loader=yaml.SafeLoader,
        )

        self.log.debug(f"Obtained the Helm values for the KDU instance: {kdu_values}")

        replicas = None

        if kdu_values:
            resource_values = (
                kdu_values.get(resource_name, None) if resource_name else None
            )

            for replica_str in ("replicaCount", "replicas"):
                if resource_values:
                    replicas = resource_values.get(replica_str)
                else:
                    replicas = kdu_values.get(replica_str)

                if replicas is not None:
                    break

        return replicas

    async def _labels_dict(self, db_dict, kdu_instance):
        # get the network service registry
        ns_id = db_dict["filter"]["_id"]
        try:
            db_nsr = self.db.get_one("nsrs", {"_id": ns_id})
        except Exception as e:
            print("nsr {} not found: {}".format(ns_id, e))
        nsd_id = db_nsr["nsd"]["_id"]

        # get the kdu registry
        for index, kdu in enumerate(db_nsr["_admin"]["deployed"]["K8s"]):
            if kdu["kdu-instance"] == kdu_instance:
                db_kdur = kdu
                break
        else:
            # No kdur found, could be the case of an EE chart
            return {}

        kdu_name = db_kdur["kdu-name"]
        member_vnf_index = db_kdur["member-vnf-index"]
        # get the vnf registry
        try:
            db_vnfr = self.db.get_one(
                "vnfrs",
                {"nsr-id-ref": ns_id, "member-vnf-index-ref": member_vnf_index},
            )
        except Exception as e:
            print("vnfr {} not found: {}".format(member_vnf_index, e))

        vnf_id = db_vnfr["_id"]
        vnfd_id = db_vnfr["vnfd-id"]

        return {
            "managed-by": "osm.etsi.org",
            "osm.etsi.org/ns-id": ns_id,
            "osm.etsi.org/nsd-id": nsd_id,
            "osm.etsi.org/vnf-id": vnf_id,
            "osm.etsi.org/vnfd-id": vnfd_id,
            "osm.etsi.org/kdu-id": kdu_instance,
            "osm.etsi.org/kdu-name": kdu_name,
        }

    async def _contains_labels(self, kdu_instance, namespace, kube_config, env):
        command = "env KUBECONFIG={} {} get manifest {} --namespace={}".format(
            kube_config,
            self._helm_command,
            quote(kdu_instance),
            quote(namespace),
        )
        output, rc = await self._local_async_exec(
            command=command, raise_exception_on_error=False, env=env
        )
        manifests = yaml.safe_load_all(output)
        for manifest in manifests:
            # Check if the manifest has metadata and labels
            if (
                manifest is not None
                and "metadata" in manifest
                and "labels" in manifest["metadata"]
            ):
                labels = {
                    "managed-by",
                    "osm.etsi.org/kdu-id",
                    "osm.etsi.org/kdu-name",
                    "osm.etsi.org/ns-id",
                    "osm.etsi.org/nsd-id",
                    "osm.etsi.org/vnf-id",
                    "osm.etsi.org/vnfd-id",
                }
                if labels.issubset(manifest["metadata"]["labels"].keys()):
                    return True
        return False

    async def _store_status(
        self,
        cluster_id: str,
        operation: str,
        kdu_instance: str,
        namespace: str = None,
        db_dict: dict = None,
    ) -> None:
        """
        Obtains the status of the KDU instance based on Helm Charts, and stores it in the database.

        :param cluster_id (str): the cluster where the KDU instance is deployed
        :param operation (str): The operation related to the status to be updated (for instance, "install" or "upgrade")
        :param kdu_instance (str): The KDU instance in relation to which the status is obtained
        :param namespace (str): The Kubernetes namespace where the KDU instance was deployed. Defaults to None
        :param db_dict (dict): A dictionary with the database necessary information. It shall contain the
        values for the keys:
            - "collection": The Mongo DB collection to write to
            - "filter": The query filter to use in the update process
            - "path": The dot separated keys which targets the object to be updated
        Defaults to None.
        """

        try:
            detailed_status = await self._status_kdu(
                cluster_id=cluster_id,
                kdu_instance=kdu_instance,
                yaml_format=False,
                namespace=namespace,
            )

            status = detailed_status.get("info").get("description")
            self.log.debug(f"Status for KDU {kdu_instance} obtained: {status}.")

            # write status to db
            result = await self.write_app_status_to_db(
                db_dict=db_dict,
                status=str(status),
                detailed_status=str(detailed_status),
                operation=operation,
            )

            if not result:
                self.log.info("Error writing in database. Task exiting...")

        except asyncio.CancelledError as e:
            self.log.warning(
                f"Exception in method {self._store_status.__name__} (task cancelled): {e}"
            )
        except Exception as e:
            self.log.warning(f"Exception in method {self._store_status.__name__}: {e}")

    # params for use in -f file
    # returns values file option and filename (in order to delete it at the end)
    def _params_to_file_option(self, cluster_id: str, params: dict) -> tuple[str, str]:
        if params and len(params) > 0:
            self._init_paths_env(cluster_name=cluster_id, create_if_not_exist=True)

            def get_random_number():
                r = random.SystemRandom().randint(1, 99999999)
                s = str(r)
                while len(s) < 10:
                    s = "0" + s
                return s

            params2 = dict()
            for key in params:
                value = params.get(key)
                if "!!yaml" in str(value):
                    value = yaml.safe_load(value[7:])
                params2[key] = value

            values_file = get_random_number() + ".yaml"
            with open(values_file, "w") as stream:
                yaml.dump(params2, stream, indent=4, default_flow_style=False)

            return "-f {}".format(values_file), values_file

        return "", None

    # params for use in --set option
    @staticmethod
    def _params_to_set_option(params: dict) -> str:
        pairs = [
            f"{quote(str(key))}={quote(str(value))}"
            for key, value in params.items()
            if value is not None
        ]
        if not pairs:
            return ""
        return "--set " + ",".join(pairs)

    @staticmethod
    def generate_kdu_instance_name(**kwargs):
        chart_name = kwargs["kdu_model"]
        # check embeded chart (file or dir)
        if chart_name.startswith("/"):
            # extract file or directory name
            chart_name = chart_name[chart_name.rfind("/") + 1 :]
        # check URL
        elif "://" in chart_name:
            # extract last portion of URL
            chart_name = chart_name[chart_name.rfind("/") + 1 :]

        name = ""
        for c in chart_name:
            if c.isalpha() or c.isnumeric():
                name += c
            else:
                name += "-"
        if len(name) > 35:
            name = name[0:35]

        # if does not start with alpha character, prefix 'a'
        if not name[0].isalpha():
            name = "a" + name

        name += "-"

        def get_random_number():
            r = random.SystemRandom().randint(1, 99999999)
            s = str(r)
            s = s.rjust(10, "0")
            return s

        name = name + get_random_number()
        return name.lower()

    def _split_version(self, kdu_model: str) -> tuple[str, str]:
        version = None
        if (
            not (
                self._is_helm_chart_a_file(kdu_model)
                or self._is_helm_chart_a_url(kdu_model)
            )
            and ":" in kdu_model
        ):
            parts = kdu_model.split(sep=":")
            if len(parts) == 2:
                version = str(parts[1])
                kdu_model = parts[0]
        return kdu_model, version

    def _split_repo(self, kdu_model: str) -> tuple[str, str]:
        """Obtain the Helm Chart's repository and Chart's names from the KDU model

        Args:
            kdu_model (str): Associated KDU model

        Returns:
            (str, str): Tuple with the Chart name in index 0, and the repo name
                        in index 2; if there was a problem finding them, return None
                        for both
        """

        chart_name = None
        repo_name = None

        idx = kdu_model.find("/")
        if not self._is_helm_chart_a_url(kdu_model) and idx >= 0:
            chart_name = kdu_model[idx + 1 :]
            repo_name = kdu_model[:idx]

        return chart_name, repo_name

    async def _find_repo(self, kdu_model: str, cluster_uuid: str) -> str:
        """Obtain the Helm repository for an Helm Chart

        Args:
            kdu_model (str): the KDU model associated with the Helm Chart instantiation
            cluster_uuid (str): The cluster UUID associated with the Helm Chart instantiation

        Returns:
            str: the repository URL; if Helm Chart is a local one, the function returns None
        """

        _, repo_name = self._split_repo(kdu_model=kdu_model)

        repo_url = None
        if repo_name:
            # Find repository link
            local_repo_list = await self.repo_list(cluster_uuid)
            for repo in local_repo_list:
                if repo["name"] == repo_name:
                    repo_url = repo["url"]
                    break  # it is not necessary to continue the loop if the repo link was found...

        return repo_url

    def _repo_to_oci_url(self, repo):
        db_repo = self.db.get_one("k8srepos", {"name": repo}, fail_on_empty=False)
        if db_repo and "oci" in db_repo:
            return db_repo.get("url")

    async def _prepare_helm_chart(self, kdu_model, cluster_id):
        # e.g.: "stable/openldap", "1.0"
        kdu_model, version = self._split_version(kdu_model)
        # e.g.: "openldap, stable"
        chart_name, repo = self._split_repo(kdu_model)
        if repo and chart_name:  # repo/chart case
            oci_url = self._repo_to_oci_url(repo)
            if oci_url:  # oci does not require helm repo update
                kdu_model = f"{oci_url.rstrip('/')}/{chart_name.lstrip('/')}"  # urljoin doesn't work for oci schema
            else:
                await self.repo_update(cluster_id, repo)
        return kdu_model, version

    async def create_certificate(
        self, cluster_uuid, namespace, dns_prefix, name, secret_name, usage
    ):
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        await kubectl.create_certificate(
            namespace=namespace,
            name=name,
            dns_prefix=dns_prefix,
            secret_name=secret_name,
            usages=[usage],
            issuer_name="ca-issuer",
        )

    async def delete_certificate(self, cluster_uuid, namespace, certificate_name):
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        await kubectl.delete_certificate(namespace, certificate_name)

    async def create_namespace(
        self,
        namespace,
        cluster_uuid,
        labels,
    ):
        """
        Create a namespace in a specific cluster

        :param namespace:    Namespace to be created
        :param cluster_uuid: K8s cluster uuid used to retrieve kubeconfig
        :param labels:       Dictionary with labels for the new namespace
        :returns: None
        """
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        await kubectl.create_namespace(
            name=namespace,
            labels=labels,
        )

    async def delete_namespace(
        self,
        namespace,
        cluster_uuid,
    ):
        """
        Delete a namespace in a specific cluster

        :param namespace: namespace to be deleted
        :param cluster_uuid: K8s cluster uuid used to retrieve kubeconfig
        :returns: None
        """
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        await kubectl.delete_namespace(
            name=namespace,
        )

    async def copy_secret_data(
        self,
        src_secret: str,
        dst_secret: str,
        cluster_uuid: str,
        data_key: str,
        src_namespace: str = "osm",
        dst_namespace: str = "osm",
    ):
        """
        Copy a single key and value from an existing secret to a new one

        :param src_secret: name of the existing secret
        :param dst_secret: name of the new secret
        :param cluster_uuid: K8s cluster uuid used to retrieve kubeconfig
        :param data_key: key of the existing secret to be copied
        :param src_namespace: Namespace of the existing secret
        :param dst_namespace: Namespace of the new secret
        :returns: None
        """
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        secret_data = await kubectl.get_secret_content(
            name=src_secret,
            namespace=src_namespace,
        )
        # Only the corresponding data_key value needs to be copy
        data = {data_key: secret_data.get(data_key)}
        await kubectl.create_secret(
            name=dst_secret,
            data=data,
            namespace=dst_namespace,
            secret_type="Opaque",
        )

    async def setup_default_rbac(
        self,
        name,
        namespace,
        cluster_uuid,
        api_groups,
        resources,
        verbs,
        service_account,
    ):
        """
        Create a basic RBAC for a new namespace.

        :param name: name of both Role and Role Binding
        :param namespace: K8s namespace
        :param cluster_uuid: K8s cluster uuid used to retrieve kubeconfig
        :param api_groups: Api groups to be allowed in Policy Rule
        :param resources: Resources to be allowed in Policy Rule
        :param verbs: Verbs to be allowed in Policy Rule
        :param service_account: Service Account name used to bind the Role
        :returns: None
        """
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )
        kubectl = Kubectl(config_file=paths["kube_config"])
        await kubectl.create_role(
            name=name,
            labels={},
            namespace=namespace,
            api_groups=api_groups,
            resources=resources,
            verbs=verbs,
        )
        await kubectl.create_role_binding(
            name=name,
            labels={},
            namespace=namespace,
            role_name=name,
            sa_name=service_account,
        )
