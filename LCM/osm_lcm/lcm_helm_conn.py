##
# Copyright 2020 Telefonica Investigacion y Desarrollo, S.A.U.
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
##
import functools
import yaml
import asyncio
import uuid
import os
import ssl

from grpclib.client import Channel

from osm_lcm.data_utils.lcm_config import VcaConfig
from osm_lcm.frontend_pb2 import PrimitiveRequest
from osm_lcm.frontend_pb2 import SshKeyRequest
from osm_lcm.frontend_grpc import FrontendExecutorStub
from osm_lcm.lcm_utils import LcmBase, get_ee_id_parts

from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem

from osm_lcm.n2vc.n2vc_conn import N2VCConnector
from osm_lcm.n2vc.k8s_helm3_conn import K8sHelm3Connector
from osm_lcm.n2vc.exceptions import (
    N2VCBadArgumentsException,
    N2VCException,
    N2VCExecutionException,
)

from osm_lcm.lcm_utils import deep_get


def retryer(max_wait_time_var="_initial_retry_time", delay_time_var="_retry_delay"):
    def wrapper(func):
        retry_exceptions = (ConnectionRefusedError, TimeoutError)

        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            # default values for wait time and delay_time
            delay_time = 10
            max_wait_time = 300

            # obtain arguments from variable names
            self = args[0]
            if self.__dict__.get(max_wait_time_var):
                max_wait_time = self.__dict__.get(max_wait_time_var)
            if self.__dict__.get(delay_time_var):
                delay_time = self.__dict__.get(delay_time_var)

            wait_time = max_wait_time
            while wait_time > 0:
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions:
                    wait_time = wait_time - delay_time
                    await asyncio.sleep(delay_time)
                    continue
            else:
                return ConnectionRefusedError

        return wrapped

    return wrapper


def create_secure_context(
    trusted: str, client_cert_path: str, client_key_path: str
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(client_cert_path, client_key_path)
    ctx.load_verify_locations(trusted)
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
    ctx.set_alpn_protocols(["h2"])
    return ctx


class LCMHelmConn(N2VCConnector, LcmBase):
    def __init__(
        self,
        log: object = None,
        vca_config: VcaConfig = None,
        on_update_db=None,
    ):
        """
        Initialize EE helm connector.
        """

        self.db = Database().instance.db
        self.fs = Filesystem().instance.fs

        # parent class constructor
        N2VCConnector.__init__(
            self, log=log, on_update_db=on_update_db, db=self.db, fs=self.fs
        )

        self.vca_config = vca_config
        self.log.debug("Initialize helm N2VC connector")
        self.log.debug("initial vca_config: {}".format(vca_config.to_dict()))

        self._retry_delay = self.vca_config.helm_ee_retry_delay

        self._initial_retry_time = self.vca_config.helm_max_initial_retry_time
        self.log.debug("Initial retry time: {}".format(self._initial_retry_time))

        self._max_retry_time = self.vca_config.helm_max_retry_time
        self.log.debug("Retry time: {}".format(self._max_retry_time))

        # initialize helm connector for helmv3
        self._k8sclusterhelm3 = K8sHelm3Connector(
            kubectl_command=self.vca_config.kubectlpath,
            helm_command=self.vca_config.helm3path,
            fs=self.fs,
            log=self.log,
            db=self.db,
            on_update_db=None,
        )

        self._system_cluster_id = None
        self.log.info("Helm N2VC connector initialized")

    # TODO - ¿reuse_ee_id?
    async def create_execution_environment(
        self,
        namespace: str,
        db_dict: dict,
        reuse_ee_id: str = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        artifact_path: str = None,
        chart_model: str = None,
        vca_type: str = None,
        *kargs,
        **kwargs,
    ) -> tuple[str, dict]:
        """
        Creates a new helm execution environment deploying the helm-chat indicated in the
        artifact_path
        :param str namespace: This param is not used, all helm charts are deployed in the osm
        system namespace
        :param dict db_dict: where to write to database when the status changes.
            It contains a dictionary with {collection: str, filter: {},  path: str},
                e.g. {collection: "nsrs", filter: {_id: <nsd-id>, path:
                "_admin.deployed.VCA.3"}
        :param str reuse_ee_id: ee id from an older execution. TODO - right now this param is not used
        :param float progress_timeout:
        :param float total_timeout:
        :param dict config:  General variables to instantiate KDU
        :param str artifact_path: path of package content
        :param str chart_model: helm chart/reference (string), which can be either
            of these options:
            - a name of chart available via the repos known by OSM
              (e.g. stable/openldap, stable/openldap:1.2.4)
            - a path to a packaged chart (e.g. mychart.tgz)
            - a path to an unpacked chart directory or a URL (e.g. mychart)
        :param str vca_type:  Type of vca, must be type helm-v3
        :returns str, dict: id of the new execution environment including namespace.helm_id
        and credentials object set to None as all credentials should be osm kubernetes .kubeconfig
        """

        if not namespace:
            namespace = self.vca_config.kubectl_osm_namespace

        self.log.info(
            "create_execution_environment: namespace: {}, artifact_path: {}, "
            "chart_model: {}, db_dict: {}, reuse_ee_id: {}".format(
                namespace, artifact_path, db_dict, chart_model, reuse_ee_id
            )
        )

        # Validate artifact-path is provided
        if artifact_path is None or len(artifact_path) == 0:
            raise N2VCBadArgumentsException(
                message="artifact_path is mandatory", bad_args=["artifact_path"]
            )

        # Validate artifact-path exists and sync path
        from_path = os.path.split(artifact_path)[0]
        self.fs.sync(from_path)

        # remove / in charm path
        while artifact_path.find("//") >= 0:
            artifact_path = artifact_path.replace("//", "/")

        # check charm path
        if self.fs.file_exists(artifact_path):
            helm_chart_path = artifact_path
        else:
            msg = "artifact path does not exist: {}".format(artifact_path)
            raise N2VCBadArgumentsException(message=msg, bad_args=["artifact_path"])

        if artifact_path.startswith("/"):
            full_path = self.fs.path + helm_chart_path
        else:
            full_path = self.fs.path + "/" + helm_chart_path

        while full_path.find("//") >= 0:
            full_path = full_path.replace("//", "/")

        # By default, the KDU is expected to be a file
        kdu_model = full_path
        # If the chart_model includes a "/", then it is a reference:
        #    e.g. (stable/openldap; stable/openldap:1.2.4)
        if chart_model.find("/") >= 0:
            kdu_model = chart_model

        try:
            # Call helm conn install
            # Obtain system cluster id from database
            system_cluster_uuid = await self._get_system_cluster_id()
            # Add parameter osm if exist to global
            if config and config.get("osm"):
                if not config.get("global"):
                    config["global"] = {}
                config["global"]["osm"] = config.get("osm")

            self.log.debug("install helm chart: {}".format(full_path))
            helm_id = self._k8sclusterhelm3.generate_kdu_instance_name(
                db_dict=db_dict,
                kdu_model=kdu_model,
            )
            await self._k8sclusterhelm3.install(
                system_cluster_uuid,
                kdu_model=kdu_model,
                kdu_instance=helm_id,
                namespace=namespace,
                params=config,
                db_dict=db_dict,
                timeout=progress_timeout,
            )

            ee_id = "{}:{}.{}".format(vca_type, namespace, helm_id)
            return ee_id, None
        except N2VCException:
            raise
        except Exception as e:
            self.log.error("Error deploying chart ee: {}".format(e), exc_info=True)
            raise N2VCException("Error deploying chart ee: {}".format(e))

    async def upgrade_execution_environment(
        self,
        namespace: str,
        db_dict: dict,
        helm_id: str,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        artifact_path: str = None,
        vca_type: str = None,
        *kargs,
        **kwargs,
    ) -> tuple[str, dict]:
        """
        Creates a new helm execution environment deploying the helm-chat indicated in the
        attifact_path
        :param str namespace: This param is not used, all helm charts are deployed in the osm
        system namespace
        :param dict db_dict: where to write to database when the status changes.
            It contains a dictionary with {collection: str, filter: {},  path: str},
                e.g. {collection: "nsrs", filter: {_id: <nsd-id>, path:
                "_admin.deployed.VCA.3"}
        :param helm_id: unique name of the Helm release to upgrade
        :param float progress_timeout:
        :param float total_timeout:
        :param dict config:  General variables to instantiate KDU
        :param str artifact_path:  path of package content
        :param str vca_type:  Type of vca, must be type helm-v3
        :returns str, dict: id of the new execution environment including namespace.helm_id
        and credentials object set to None as all credentials should be osm kubernetes .kubeconfig
        """

        self.log.info(
            "upgrade_execution_environment: namespace: {}, artifact_path: {}, db_dict: {}, "
        )

        # Validate helm_id is provided
        if helm_id is None or len(helm_id) == 0:
            raise N2VCBadArgumentsException(
                message="helm_id is mandatory", bad_args=["helm_id"]
            )

        # Validate artifact-path is provided
        if artifact_path is None or len(artifact_path) == 0:
            raise N2VCBadArgumentsException(
                message="artifact_path is mandatory", bad_args=["artifact_path"]
            )

        # Validate artifact-path exists and sync path
        from_path = os.path.split(artifact_path)[0]
        self.fs.sync(from_path)

        # remove / in charm path
        while artifact_path.find("//") >= 0:
            artifact_path = artifact_path.replace("//", "/")

        # check charm path
        if self.fs.file_exists(artifact_path):
            helm_chart_path = artifact_path
        else:
            msg = "artifact path does not exist: {}".format(artifact_path)
            raise N2VCBadArgumentsException(message=msg, bad_args=["artifact_path"])

        if artifact_path.startswith("/"):
            full_path = self.fs.path + helm_chart_path
        else:
            full_path = self.fs.path + "/" + helm_chart_path

        while full_path.find("//") >= 0:
            full_path = full_path.replace("//", "/")

        try:
            # Call helm conn upgrade
            # Obtain system cluster id from database
            system_cluster_uuid = await self._get_system_cluster_id()
            # Add parameter osm if exist to global
            if config and config.get("osm"):
                if not config.get("global"):
                    config["global"] = {}
                config["global"]["osm"] = config.get("osm")

            self.log.debug("Ugrade helm chart: {}".format(full_path))
            await self._k8sclusterhelm3.upgrade(
                system_cluster_uuid,
                kdu_model=full_path,
                kdu_instance=helm_id,
                namespace=namespace,
                params=config,
                db_dict=db_dict,
                timeout=progress_timeout,
                force=True,
            )

        except N2VCException:
            raise
        except Exception as e:
            self.log.error("Error upgrading chart ee: {}".format(e), exc_info=True)
            raise N2VCException("Error upgrading chart ee: {}".format(e))

    async def create_tls_certificate(
        self,
        nsr_id: str,
        secret_name: str,
        usage: str,
        dns_prefix: str,
        namespace: str = None,
    ):
        # Obtain system cluster id from database
        system_cluster_uuid = await self._get_system_cluster_id()
        # use helm-v3 as certificates don't depend on helm version
        await self._k8sclusterhelm3.create_certificate(
            cluster_uuid=system_cluster_uuid,
            namespace=namespace or self.vca_config.kubectl_osm_namespace,
            dns_prefix=dns_prefix,
            name=nsr_id,
            secret_name=secret_name,
            usage=usage,
        )

    async def delete_tls_certificate(
        self,
        certificate_name: str = None,
        namespace: str = None,
    ):
        # Obtain system cluster id from database
        system_cluster_uuid = await self._get_system_cluster_id()
        await self._k8sclusterhelm3.delete_certificate(
            cluster_uuid=system_cluster_uuid,
            namespace=namespace or self.vca_config.kubectl_osm_namespace,
            certificate_name=certificate_name,
        )

    async def setup_ns_namespace(
        self,
        name: str,
    ):
        # Obtain system cluster id from database
        system_cluster_uuid = await self._get_system_cluster_id()
        await self._k8sclusterhelm3.create_namespace(
            namespace=name,
            cluster_uuid=system_cluster_uuid,
            labels={
                "pod-security.kubernetes.io/enforce": self.vca_config.eegrpc_pod_admission_policy
            },
        )
        await self._k8sclusterhelm3.setup_default_rbac(
            name="ee-role",
            namespace=name,
            api_groups=[""],
            resources=["secrets"],
            verbs=["get"],
            service_account="default",
            cluster_uuid=system_cluster_uuid,
        )
        await self._k8sclusterhelm3.copy_secret_data(
            src_secret="osm-ca",
            dst_secret="osm-ca",
            src_namespace=self.vca_config.kubectl_osm_namespace,
            dst_namespace=name,
            cluster_uuid=system_cluster_uuid,
            data_key="ca.crt",
        )

    async def register_execution_environment(
        self,
        namespace: str,
        credentials: dict,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        *kargs,
        **kwargs,
    ) -> str:
        # nothing to do
        pass

    async def install_configuration_sw(self, *args, **kwargs):
        # nothing to do
        pass

    async def add_relation(self, *args, **kwargs):
        # nothing to do
        pass

    async def remove_relation(self):
        # nothing to to
        pass

    async def get_status(self, *args, **kwargs):
        # not used for this connector
        pass

    async def get_ee_ssh_public__key(
        self,
        ee_id: str,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        **kwargs,
    ) -> str:
        """
        Obtains ssh-public key from ee executing GetSShKey method from the ee.

        :param str ee_id: the id of the execution environment returned by
            create_execution_environment or register_execution_environment
        :param dict db_dict:
        :param float progress_timeout:
        :param float total_timeout:
        :returns: public key of the execution environment
        """

        self.log.info(
            "get_ee_ssh_public_key: ee_id: {}, db_dict: {}".format(ee_id, db_dict)
        )

        # check arguments
        if ee_id is None or len(ee_id) == 0:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )

        try:
            # Obtain ip_addr for the ee service, it is resolved by dns from the ee name by kubernetes
            version, namespace, helm_id = get_ee_id_parts(ee_id)
            ip_addr = "{}.{}.svc".format(helm_id, namespace)
            # Obtain ssh_key from the ee, this method will implement retries to allow the ee
            # install libraries and start successfully
            ssh_key = await self._get_ssh_key(ip_addr)
            return ssh_key
        except Exception as e:
            self.log.error("Error obtaining ee ssh_key: {}".format(e), exc_info=True)
            raise N2VCException("Error obtaining ee ssh_ke: {}".format(e))

    async def upgrade_charm(
        self,
        ee_id: str = None,
        path: str = None,
        charm_id: str = None,
        charm_type: str = None,
        timeout: float = None,
    ) -> str:
        """This method upgrade charms in VNFs

        This method does not support KDU's deployed with Helm.

        Args:
            ee_id:  Execution environment id
            path:   Local path to the charm
            charm_id:   charm-id
            charm_type: Charm type can be lxc-proxy-charm, native-charm or k8s-proxy-charm
            timeout: (Float)    Timeout for the ns update operation

        Returns:
            the output of the update operation if status equals to "completed"

        """
        raise N2VCException("KDUs deployed with Helm do not support charm upgrade")

    async def exec_primitive(
        self,
        ee_id: str,
        primitive_name: str,
        params_dict: dict,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        **kwargs,
    ) -> str:
        """
        Execute a primitive in the execution environment

        :param str ee_id: the one returned by create_execution_environment or
            register_execution_environment with the format namespace.helm_id
        :param str primitive_name: must be one defined in the software. There is one
            called 'config', where, for the proxy case, the 'credentials' of VM are
            provided
        :param dict params_dict: parameters of the action
        :param dict db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nslcmops", filter:
                                {_id: <nslcmop_id>, path: "_admin.VCA"}
                        It will be used to store information about intermediate notifications
        :param float progress_timeout:
        :param float total_timeout:
        :returns str: primitive result, if ok. It raises exceptions in case of fail
        """

        self.log.info(
            "exec primitive for ee_id : {}, primitive_name: {}, params_dict: {}, db_dict: {}".format(
                ee_id, primitive_name, params_dict, db_dict
            )
        )

        # check arguments
        if ee_id is None or len(ee_id) == 0:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )
        if primitive_name is None or len(primitive_name) == 0:
            raise N2VCBadArgumentsException(
                message="action_name is mandatory", bad_args=["action_name"]
            )
        if params_dict is None:
            params_dict = dict()

        try:
            version, namespace, helm_id = get_ee_id_parts(ee_id)
            ip_addr = "{}.{}.svc".format(helm_id, namespace)
        except Exception as e:
            self.log.error("Error getting ee ip ee: {}".format(e))
            raise N2VCException("Error getting ee ip ee: {}".format(e))

        if primitive_name == "config":
            try:
                # Execute config primitive, higher timeout to check the case ee is starting
                status, detailed_message = await self._execute_config_primitive(
                    ip_addr, params_dict, db_dict=db_dict
                )
                self.log.debug(
                    "Executed config primitive ee_id_ {}, status: {}, message: {}".format(
                        ee_id, status, detailed_message
                    )
                )
                if status != "OK":
                    self.log.error(
                        "Error configuring helm ee, status: {}, message: {}".format(
                            status, detailed_message
                        )
                    )
                    raise N2VCExecutionException(
                        message="Error configuring helm ee_id: {}, status: {}, message: {}: ".format(
                            ee_id, status, detailed_message
                        ),
                        primitive_name=primitive_name,
                    )
            except Exception as e:
                self.log.error("Error configuring helm ee: {}".format(e))
                raise N2VCExecutionException(
                    message="Error configuring helm ee_id: {}, {}".format(ee_id, e),
                    primitive_name=primitive_name,
                )
            return "CONFIG OK"
        else:
            try:
                # Execute primitive
                status, detailed_message = await self._execute_primitive(
                    ip_addr, primitive_name, params_dict, db_dict=db_dict
                )
                self.log.debug(
                    "Executed primitive {} ee_id_ {}, status: {}, message: {}".format(
                        primitive_name, ee_id, status, detailed_message
                    )
                )
                if status != "OK" and status != "PROCESSING":
                    self.log.error(
                        "Execute primitive {} returned not ok status: {}, message: {}".format(
                            primitive_name, status, detailed_message
                        )
                    )
                    raise N2VCExecutionException(
                        message="Execute primitive {} returned not ok status: {}, message: {}".format(
                            primitive_name, status, detailed_message
                        ),
                        primitive_name=primitive_name,
                    )
            except Exception as e:
                self.log.error(
                    "Error executing primitive {}: {}".format(primitive_name, e)
                )
                raise N2VCExecutionException(
                    message="Error executing primitive {} into ee={} : {}".format(
                        primitive_name, ee_id, e
                    ),
                    primitive_name=primitive_name,
                )
            return detailed_message

    async def deregister_execution_environments(self):
        # nothing to be done
        pass

    async def delete_execution_environment(
        self,
        ee_id: str,
        db_dict: dict = None,
        total_timeout: float = None,
        **kwargs,
    ):
        """
        Delete an execution environment
        :param str ee_id: id of the execution environment to delete, included namespace.helm_id
        :param dict db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nsrs", filter:
                                {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param float total_timeout:
        """

        self.log.info("ee_id: {}".format(ee_id))

        # check arguments
        if ee_id is None:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )

        try:
            # Obtain cluster_uuid
            system_cluster_uuid = await self._get_system_cluster_id()

            # Get helm_id
            version, namespace, helm_id = get_ee_id_parts(ee_id)

            await self._k8sclusterhelm3.uninstall(system_cluster_uuid, helm_id)
            self.log.info("ee_id: {} deleted".format(ee_id))
        except N2VCException:
            raise
        except Exception as e:
            self.log.error(
                "Error deleting ee id: {}: {}".format(ee_id, e), exc_info=True
            )
            raise N2VCException("Error deleting ee id {}: {}".format(ee_id, e))

    async def delete_namespace(
        self, namespace: str, db_dict: dict = None, total_timeout: float = None
    ):
        # Obtain system cluster id from database
        system_cluster_uuid = await self._get_system_cluster_id()
        await self._k8sclusterhelm3.delete_namespace(
            namespace=namespace,
            cluster_uuid=system_cluster_uuid,
        )

    async def install_k8s_proxy_charm(
        self,
        charm_name: str,
        namespace: str,
        artifact_path: str,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        *kargs,
        **kwargs,
    ) -> str:
        pass

    @retryer(max_wait_time_var="_initial_retry_time", delay_time_var="_retry_delay")
    async def _get_ssh_key(self, ip_addr):
        return await self._execute_primitive_internal(
            ip_addr,
            "_get_ssh_key",
            None,
        )

    @retryer(max_wait_time_var="_initial_retry_time", delay_time_var="_retry_delay")
    async def _execute_config_primitive(self, ip_addr, params, db_dict=None):
        return await self._execute_primitive_internal(
            ip_addr, "config", params, db_dict=db_dict
        )

    @retryer(max_wait_time_var="_max_retry_time", delay_time_var="_retry_delay")
    async def _execute_primitive(self, ip_addr, primitive_name, params, db_dict=None):
        return await self._execute_primitive_internal(
            ip_addr, primitive_name, params, db_dict=db_dict
        )

    async def _execute_primitive_internal(
        self, ip_addr, primitive_name, params, db_dict=None
    ):
        async def execute():
            stub = FrontendExecutorStub(channel)
            if primitive_name == "_get_ssh_key":
                self.log.debug("get ssh key, ip_addr: {}".format(ip_addr))
                reply = await stub.GetSshKey(SshKeyRequest())
                return reply.message
            # For any other primitives
            async with stub.RunPrimitive.open() as stream:
                primitive_id = str(uuid.uuid1())
                result = None
                self.log.debug(
                    "Execute primitive internal: id:{}, name:{}, params: {}".format(
                        primitive_id, primitive_name, params
                    )
                )
                await stream.send_message(
                    PrimitiveRequest(
                        id=primitive_id, name=primitive_name, params=yaml.dump(params)
                    ),
                    end=True,
                )
                async for reply in stream:
                    self.log.debug("Received reply: {}".format(reply))
                    result = reply
                    # If db_dict provided write notifs in database
                    if db_dict:
                        self._write_op_detailed_status(
                            db_dict, reply.status, reply.detailed_message
                        )
                if result:
                    return reply.status, reply.detailed_message
                else:
                    return "ERROR", "No result received"

        ssl_context = create_secure_context(
            self.vca_config.ca_store,
            self.vca_config.client_cert_path,
            self.vca_config.client_key_path,
        )
        channel = Channel(
            ip_addr, self.vca_config.helm_ee_service_port, ssl=ssl_context
        )
        try:
            return await execute()
        except ssl.SSLError as ssl_error:  # fallback to insecure gRPC
            if (
                ssl_error.reason == "WRONG_VERSION_NUMBER"
                and not self.vca_config.eegrpc_tls_enforce
            ):
                self.log.debug(
                    "Execution environment doesn't support TLS, falling back to unsecure gRPC"
                )
                channel = Channel(ip_addr, self.vca_config.helm_ee_service_port)
                return await execute()
            elif ssl_error.reason == "WRONG_VERSION_NUMBER":
                raise N2VCException(
                    "Execution environment doesn't support TLS, primitives cannot be executed"
                )
            else:
                raise
        finally:
            channel.close()

    def _write_op_detailed_status(self, db_dict, status, detailed_message):
        # write ee_id to database: _admin.deployed.VCA.x
        try:
            the_table = db_dict["collection"]
            the_filter = db_dict["filter"]
            update_dict = {"detailed-status": "{}: {}".format(status, detailed_message)}
            # self.log.debug('Writing ee_id to database: {}'.format(the_path))
            self.db.set_one(
                table=the_table,
                q_filter=the_filter,
                update_dict=update_dict,
                fail_on_empty=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.log.error("Error writing detailedStatus to database: {}".format(e))

    async def _get_system_cluster_id(self):
        if not self._system_cluster_id:
            db_k8cluster = self.db.get_one(
                "k8sclusters", {"name": self.vca_config.kubectl_osm_cluster_name}
            )
            k8s_hc_id = deep_get(db_k8cluster, ("_admin", "helm-chart-v3", "id"))
            if not k8s_hc_id:
                try:
                    # backward compatibility for existing clusters that have not been initialized for helm v3
                    cluster_id = db_k8cluster.get("_id")
                    k8s_credentials = yaml.safe_dump(db_k8cluster.get("credentials"))
                    k8s_hc_id, uninstall_sw = await self._k8sclusterhelm3.init_env(
                        k8s_credentials, reuse_cluster_uuid=cluster_id
                    )
                    db_k8scluster_update = {
                        "_admin.helm-chart-v3.error_msg": None,
                        "_admin.helm-chart-v3.id": k8s_hc_id,
                        "_admin.helm-chart-v3}.created": uninstall_sw,
                        "_admin.helm-chart-v3.operationalState": "ENABLED",
                    }
                    self.update_db_2("k8sclusters", cluster_id, db_k8scluster_update)
                except Exception as e:
                    self.log.error(
                        "error initializing helm-v3 cluster: {}".format(str(e))
                    )
                    raise N2VCException(
                        "K8s system cluster '{}' has not been initialized for helm-chart-v3".format(
                            cluster_id
                        )
                    )
            self._system_cluster_id = k8s_hc_id
        return self._system_cluster_id
