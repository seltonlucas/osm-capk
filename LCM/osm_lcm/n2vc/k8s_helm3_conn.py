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
from typing import Union
from shlex import quote
import os
import yaml

from osm_lcm.n2vc.k8s_helm_base_conn import K8sHelmBaseConnector
from osm_lcm.n2vc.exceptions import K8sException


class K8sHelm3Connector(K8sHelmBaseConnector):

    """
    ####################################################################################
    ################################### P U B L I C ####################################
    ####################################################################################
    """

    def __init__(
        self,
        fs: object,
        db: object,
        kubectl_command: str = "/usr/bin/kubectl",
        helm_command: str = "/usr/bin/helm3",
        log: object = None,
        on_update_db=None,
    ):
        """
        Initializes helm connector for helm v3

        :param fs: file system for kubernetes and helm configuration
        :param db: database object to write current operation status
        :param kubectl_command: path to kubectl executable
        :param helm_command: path to helm executable
        :param log: logger
        :param on_update_db: callback called when k8s connector updates database
        """

        # parent class
        K8sHelmBaseConnector.__init__(
            self,
            db=db,
            log=log,
            fs=fs,
            kubectl_command=kubectl_command,
            helm_command=helm_command,
            on_update_db=on_update_db,
        )

        self.log.info("K8S Helm3 connector initialized")

    async def install(
        self,
        cluster_uuid: str,
        kdu_model: str,
        kdu_instance: str,
        atomic: bool = True,
        timeout: float = 300,
        params: dict = None,
        db_dict: dict = None,
        kdu_name: str = None,
        namespace: str = None,
        **kwargs,
    ):
        """Install a helm chart

        :param cluster_uuid str: The UUID of the cluster to install to
        :param kdu_model str: chart/reference (string), which can be either
            of these options:
            - a name of chart available via the repos known by OSM
              (e.g. stable/openldap, stable/openldap:1.2.4)
            - a path to a packaged chart (e.g. mychart.tgz)
            - a path to an unpacked chart directory or a URL (e.g. mychart)
        :param kdu_instance: Kdu instance name
        :param atomic bool: If set, waits until the model is active and resets
                            the cluster on failure.
        :param timeout int: The time, in seconds, to wait for the install
                            to finish
        :param params dict: Key-value pairs of instantiation parameters
        :param kdu_name: Name of the KDU instance to be installed
        :param namespace: K8s namespace to use for the KDU instance

        :param kwargs: Additional parameters (None yet)

        :return: True if successful
        """

        self.log.debug("installing {} in cluster {}".format(kdu_model, cluster_uuid))

        labels_dict = None
        if db_dict:
            labels_dict = await self._labels_dict(db_dict, kdu_instance)

        # sync local dir
        self.fs.sync(from_path=cluster_uuid)

        # init env, paths
        paths, env = self._init_paths_env(
            cluster_name=cluster_uuid, create_if_not_exist=True
        )

        # for helm3 if namespace does not exist must create it
        if namespace and namespace != "kube-system":
            if not await self._namespace_exists(cluster_uuid, namespace):
                try:
                    # TODO: refactor to use kubernetes API client
                    await self._create_namespace(cluster_uuid, namespace)
                except Exception as e:
                    if not await self._namespace_exists(cluster_uuid, namespace):
                        err_msg = (
                            "namespace {} does not exist in cluster_id {} "
                            "error message: ".format(namespace, e)
                        )
                        self.log.error(err_msg)
                        raise K8sException(err_msg)

        await self._install_impl(
            cluster_uuid,
            kdu_model,
            paths,
            env,
            kdu_instance,
            atomic=atomic,
            timeout=timeout,
            params=params,
            db_dict=db_dict,
            labels=labels_dict,
            kdu_name=kdu_name,
            namespace=namespace,
        )

        # sync fs
        self.fs.reverse_sync(from_path=cluster_uuid)

        self.log.debug("Returning kdu_instance {}".format(kdu_instance))
        return True

    async def migrate(self, nsr_id, target):
        db_nsr = self.db.get_one("nsrs", {"_id": nsr_id})

        # check if it has k8s deployed kdus
        if len(db_nsr["_admin"]["deployed"]["K8s"]) < 1:
            err_msg = "INFO: No deployed KDUs"
            self.log.error(err_msg)
            raise K8sException(err_msg)

        kdu_id = target["vdu"]["vduId"]
        for index, kdu in enumerate(db_nsr["_admin"]["deployed"]["K8s"]):
            if kdu["kdu-instance"] == kdu_id:
                namespace = kdu["namespace"]
                cluster_uuid = kdu["k8scluster-uuid"]
                kdu_model = kdu["kdu-model"]
                db_dict = {
                    "collection": "nsrs",
                    "filter": {"_id": nsr_id},
                    "path": "_admin.deployed.K8s.{}".format(index),
                }

                await self.upgrade(
                    cluster_uuid,
                    kdu_instance=kdu_id,
                    kdu_model=kdu_model,
                    namespace=namespace,
                    targetHostK8sLabels=target["targetHostK8sLabels"],
                    atomic=True,
                    db_dict=db_dict,
                    force=True,
                )

                return True

        self.log.debug("ERROR: Unable to retrieve kdu from the database")

    async def inspect_kdu(self, kdu_model: str, repo_url: str = None) -> str:
        self.log.debug(
            "inspect kdu_model {} from (optional) repo: {}".format(kdu_model, repo_url)
        )

        return await self._exec_inspect_command(
            inspect_command="all", kdu_model=kdu_model, repo_url=repo_url
        )

    """
    ####################################################################################
    ################################### P R I V A T E ##################################
    ####################################################################################
    """

    def _init_paths_env(self, cluster_name: str, create_if_not_exist: bool = True):
        """
        Creates and returns base cluster and kube dirs and returns them.
        Also created helm3 dirs according to new directory specification, paths are
        returned and also environment variables that must be provided to execute commands

        Helm 3 directory specification uses XDG categories for variable support:
        - Cache: $XDG_CACHE_HOME, for example, ${HOME}/.cache/helm/
        - Configuration: $XDG_CONFIG_HOME, for example, ${HOME}/.config/helm/
        - Data: $XDG_DATA_HOME, for example ${HOME}/.local/share/helm

        The variables assigned for this paths are:
        (In the documentation the variables names are $HELM_PATH_CACHE, $HELM_PATH_CONFIG,
        $HELM_PATH_DATA but looking and helm env the variable names are different)
        - Cache: $HELM_CACHE_HOME
        - Config: $HELM_CONFIG_HOME
        - Data: $HELM_DATA_HOME
        - helm kubeconfig: $KUBECONFIG

        :param cluster_name:  cluster_name
        :return: Dictionary with config_paths and dictionary with helm environment variables
        """

        base = self.fs.path
        if base.endswith("/") or base.endswith("\\"):
            base = base[:-1]

        # base dir for cluster
        cluster_dir = base + "/" + cluster_name

        # kube dir
        kube_dir = cluster_dir + "/" + ".kube"
        if create_if_not_exist and not os.path.exists(kube_dir):
            self.log.debug("Creating dir {}".format(kube_dir))
            os.makedirs(kube_dir)

        helm_path_cache = cluster_dir + "/.cache/helm"
        if create_if_not_exist and not os.path.exists(helm_path_cache):
            self.log.debug("Creating dir {}".format(helm_path_cache))
            os.makedirs(helm_path_cache)

        helm_path_config = cluster_dir + "/.config/helm"
        if create_if_not_exist and not os.path.exists(helm_path_config):
            self.log.debug("Creating dir {}".format(helm_path_config))
            os.makedirs(helm_path_config)

        helm_path_data = cluster_dir + "/.local/share/helm"
        if create_if_not_exist and not os.path.exists(helm_path_data):
            self.log.debug("Creating dir {}".format(helm_path_data))
            os.makedirs(helm_path_data)

        config_filename = kube_dir + "/config"

        # 2 - Prepare dictionary with paths
        paths = {
            "kube_dir": kube_dir,
            "kube_config": config_filename,
            "cluster_dir": cluster_dir,
        }

        # 3 - Prepare environment variables
        env = {
            "HELM_CACHE_HOME": helm_path_cache,
            "HELM_CONFIG_HOME": helm_path_config,
            "HELM_DATA_HOME": helm_path_data,
            "KUBECONFIG": config_filename,
        }

        for file_name, file in paths.items():
            if "dir" in file_name and not os.path.exists(file):
                err_msg = "{} dir does not exist".format(file)
                self.log.error(err_msg)
                raise K8sException(err_msg)

        return paths, env

    async def _namespace_exists(self, cluster_id, namespace) -> bool:
        self.log.debug(
            "checking if namespace {} exists cluster_id {}".format(
                namespace, cluster_id
            )
        )
        namespaces = await self._get_namespaces(cluster_id)
        return namespace in namespaces if namespaces else False

    async def _get_namespaces(self, cluster_id: str):
        self.log.debug("get namespaces cluster_id {}".format(cluster_id))

        # init config, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        command = "{} --kubeconfig={} get namespaces -o=yaml".format(
            self.kubectl_command, quote(paths["kube_config"])
        )
        output, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        data = yaml.load(output, Loader=yaml.SafeLoader)
        namespaces = [item["metadata"]["name"] for item in data["items"]]
        self.log.debug(f"namespaces {namespaces}")

        return namespaces

    async def _create_namespace(self, cluster_id: str, namespace: str):
        self.log.debug(f"create namespace: {cluster_id} for cluster_id: {namespace}")

        # init config, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        command = "{} --kubeconfig={} create namespace {}".format(
            self.kubectl_command, quote(paths["kube_config"]), quote(namespace)
        )
        _, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )
        self.log.debug(f"namespace {namespace} created")

        return _rc

    async def _get_services(
        self, cluster_id: str, kdu_instance: str, namespace: str, kubeconfig: str
    ):
        # init config, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        command = "env KUBECONFIG={} {} get manifest {} --namespace={}".format(
            kubeconfig, self._helm_command, quote(kdu_instance), quote(namespace)
        )
        output, _rc = await self._local_async_exec(
            command, env=env, raise_exception_on_error=True
        )
        services = self._parse_services(output)

        return services

    async def _cluster_init(self, cluster_id, namespace, paths, env):
        """
        Implements the helm version dependent cluster initialization:
        For helm3 it creates the namespace if it is not created
        """
        if namespace != "kube-system":
            namespaces = await self._get_namespaces(cluster_id)
            if namespace not in namespaces:
                # TODO: refactor to use kubernetes API client
                await self._create_namespace(cluster_id, namespace)

        repo_list = await self.repo_list(cluster_id)
        stable_repo = [repo for repo in repo_list if repo["name"] == "stable"]
        if not stable_repo and self._stable_repo_url:
            await self.repo_add(cluster_id, "stable", self._stable_repo_url)

        # Returns False as no software needs to be uninstalled
        return False

    async def _uninstall_sw(self, cluster_id: str, namespace: str):
        # nothing to do to uninstall sw
        pass

    async def _instances_list(self, cluster_id: str):
        # init paths, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )

        command = "{} list --all-namespaces  --output yaml".format(self._helm_command)
        output, _rc = await self._local_async_exec(
            command=command, raise_exception_on_error=True, env=env
        )

        if output and len(output) > 0:
            self.log.debug("instances list output: {}".format(output))
            return yaml.load(output, Loader=yaml.SafeLoader)
        else:
            return []

    def _get_inspect_command(
        self, show_command: str, kdu_model: str, repo_str: str, version: str
    ):
        """Generates the command to obtain the information about an Helm Chart package
            (´helm show ...´ command)

        Args:
            show_command: the second part of the command (`helm show <show_command>`)
            kdu_model: The name or path of a Helm Chart
            repo_str: Helm Chart repository url
            version: constraint with specific version of the Chart to use

        Returns:
            str: the generated Helm Chart command
        """

        inspect_command = "{} show {} {}{} {}".format(
            self._helm_command, show_command, quote(kdu_model), repo_str, version
        )
        return inspect_command

    def _get_get_command(
        self, get_command: str, kdu_instance: str, namespace: str, kubeconfig: str
    ):
        get_command = (
            "env KUBECONFIG={} {} get {} {} --namespace={} --output yaml".format(
                kubeconfig,
                self._helm_command,
                get_command,
                quote(kdu_instance),
                quote(namespace),
            )
        )
        return get_command

    async def _status_kdu(
        self,
        cluster_id: str,
        kdu_instance: str,
        namespace: str = None,
        yaml_format: bool = False,
        show_error_log: bool = False,
    ) -> Union[str, dict]:
        self.log.debug(
            "status of kdu_instance: {}, namespace: {} ".format(kdu_instance, namespace)
        )

        if not namespace:
            namespace = "kube-system"

        # init config, env
        paths, env = self._init_paths_env(
            cluster_name=cluster_id, create_if_not_exist=True
        )
        command = "env KUBECONFIG={} {} status {} --namespace={} --output yaml".format(
            paths["kube_config"],
            self._helm_command,
            quote(kdu_instance),
            quote(namespace),
        )

        output, rc = await self._local_async_exec(
            command=command,
            raise_exception_on_error=True,
            show_error_log=show_error_log,
            env=env,
        )

        if yaml_format:
            return str(output)

        if rc != 0:
            return None

        data = yaml.load(output, Loader=yaml.SafeLoader)

        # remove field 'notes' and manifest
        try:
            del data.get("info")["notes"]
        except KeyError:
            pass

        # parse the manifest to a list of dictionaries
        if "manifest" in data:
            manifest_str = data.get("manifest")
            manifest_docs = yaml.load_all(manifest_str, Loader=yaml.SafeLoader)

            data["manifest"] = []
            for doc in manifest_docs:
                data["manifest"].append(doc)

        return data

    def _get_install_command(
        self,
        kdu_model: str,
        kdu_instance: str,
        namespace: str,
        labels: dict,
        params_str: str,
        version: str,
        atomic: bool,
        timeout: float,
        kubeconfig: str,
    ) -> str:
        timeout_str = ""
        if timeout:
            timeout_str = "--timeout {}s".format(timeout)

        # atomic
        atomic_str = ""
        if atomic:
            atomic_str = "--atomic"
        # namespace
        namespace_str = ""
        if namespace:
            namespace_str = "--namespace {}".format(quote(namespace))

        # version
        version_str = ""
        if version:
            version_str = "--version {}".format(version)

        # labels
        post_renderer_args = []
        post_renderer_str = post_renderer_args_str = ""
        if labels and self.podLabels_post_renderer_path:
            post_renderer_args.append(
                "{}={}".format(
                    self.podLabels_post_renderer_path,
                    " ".join(
                        ["{}:{}".format(key, value) for key, value in labels.items()]
                    ),
                )
            )

        if len(post_renderer_args) > 0 and self.main_post_renderer_path:
            post_renderer_str = "--post-renderer {}".format(
                self.main_post_renderer_path,
            )
            post_renderer_args_str += (
                "--post-renderer-args '" + ",".join(post_renderer_args) + "'"
            )

        command = (
            "env KUBECONFIG={kubeconfig} {helm} install {name} {atomic} --output yaml  "
            "{params} {timeout} {ns} {post_renderer} {post_renderer_args} {model} {ver}".format(
                kubeconfig=kubeconfig,
                helm=self._helm_command,
                name=quote(kdu_instance),
                atomic=atomic_str,
                params=params_str,
                timeout=timeout_str,
                ns=namespace_str,
                post_renderer=post_renderer_str,
                post_renderer_args=post_renderer_args_str,
                model=quote(kdu_model),
                ver=version_str,
            )
        )
        return command

    def _get_upgrade_scale_command(
        self,
        kdu_model: str,
        kdu_instance: str,
        namespace: str,
        scale: int,
        labels: dict,
        version: str,
        atomic: bool,
        replica_str: str,
        timeout: float,
        resource_name: str,
        kubeconfig: str,
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

        # scale
        if resource_name:
            scale_dict = {"{}.{}".format(resource_name, replica_str): scale}
        else:
            scale_dict = {replica_str: scale}

        scale_str = self._params_to_set_option(scale_dict)

        return self._get_upgrade_command(
            kdu_model=kdu_model,
            kdu_instance=kdu_instance,
            namespace=namespace,
            params_str=scale_str,
            labels=labels,
            version=version,
            atomic=atomic,
            timeout=timeout,
            kubeconfig=kubeconfig,
        )

    def _get_upgrade_command(
        self,
        kdu_model: str,
        kdu_instance: str,
        namespace: str,
        params_str: str,
        labels: dict,
        version: str,
        atomic: bool,
        timeout: float,
        kubeconfig: str,
        targetHostK8sLabels: dict = None,
        reset_values: bool = False,
        reuse_values: bool = True,
        reset_then_reuse_values: bool = False,
        force: bool = False,
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

        timeout_str = ""
        if timeout:
            timeout_str = "--timeout {}s".format(timeout)

        # atomic
        atomic_str = ""
        if atomic:
            atomic_str = "--atomic"

        # force
        force_str = ""
        if force:
            force_str = "--force "

        # version
        version_str = ""
        if version:
            version_str = "--version {}".format(quote(version))

        # namespace
        namespace_str = ""
        if namespace:
            namespace_str = "--namespace {}".format(quote(namespace))

        # reset, reuse or reset_then_reuse values
        on_values_str = "--reuse-values"
        if reset_values:
            on_values_str = "--reset-values"
        elif reuse_values:
            on_values_str = "--reuse-values"
        elif reset_then_reuse_values:
            on_values_str = "--reset-then-reuse-values"

        # labels
        post_renderer_args = []
        post_renderer_str = post_renderer_args_str = ""
        if labels and self.podLabels_post_renderer_path:
            post_renderer_args.append(
                "{}={}".format(
                    self.podLabels_post_renderer_path,
                    " ".join(
                        ["{}:{}".format(key, value) for key, value in labels.items()]
                    ),
                )
            )

        # migration
        if targetHostK8sLabels and self.nodeSelector_post_renderer_path:
            post_renderer_args.append(
                "{}={}".format(
                    self.nodeSelector_post_renderer_path,
                    " ".join(
                        [
                            "{}:{}".format(key, value)
                            for key, value in targetHostK8sLabels.items()
                        ]
                    ),
                )
            )

        if len(post_renderer_args) > 0 and self.main_post_renderer_path:
            post_renderer_str = "--post-renderer {}".format(
                self.main_post_renderer_path,
            )
            post_renderer_args_str += (
                "--post-renderer-args '" + ",".join(post_renderer_args) + "'"
            )

        command = (
            "env KUBECONFIG={kubeconfig} {helm} upgrade {name} {model} {namespace} {atomic} {force}"
            "--output yaml {params} {timeout} {post_renderer} {post_renderer_args} {on_values} {ver}"
        ).format(
            kubeconfig=kubeconfig,
            helm=self._helm_command,
            name=quote(kdu_instance),
            namespace=namespace_str,
            atomic=atomic_str,
            force=force_str,
            params=params_str,
            timeout=timeout_str,
            post_renderer=post_renderer_str,
            post_renderer_args=post_renderer_args_str,
            model=quote(kdu_model),
            on_values=on_values_str,
            ver=version_str,
        )
        return command

    def _get_rollback_command(
        self, kdu_instance: str, namespace: str, revision: float, kubeconfig: str
    ) -> str:
        return "env KUBECONFIG={} {} rollback {} {} --namespace={} --wait".format(
            kubeconfig,
            self._helm_command,
            quote(kdu_instance),
            revision,
            quote(namespace),
        )

    def _get_uninstall_command(
        self, kdu_instance: str, namespace: str, kubeconfig: str
    ) -> str:
        return "env KUBECONFIG={} {} uninstall {} --namespace={}".format(
            kubeconfig, self._helm_command, quote(kdu_instance), quote(namespace)
        )

    def _get_helm_chart_repos_ids(self, cluster_uuid) -> list:
        repo_ids = []
        cluster_filter = {"_admin.helm-chart-v3.id": cluster_uuid}
        cluster = self.db.get_one("k8sclusters", cluster_filter)
        if cluster:
            repo_ids = cluster.get("_admin").get("helm_chart_repos") or []
            return repo_ids
        else:
            raise K8sException(
                "k8cluster with helm-id : {} not found".format(cluster_uuid)
            )
