# Copyright 2022 Whitestack, LLC
# *************************************************************
#
# This file is part of OSM Monitoring module
# All Rights Reserved to Whitestack, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact: lvega@whitestack.com
##

from configman import ConfigMan
from glom import glom, assign


class OsmConfigman(ConfigMan):
    def __init__(self, config_dict=None):
        super().__init__()
        self.set_from_dict(config_dict)
        self.set_auto_env("OSMLCM")
        self.set_auto_env("OSM")

    def get(self, key, defaultValue):
        return self.to_dict()[key]

    def set_from_dict(self, config_dict):
        def func(attr_path: str, _: type) -> None:
            conf_val = glom(config_dict, attr_path, default=None)
            if conf_val is not None:
                assign(self, attr_path, conf_val)

        self._run_func_for_all_premitives(func)

    def _get_env_name(self, path: str, prefix: str = None) -> str:
        path_parts = path.split(".")
        if prefix is not None:
            path_parts.insert(0, prefix)
        return "_".join(path_parts).upper()

    def transform(self):
        pass


# Configs from lcm.cfg


class GlobalConfig(OsmConfigman):
    loglevel: str = "DEBUG"
    logfile: str = None
    nologging: bool = False


class Timeout(OsmConfigman):
    nsi_deploy: int = 2 * 3600  # default global timeout for deployment a nsi
    vca_on_error: int = (
        5 * 60
    )  # Time for charm from first time at blocked,error status to mark as failed
    ns_deploy: int = 2 * 3600  # default global timeout for deployment a ns
    ns_terminate: int = 1800  # default global timeout for un deployment a ns
    ns_heal: int = 1800  # default global timeout for un deployment a ns
    charm_delete: int = 10 * 60
    primitive: int = 30 * 60  # timeout for primitive execution
    ns_update: int = 30 * 60  # timeout for ns update
    progress_primitive: int = (
        10 * 60
    )  # timeout for some progress in a primitive execution
    migrate: int = 1800  # default global timeout for migrating vnfs
    operate: int = 1800  # default global timeout for migrating vnfs
    verticalscale: int = 1800  # default global timeout for Vertical Sclaing
    scale_on_error = (
        5 * 60
    )  # Time for charm from first time at blocked,error status to mark as failed
    scale_on_error_outer_factor = 1.05  # Factor in relation to timeout_scale_on_error related to the timeout to be applied within the asyncio.wait_for coroutine
    primitive_outer_factor = 1.05  # Factor in relation to timeout_primitive related to the timeout to be applied within the asyncio.wait_for coroutine


class RoConfig(OsmConfigman):
    host: str = None
    ng: bool = False
    port: int = None
    uri: str = None
    tenant: str = "osm"
    loglevel: str = "ERROR"
    logfile: str = None
    logger_name: str = None

    def transform(self):
        if not self.uri:
            self.uri = "http://{}:{}/".format(self.host, self.port)
        elif "/ro" in self.uri[-4:] or "/openmano" in self.uri[-10:]:
            # uri ends with '/ro', '/ro/', '/openmano', '/openmano/'
            index = self.uri[-1].rfind("/")
            self.uri = self.uri[index + 1]
        self.logger_name = "lcm.roclient"


class VcaConfig(OsmConfigman):
    host: str = None
    port: int = None
    user: str = None
    secret: str = None
    cloud: str = None
    k8s_cloud: str = None
    helmpath: str = None
    helm3path: str = None
    kubectlpath: str = None
    jujupath: str = None
    public_key: str = None
    ca_cert: str = None
    api_proxy: str = None
    apt_mirror: str = None
    eegrpcinittimeout: int = None
    eegrpctimeout: int = None
    eegrpc_tls_enforce: bool = False
    eegrpc_pod_admission_policy: str = "baseline"
    loglevel: str = "DEBUG"
    logfile: str = None
    ca_store: str = "/etc/ssl/certs/osm-ca.crt"
    client_cert_path: str = "/etc/ssl/lcm-client/tls.crt"
    client_key_path: str = "/etc/ssl/lcm-client/tls.key"
    kubectl_osm_namespace: str = "osm"
    kubectl_osm_cluster_name: str = "_system-osm-k8s"
    helm_ee_service_port: int = 50050
    helm_max_initial_retry_time: int = 600
    helm_max_retry_time: int = 30  # Max retry time for normal operations
    helm_ee_retry_delay: int = (
        10  # time between retries, retry time after a connection error is raised
    )

    def transform(self):
        if self.eegrpcinittimeout:
            self.helm_max_initial_retry_time = self.eegrpcinittimeout
        if self.eegrpctimeout:
            self.helm_max_retry_time = self.eegrpctimeout


class DatabaseConfig(OsmConfigman):
    driver: str = None
    host: str = None
    port: int = None
    uri: str = None
    name: str = None
    replicaset: str = None
    user: str = None
    password: str = None
    commonkey: str = None
    loglevel: str = "DEBUG"
    logfile: str = None
    logger_name: str = None

    def transform(self):
        self.logger_name = "lcm.db"


class StorageConfig(OsmConfigman):
    driver: str = None
    path: str = "/app/storage"
    loglevel: str = "DEBUG"
    logfile: str = None
    logger_name: str = None
    collection: str = None
    uri: str = None

    def transform(self):
        self.logger_name = "lcm.fs"


class MessageConfig(OsmConfigman):
    driver: str = None
    path: str = None
    host: str = None
    port: int = None
    loglevel: str = "DEBUG"
    logfile: str = None
    group_id: str = None
    logger_name: str = None

    def transform(self):
        self.logger_name = "lcm.msg"


class TsdbConfig(OsmConfigman):
    driver: str = None
    path: str = None
    uri: str = None
    loglevel: str = "DEBUG"
    logfile: str = None
    logger_name: str = None

    def transform(self):
        self.logger_name = "lcm.prometheus"


class MonitoringConfig(OsmConfigman):
    old_sa: bool = True


class GitopsConfig(OsmConfigman):
    git_base_url: str = None
    fleet_repo_url: str = None
    sw_catalogs_repo_url: str = None
    user: str = None
    pubkey: str = None
    mgmtcluster_kubeconfig: str = None
    workflow_debug: bool = True
    workflow_dry_run: bool = False
    loglevel: str = "DEBUG"
    logfile: str = None
    logger_name: str = None

    def transform(self):
        self.logger_name = "lcm.gitops"


# Main configuration Template


class LcmCfg(OsmConfigman):
    globalConfig: GlobalConfig = GlobalConfig()
    timeout: Timeout = Timeout()
    RO: RoConfig = RoConfig()
    VCA: VcaConfig = VcaConfig()
    database: DatabaseConfig = DatabaseConfig()
    storage: StorageConfig = StorageConfig()
    message: MessageConfig = MessageConfig()
    tsdb: TsdbConfig = TsdbConfig()
    servicekpi: MonitoringConfig = MonitoringConfig()
    gitops: GitopsConfig = GitopsConfig()

    def transform(self):
        for attribute in dir(self):
            method = getattr(self, attribute)
            if isinstance(method, OsmConfigman):
                method.transform()


class SubOperation(OsmConfigman):
    STATUS_NOT_FOUND: int = -1
    STATUS_NEW: int = -2
    STATUS_SKIP: int = -3


class LCMConfiguration(OsmConfigman):
    suboperation: SubOperation = SubOperation()
    task_name_deploy_vca = "Deploying VCA"
