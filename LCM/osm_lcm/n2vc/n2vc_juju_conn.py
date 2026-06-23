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

import asyncio
import logging

from osm_lcm.n2vc.config import EnvironConfig
from osm_lcm.n2vc.definitions import RelationEndpoint
from osm_lcm.n2vc.exceptions import (
    N2VCBadArgumentsException,
    N2VCException,
    N2VCConnectionException,
    N2VCExecutionException,
    N2VCApplicationExists,
    JujuApplicationExists,
    # N2VCNotFound,
    MethodNotImplemented,
)
from osm_lcm.n2vc.n2vc_conn import N2VCConnector
from osm_lcm.n2vc.n2vc_conn import obj_to_dict, obj_to_yaml
from osm_lcm.n2vc.libjuju import Libjuju, retry_callback
from osm_lcm.n2vc.store import MotorStore
from osm_lcm.n2vc.utils import get_ee_id_components, generate_random_alfanum_string
from osm_lcm.n2vc.vca.connection import get_connection
from retrying_async import retry
from typing import Tuple


class N2VCJujuConnector(N2VCConnector):

    """
    ####################################################################################
    ################################### P U B L I C ####################################
    ####################################################################################
    """

    BUILT_IN_CLOUDS = ["localhost", "microk8s"]
    libjuju = None

    def __init__(
        self,
        db: object,
        fs: object,
        log: object = None,
        on_update_db=None,
    ):
        """
        Constructor

        :param: db: Database object from osm_common
        :param: fs: Filesystem object from osm_common
        :param: log: Logger
        :param: on_update_db: Callback function to be called for updating the database.
        """

        # parent class constructor
        N2VCConnector.__init__(self, db=db, fs=fs, log=log, on_update_db=on_update_db)

        # silence websocket traffic log
        logging.getLogger("websockets.protocol").setLevel(logging.INFO)
        logging.getLogger("juju.client.connection").setLevel(logging.WARN)
        logging.getLogger("model").setLevel(logging.WARN)

        self.log.info("Initializing N2VC juju connector...")

        db_uri = EnvironConfig(prefixes=["OSMLCM_", "OSMMON_"]).get("database_uri")
        self._store = MotorStore(db_uri)
        self.loading_libjuju = asyncio.Lock()
        self.delete_namespace_locks = {}
        self.log.info("N2VC juju connector initialized")

    async def get_status(
        self, namespace: str, yaml_format: bool = True, vca_id: str = None
    ):
        """
        Get status from all juju models from a VCA

        :param namespace: we obtain ns from namespace
        :param yaml_format: returns a yaml string
        :param: vca_id: VCA ID from which the status will be retrieved.
        """
        # TODO: Review where is this function used. It is not optimal at all to get the status
        #       from all the juju models of a particular VCA. Additionally, these models might
        #       not have been deployed by OSM, in that case we are getting information from
        #       deployments outside of OSM's scope.

        # self.log.info('Getting NS status. namespace: {}'.format(namespace))
        libjuju = await self._get_libjuju(vca_id)

        _nsi_id, ns_id, _vnf_id, _vdu_id, _vdu_count = self._get_namespace_components(
            namespace=namespace
        )
        # model name is ns_id
        model_name = ns_id
        if model_name is None:
            msg = "Namespace {} not valid".format(namespace)
            self.log.error(msg)
            raise N2VCBadArgumentsException(msg, ["namespace"])

        status = {}
        models = await libjuju.list_models(contains=ns_id)

        for m in models:
            status[m] = await libjuju.get_model_status(m)

        if yaml_format:
            return obj_to_yaml(status)
        else:
            return obj_to_dict(status)

    async def update_vca_status(self, vcastatus: dict, vca_id: str = None):
        """
        Add all configs, actions, executed actions of all applications in a model to vcastatus dict.

        :param vcastatus: dict containing vcaStatus
        :param: vca_id: VCA ID

        :return: None
        """
        try:
            libjuju = await self._get_libjuju(vca_id)
            for model_name in vcastatus:
                # Adding executed actions
                vcastatus[model_name][
                    "executedActions"
                ] = await libjuju.get_executed_actions(model_name)
                for application in vcastatus[model_name]["applications"]:
                    # Adding application actions
                    vcastatus[model_name]["applications"][application][
                        "actions"
                    ] = await libjuju.get_actions(application, model_name)
                    # Adding application configs
                    vcastatus[model_name]["applications"][application][
                        "configs"
                    ] = await libjuju.get_application_configs(model_name, application)
        except Exception as e:
            self.log.debug("Error in updating vca status: {}".format(str(e)))

    async def create_execution_environment(
        self,
        namespace: str,
        db_dict: dict,
        reuse_ee_id: str = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        vca_id: str = None,
    ) -> (str, dict):
        """
        Create an Execution Environment. Returns when it is created or raises an
        exception on failing

        :param: namespace: Contains a dot separate string.
                    LCM will use: [<nsi-id>].<ns-id>.<vnf-id>.<vdu-id>[-<count>]
        :param: db_dict: where to write to database when the status changes.
            It contains a dictionary with {collection: str, filter: {},  path: str},
                e.g. {collection: "nsrs", filter: {_id: <nsd-id>, path:
                "_admin.deployed.VCA.3"}
        :param: reuse_ee_id: ee id from an older execution. It allows us to reuse an
                             older environment
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param: vca_id: VCA ID

        :returns: id of the new execution environment and credentials for it
                  (credentials can contains hostname, username, etc depending on underlying cloud)
        """

        self.log.info(
            "Creating execution environment. namespace: {}, reuse_ee_id: {}".format(
                namespace, reuse_ee_id
            )
        )
        libjuju = await self._get_libjuju(vca_id)

        machine_id = None
        if reuse_ee_id:
            model_name, application_name, machine_id = self._get_ee_id_components(
                ee_id=reuse_ee_id
            )
        else:
            (
                _nsi_id,
                ns_id,
                _vnf_id,
                _vdu_id,
                _vdu_count,
            ) = self._get_namespace_components(namespace=namespace)
            # model name is ns_id
            model_name = ns_id
            # application name
            application_name = self._get_application_name(namespace=namespace)

        self.log.debug(
            "model name: {}, application name:  {}, machine_id: {}".format(
                model_name, application_name, machine_id
            )
        )

        # create or reuse a new juju machine
        try:
            if not await libjuju.model_exists(model_name):
                await libjuju.add_model(model_name, libjuju.vca_connection.lxd_cloud)
            machine, new = await libjuju.create_machine(
                model_name=model_name,
                machine_id=machine_id,
                db_dict=db_dict,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
            )
            # id for the execution environment
            ee_id = N2VCJujuConnector._build_ee_id(
                model_name=model_name,
                application_name=application_name,
                machine_id=str(machine.entity_id),
            )
            self.log.debug("ee_id: {}".format(ee_id))

            if new:
                # write ee_id in database
                self._write_ee_id_db(db_dict=db_dict, ee_id=ee_id)

        except Exception as e:
            message = "Error creating machine on juju: {}".format(e)
            self.log.error(message)
            raise N2VCException(message=message)

        # new machine credentials
        credentials = {"hostname": machine.dns_name}

        self.log.info(
            "Execution environment created. ee_id: {}, credentials: {}".format(
                ee_id, credentials
            )
        )

        return ee_id, credentials

    async def register_execution_environment(
        self,
        namespace: str,
        credentials: dict,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        vca_id: str = None,
    ) -> str:
        """
        Register an existing execution environment at the VCA

        :param: namespace: Contains a dot separate string.
                    LCM will use: [<nsi-id>].<ns-id>.<vnf-id>.<vdu-id>[-<count>]
        :param: credentials: credentials to access the existing execution environment
                            (it can contains hostname, username, path to private key,
                            etc depending on underlying cloud)
        :param: db_dict: where to write to database when the status changes.
            It contains a dictionary with {collection: str, filter: {},  path: str},
                e.g. {collection: "nsrs", filter: {_id: <nsd-id>, path:
                "_admin.deployed.VCA.3"}
        :param: reuse_ee_id: ee id from an older execution. It allows us to reuse an
                             older environment
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param: vca_id: VCA ID

        :returns: id of the execution environment
        """
        self.log.info(
            "Registering execution environment. namespace={}, credentials={}".format(
                namespace, credentials
            )
        )
        libjuju = await self._get_libjuju(vca_id)

        if credentials is None:
            raise N2VCBadArgumentsException(
                message="credentials are mandatory", bad_args=["credentials"]
            )
        if credentials.get("hostname"):
            hostname = credentials["hostname"]
        else:
            raise N2VCBadArgumentsException(
                message="hostname is mandatory", bad_args=["credentials.hostname"]
            )
        if credentials.get("username"):
            username = credentials["username"]
        else:
            raise N2VCBadArgumentsException(
                message="username is mandatory", bad_args=["credentials.username"]
            )
        if "private_key_path" in credentials:
            private_key_path = credentials["private_key_path"]
        else:
            # if not passed as argument, use generated private key path
            private_key_path = self.private_key_path

        _nsi_id, ns_id, _vnf_id, _vdu_id, _vdu_count = self._get_namespace_components(
            namespace=namespace
        )

        # model name
        model_name = ns_id
        # application name
        application_name = self._get_application_name(namespace=namespace)

        # register machine on juju
        try:
            if not await libjuju.model_exists(model_name):
                await libjuju.add_model(model_name, libjuju.vca_connection.lxd_cloud)
            machine_id = await libjuju.provision_machine(
                model_name=model_name,
                hostname=hostname,
                username=username,
                private_key_path=private_key_path,
                db_dict=db_dict,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
            )
        except Exception as e:
            self.log.error("Error registering machine: {}".format(e))
            raise N2VCException(
                message="Error registering machine on juju: {}".format(e)
            )

        self.log.info("Machine registered: {}".format(machine_id))

        # id for the execution environment
        ee_id = N2VCJujuConnector._build_ee_id(
            model_name=model_name,
            application_name=application_name,
            machine_id=str(machine_id),
        )

        self.log.info("Execution environment registered. ee_id: {}".format(ee_id))

        return ee_id

    # In case of native_charm is being deployed, if JujuApplicationExists error happens
    # it will try to add_unit
    @retry(
        attempts=3,
        delay=5,
        retry_exceptions=(N2VCApplicationExists,),
        timeout=None,
        callback=retry_callback,
    )
    async def install_configuration_sw(
        self,
        ee_id: str,
        artifact_path: str,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        num_units: int = 1,
        vca_id: str = None,
        scaling_out: bool = False,
        vca_type: str = None,
    ):
        """
        Install the software inside the execution environment identified by ee_id

        :param: ee_id: the id of the execution environment returned by
                          create_execution_environment or register_execution_environment
        :param: artifact_path: where to locate the artifacts (parent folder) using
                                  the self.fs
                                  the final artifact path will be a combination of this
                                  artifact_path and additional string from the config_dict
                                  (e.g. charm name)
        :param: db_dict: where to write into database when the status changes.
                             It contains a dict with
                                {collection: <str>, filter: {},  path: <str>},
                                e.g. {collection: "nsrs", filter:
                                    {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param: config: Dictionary with deployment config information.
        :param: num_units: Number of units to deploy of a particular charm.
        :param: vca_id: VCA ID
        :param: scaling_out: Boolean to indicate if it is a scaling out operation
        :param: vca_type: VCA type
        """

        self.log.info(
            (
                "Installing configuration sw on ee_id: {}, "
                "artifact path: {}, db_dict: {}"
            ).format(ee_id, artifact_path, db_dict)
        )
        libjuju = await self._get_libjuju(vca_id)

        # check arguments
        if ee_id is None or len(ee_id) == 0:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )
        if artifact_path is None or len(artifact_path) == 0:
            raise N2VCBadArgumentsException(
                message="artifact_path is mandatory", bad_args=["artifact_path"]
            )
        if db_dict is None:
            raise N2VCBadArgumentsException(
                message="db_dict is mandatory", bad_args=["db_dict"]
            )

        try:
            (
                model_name,
                application_name,
                machine_id,
            ) = N2VCJujuConnector._get_ee_id_components(ee_id=ee_id)
            self.log.debug(
                "model: {}, application: {}, machine: {}".format(
                    model_name, application_name, machine_id
                )
            )
        except Exception:
            raise N2VCBadArgumentsException(
                message="ee_id={} is not a valid execution environment id".format(
                    ee_id
                ),
                bad_args=["ee_id"],
            )

        # remove // in charm path
        while artifact_path.find("//") >= 0:
            artifact_path = artifact_path.replace("//", "/")

        # check charm path
        if not self.fs.file_exists(artifact_path):
            msg = "artifact path does not exist: {}".format(artifact_path)
            raise N2VCBadArgumentsException(message=msg, bad_args=["artifact_path"])

        if artifact_path.startswith("/"):
            full_path = self.fs.path + artifact_path
        else:
            full_path = self.fs.path + "/" + artifact_path

        try:
            if vca_type == "native_charm" and await libjuju.check_application_exists(
                model_name, application_name
            ):
                await libjuju.add_unit(
                    application_name=application_name,
                    model_name=model_name,
                    machine_id=machine_id,
                    db_dict=db_dict,
                    progress_timeout=progress_timeout,
                    total_timeout=total_timeout,
                )
            else:
                await libjuju.deploy_charm(
                    model_name=model_name,
                    application_name=application_name,
                    path=full_path,
                    machine_id=machine_id,
                    db_dict=db_dict,
                    progress_timeout=progress_timeout,
                    total_timeout=total_timeout,
                    config=config,
                    num_units=num_units,
                )
        except JujuApplicationExists as e:
            raise N2VCApplicationExists(
                message="Error deploying charm into ee={} : {}".format(ee_id, e.message)
            )
        except Exception as e:
            raise N2VCException(
                message="Error deploying charm into ee={} : {}".format(ee_id, e)
            )

        self.log.info("Configuration sw installed")

    async def install_k8s_proxy_charm(
        self,
        charm_name: str,
        namespace: str,
        artifact_path: str,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        vca_id: str = None,
    ) -> str:
        """
        Install a k8s proxy charm

        :param charm_name: Name of the charm being deployed
        :param namespace: collection of all the uuids related to the charm.
        :param str artifact_path: where to locate the artifacts (parent folder) using
            the self.fs
            the final artifact path will be a combination of this artifact_path and
            additional string from the config_dict (e.g. charm name)
        :param dict db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nsrs", filter:
                                {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param config: Dictionary with additional configuration
        :param vca_id: VCA ID

        :returns ee_id: execution environment id.
        """
        self.log.info(
            "Installing k8s proxy charm: {}, artifact path: {}, db_dict: {}".format(
                charm_name, artifact_path, db_dict
            )
        )
        libjuju = await self._get_libjuju(vca_id)

        if artifact_path is None or len(artifact_path) == 0:
            raise N2VCBadArgumentsException(
                message="artifact_path is mandatory", bad_args=["artifact_path"]
            )
        if db_dict is None:
            raise N2VCBadArgumentsException(
                message="db_dict is mandatory", bad_args=["db_dict"]
            )

        # remove // in charm path
        while artifact_path.find("//") >= 0:
            artifact_path = artifact_path.replace("//", "/")

        # check charm path
        if not self.fs.file_exists(artifact_path):
            msg = "artifact path does not exist: {}".format(artifact_path)
            raise N2VCBadArgumentsException(message=msg, bad_args=["artifact_path"])

        if artifact_path.startswith("/"):
            full_path = self.fs.path + artifact_path
        else:
            full_path = self.fs.path + "/" + artifact_path

        _, ns_id, _, _, _ = self._get_namespace_components(namespace=namespace)
        model_name = "{}-k8s".format(ns_id)
        if not await libjuju.model_exists(model_name):
            await libjuju.add_model(model_name, libjuju.vca_connection.k8s_cloud)
        application_name = self._get_application_name(namespace)

        try:
            await libjuju.deploy_charm(
                model_name=model_name,
                application_name=application_name,
                path=full_path,
                machine_id=None,
                db_dict=db_dict,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
                config=config,
            )
        except Exception as e:
            raise N2VCException(message="Error deploying charm: {}".format(e))

        self.log.info("K8s proxy charm installed")
        ee_id = N2VCJujuConnector._build_ee_id(
            model_name=model_name, application_name=application_name, machine_id="k8s"
        )

        self._write_ee_id_db(db_dict=db_dict, ee_id=ee_id)

        return ee_id

    async def get_ee_ssh_public__key(
        self,
        ee_id: str,
        db_dict: dict,
        progress_timeout: float = None,
        total_timeout: float = None,
        vca_id: str = None,
    ) -> str:
        """
        Get Execution environment ssh public key

        :param: ee_id: the id of the execution environment returned by
            create_execution_environment or register_execution_environment
        :param: db_dict: where to write into database when the status changes.
                            It contains a dict with
                                {collection: <str>, filter: {},  path: <str>},
                                e.g. {collection: "nsrs", filter:
                                    {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param vca_id: VCA ID
        :returns: public key of the execution environment
                    For the case of juju proxy charm ssh-layered, it is the one
                    returned by 'get-ssh-public-key' primitive.
                    It raises a N2VC exception if fails
        """

        self.log.info(
            (
                "Generating priv/pub key pair and get pub key on ee_id: {}, db_dict: {}"
            ).format(ee_id, db_dict)
        )
        libjuju = await self._get_libjuju(vca_id)

        # check arguments
        if ee_id is None or len(ee_id) == 0:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )
        if db_dict is None:
            raise N2VCBadArgumentsException(
                message="db_dict is mandatory", bad_args=["db_dict"]
            )

        try:
            (
                model_name,
                application_name,
                machine_id,
            ) = N2VCJujuConnector._get_ee_id_components(ee_id=ee_id)
            self.log.debug(
                "model: {}, application: {}, machine: {}".format(
                    model_name, application_name, machine_id
                )
            )
        except Exception:
            raise N2VCBadArgumentsException(
                message="ee_id={} is not a valid execution environment id".format(
                    ee_id
                ),
                bad_args=["ee_id"],
            )

        # try to execute ssh layer primitives (if exist):
        #       generate-ssh-key
        #       get-ssh-public-key

        output = None

        application_name = N2VCJujuConnector._format_app_name(application_name)

        # execute action: generate-ssh-key
        try:
            output, _status = await libjuju.execute_action(
                model_name=model_name,
                application_name=application_name,
                action_name="generate-ssh-key",
                db_dict=db_dict,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
            )
        except Exception as e:
            self.log.info(
                "Skipping exception while executing action generate-ssh-key: {}".format(
                    e
                )
            )

        # execute action: get-ssh-public-key
        try:
            output, _status = await libjuju.execute_action(
                model_name=model_name,
                application_name=application_name,
                action_name="get-ssh-public-key",
                db_dict=db_dict,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
            )
        except Exception as e:
            msg = "Cannot execute action get-ssh-public-key: {}\n".format(e)
            self.log.info(msg)
            raise N2VCExecutionException(e, primitive_name="get-ssh-public-key")

        # return public key if exists
        return output["pubkey"] if "pubkey" in output else output

    async def get_metrics(
        self, model_name: str, application_name: str, vca_id: str = None
    ) -> dict:
        """
        Get metrics from application

        :param: model_name: Model name
        :param: application_name: Application name
        :param: vca_id: VCA ID

        :return: Dictionary with obtained metrics
        """
        libjuju = await self._get_libjuju(vca_id)
        return await libjuju.get_metrics(model_name, application_name)

    async def add_relation(
        self, provider: RelationEndpoint, requirer: RelationEndpoint
    ):
        """
        Add relation between two charmed endpoints

        :param: provider: Provider relation endpoint
        :param: requirer: Requirer relation endpoint
        """
        self.log.debug(f"adding new relation between {provider} and {requirer}")
        cross_model_relation = (
            provider.model_name != requirer.model_name
            or provider.vca_id != requirer.vca_id
        )
        try:
            if cross_model_relation:
                # Cross-model relation
                provider_libjuju = await self._get_libjuju(provider.vca_id)
                requirer_libjuju = await self._get_libjuju(requirer.vca_id)
                offer = await provider_libjuju.offer(provider)
                if offer:
                    saas_name = await requirer_libjuju.consume(
                        requirer.model_name, offer, provider_libjuju
                    )
                    await requirer_libjuju.add_relation(
                        requirer.model_name, requirer.endpoint, saas_name
                    )
            else:
                # Standard relation
                vca_id = provider.vca_id
                model = provider.model_name
                libjuju = await self._get_libjuju(vca_id)
                # add juju relations between two applications
                await libjuju.add_relation(
                    model_name=model,
                    endpoint_1=provider.endpoint,
                    endpoint_2=requirer.endpoint,
                )
        except Exception as e:
            message = f"Error adding relation between {provider} and {requirer}: {e}"
            self.log.error(message)
            raise N2VCException(message=message)

    async def remove_relation(self):
        # TODO
        self.log.info("Method not implemented yet")
        raise MethodNotImplemented()

    async def deregister_execution_environments(self):
        self.log.info("Method not implemented yet")
        raise MethodNotImplemented()

    async def delete_namespace(
        self,
        namespace: str,
        db_dict: dict = None,
        total_timeout: float = None,
        vca_id: str = None,
    ):
        """
        Remove a network scenario and its execution environments
        :param: namespace: [<nsi-id>].<ns-id>
        :param: db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nsrs", filter:
                                {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param: total_timeout: Total timeout
        :param: vca_id: VCA ID
        """
        self.log.info("Deleting namespace={}".format(namespace))
        will_not_delete = False
        if namespace not in self.delete_namespace_locks:
            self.delete_namespace_locks[namespace] = asyncio.Lock()
        delete_lock = self.delete_namespace_locks[namespace]

        while delete_lock.locked():
            will_not_delete = True
            await asyncio.sleep(0.1)

        if will_not_delete:
            self.log.info("Namespace {} deleted by another worker.".format(namespace))
            return

        try:
            async with delete_lock:
                libjuju = await self._get_libjuju(vca_id)

                # check arguments
                if namespace is None:
                    raise N2VCBadArgumentsException(
                        message="namespace is mandatory", bad_args=["namespace"]
                    )

                (
                    _nsi_id,
                    ns_id,
                    _vnf_id,
                    _vdu_id,
                    _vdu_count,
                ) = self._get_namespace_components(namespace=namespace)
                if ns_id is not None:
                    try:
                        models = await libjuju.list_models(contains=ns_id)
                        for model in models:
                            await libjuju.destroy_model(
                                model_name=model, total_timeout=total_timeout
                            )
                    except Exception as e:
                        self.log.error(f"Error deleting namespace {namespace} : {e}")
                        raise N2VCException(
                            message="Error deleting namespace {} : {}".format(
                                namespace, e
                            )
                        )
                else:
                    raise N2VCBadArgumentsException(
                        message="only ns_id is permitted to delete yet",
                        bad_args=["namespace"],
                    )
        except Exception as e:
            self.log.error(f"Error deleting namespace {namespace} : {e}")
            raise e
        finally:
            self.delete_namespace_locks.pop(namespace)
        self.log.info("Namespace {} deleted".format(namespace))

    async def delete_execution_environment(
        self,
        ee_id: str,
        db_dict: dict = None,
        total_timeout: float = None,
        scaling_in: bool = False,
        vca_type: str = None,
        vca_id: str = None,
        application_to_delete: str = None,
    ):
        """
        Delete an execution environment
        :param str ee_id: id of the execution environment to delete
        :param dict db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nsrs", filter:
                                {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param total_timeout: Total timeout
        :param scaling_in: Boolean to indicate if it is a scaling in operation
        :param vca_type: VCA type
        :param vca_id: VCA ID
        :param application_to_delete: name of the single application to be deleted
        """
        self.log.info("Deleting execution environment ee_id={}".format(ee_id))
        libjuju = await self._get_libjuju(vca_id)

        # check arguments
        if ee_id is None:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )

        model_name, application_name, machine_id = self._get_ee_id_components(
            ee_id=ee_id
        )
        try:
            if application_to_delete == application_name:
                # destroy the application
                await libjuju.destroy_application(
                    model_name=model_name,
                    application_name=application_name,
                    total_timeout=total_timeout,
                )
                # if model is empty delete it
                controller = await libjuju.get_controller()
                model = await libjuju.get_model(
                    controller=controller,
                    model_name=model_name,
                )
                if not model.applications:
                    self.log.info("Model {} is empty, deleting it".format(model_name))
                    await libjuju.destroy_model(
                        model_name=model_name,
                        total_timeout=total_timeout,
                    )
            elif not scaling_in:
                # destroy the model
                await libjuju.destroy_model(
                    model_name=model_name, total_timeout=total_timeout
                )
            elif vca_type == "native_charm" and scaling_in:
                # destroy the unit in the application
                await libjuju.destroy_unit(
                    application_name=application_name,
                    model_name=model_name,
                    machine_id=machine_id,
                    total_timeout=total_timeout,
                )
            else:
                # destroy the application
                await libjuju.destroy_application(
                    model_name=model_name,
                    application_name=application_name,
                    total_timeout=total_timeout,
                )
        except Exception as e:
            raise N2VCException(
                message=(
                    "Error deleting execution environment {} (application {}) : {}"
                ).format(ee_id, application_name, e)
            )

        self.log.info("Execution environment {} deleted".format(ee_id))

    async def exec_primitive(
        self,
        ee_id: str,
        primitive_name: str,
        params_dict: dict,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        vca_id: str = None,
        vca_type: str = None,
    ) -> str:
        """
        Execute a primitive in the execution environment

        :param: ee_id: the one returned by create_execution_environment or
            register_execution_environment
        :param: primitive_name: must be one defined in the software. There is one
            called 'config', where, for the proxy case, the 'credentials' of VM are
            provided
        :param: params_dict: parameters of the action
        :param: db_dict: where to write into database when the status changes.
                        It contains a dict with
                            {collection: <str>, filter: {},  path: <str>},
                            e.g. {collection: "nsrs", filter:
                                {_id: <nsd-id>, path: "_admin.deployed.VCA.3"}
        :param: progress_timeout: Progress timeout
        :param: total_timeout: Total timeout
        :param: vca_id: VCA ID
        :param: vca_type: VCA type
        :returns str: primitive result, if ok. It raises exceptions in case of fail
        """

        self.log.info(
            "Executing primitive: {} on ee: {}, params: {}".format(
                primitive_name, ee_id, params_dict
            )
        )
        libjuju = await self._get_libjuju(vca_id)

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
            (
                model_name,
                application_name,
                machine_id,
            ) = N2VCJujuConnector._get_ee_id_components(ee_id=ee_id)
            # To run action on the leader unit in libjuju.execute_action function,
            # machine_id must be set to None if vca_type is not native_charm
            if vca_type != "native_charm":
                machine_id = None
        except Exception:
            raise N2VCBadArgumentsException(
                message="ee_id={} is not a valid execution environment id".format(
                    ee_id
                ),
                bad_args=["ee_id"],
            )

        if primitive_name == "config":
            # Special case: config primitive
            try:
                await libjuju.configure_application(
                    model_name=model_name,
                    application_name=application_name,
                    config=params_dict,
                )
                actions = await libjuju.get_actions(
                    application_name=application_name, model_name=model_name
                )
                self.log.debug(
                    "Application {} has these actions: {}".format(
                        application_name, actions
                    )
                )
                if "verify-ssh-credentials" in actions:
                    # execute verify-credentials
                    num_retries = 20
                    retry_timeout = 15.0
                    for _ in range(num_retries):
                        try:
                            self.log.debug("Executing action verify-ssh-credentials...")
                            output, ok = await libjuju.execute_action(
                                model_name=model_name,
                                application_name=application_name,
                                action_name="verify-ssh-credentials",
                                db_dict=db_dict,
                                progress_timeout=progress_timeout,
                                total_timeout=total_timeout,
                            )

                            if ok == "failed":
                                self.log.debug(
                                    "Error executing verify-ssh-credentials: {}. Retrying..."
                                )
                                await asyncio.sleep(retry_timeout)

                                continue
                            self.log.debug("Result: {}, output: {}".format(ok, output))
                            break
                        except asyncio.CancelledError:
                            raise
                    else:
                        self.log.error(
                            "Error executing verify-ssh-credentials after {} retries. ".format(
                                num_retries
                            )
                        )
                else:
                    msg = "Action verify-ssh-credentials does not exist in application {}".format(
                        application_name
                    )
                    self.log.debug(msg=msg)
            except Exception as e:
                self.log.error("Error configuring juju application: {}".format(e))
                raise N2VCExecutionException(
                    message="Error configuring application into ee={} : {}".format(
                        ee_id, e
                    ),
                    primitive_name=primitive_name,
                )
            return "CONFIG OK"
        else:
            try:
                output, status = await libjuju.execute_action(
                    model_name=model_name,
                    application_name=application_name,
                    action_name=primitive_name,
                    db_dict=db_dict,
                    machine_id=machine_id,
                    progress_timeout=progress_timeout,
                    total_timeout=total_timeout,
                    **params_dict,
                )
                if status == "completed":
                    return output
                else:
                    if "output" in output:
                        raise Exception(f'{status}: {output["output"]}')
                    else:
                        raise Exception(
                            f"{status}: No further information received from action"
                        )

            except Exception as e:
                self.log.error(f"Error executing primitive {primitive_name}: {e}")
                raise N2VCExecutionException(
                    message=f"Error executing primitive {primitive_name} in ee={ee_id}: {e}",
                    primitive_name=primitive_name,
                )

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
        self.log.info("Upgrading charm: {} on ee: {}".format(path, ee_id))
        libjuju = await self._get_libjuju(charm_id)

        # check arguments
        if ee_id is None or len(ee_id) == 0:
            raise N2VCBadArgumentsException(
                message="ee_id is mandatory", bad_args=["ee_id"]
            )
        try:
            (
                model_name,
                application_name,
                machine_id,
            ) = N2VCJujuConnector._get_ee_id_components(ee_id=ee_id)

        except Exception:
            raise N2VCBadArgumentsException(
                message="ee_id={} is not a valid execution environment id".format(
                    ee_id
                ),
                bad_args=["ee_id"],
            )

        try:
            await libjuju.upgrade_charm(
                application_name=application_name,
                path=path,
                model_name=model_name,
                total_timeout=timeout,
            )

            return f"Charm upgraded with application name {application_name}"

        except Exception as e:
            self.log.error("Error upgrading charm {}: {}".format(path, e))

            raise N2VCException(
                message="Error upgrading charm {} in ee={} : {}".format(path, ee_id, e)
            )

    async def disconnect(self, vca_id: str = None):
        """
        Disconnect from VCA

        :param: vca_id: VCA ID
        """
        self.log.info("closing juju N2VC...")
        libjuju = await self._get_libjuju(vca_id)
        try:
            await libjuju.disconnect()
        except Exception as e:
            raise N2VCConnectionException(
                message="Error disconnecting controller: {}".format(e),
                url=libjuju.vca_connection.data.endpoints,
            )

    """
####################################################################################
################################### P R I V A T E ##################################
####################################################################################
    """

    async def _get_libjuju(self, vca_id: str = None) -> Libjuju:
        """
        Get libjuju object

        :param: vca_id: VCA ID
                        If None, get a libjuju object with a Connection to the default VCA
                        Else, geta libjuju object with a Connection to the specified VCA
        """
        if not vca_id:
            while self.loading_libjuju.locked():
                await asyncio.sleep(0.1)
            if not self.libjuju:
                async with self.loading_libjuju:
                    vca_connection = await get_connection(self._store)
                    self.libjuju = Libjuju(vca_connection, log=self.log)
            return self.libjuju
        else:
            vca_connection = await get_connection(self._store, vca_id)
            return Libjuju(vca_connection, log=self.log, n2vc=self)

    def _write_ee_id_db(self, db_dict: dict, ee_id: str):
        # write ee_id to database: _admin.deployed.VCA.x
        try:
            the_table = db_dict["collection"]
            the_filter = db_dict["filter"]
            the_path = db_dict["path"]
            if not the_path[-1] == ".":
                the_path = the_path + "."
            update_dict = {the_path + "ee_id": ee_id}
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
            self.log.error("Error writing ee_id to database: {}".format(e))

    @staticmethod
    def _build_ee_id(model_name: str, application_name: str, machine_id: str):
        """
        Build an execution environment id form model, application and machine
        :param model_name:
        :param application_name:
        :param machine_id:
        :return:
        """
        # id for the execution environment
        return "{}.{}.{}".format(model_name, application_name, machine_id)

    @staticmethod
    def _get_ee_id_components(ee_id: str) -> (str, str, str):
        """
        Get model, application and machine components from an execution environment id
        :param ee_id:
        :return: model_name, application_name, machine_id
        """

        return get_ee_id_components(ee_id)

    @staticmethod
    def _find_charm_level(vnf_id: str, vdu_id: str) -> str:
        """Decides the charm level.
        Args:
            vnf_id  (str):  VNF id
            vdu_id  (str):  VDU id

        Returns:
            charm_level (str):  ns-level or vnf-level or vdu-level
        """
        if vdu_id and not vnf_id:
            raise N2VCException(message="If vdu-id exists, vnf-id should be provided.")
        if vnf_id and vdu_id:
            return "vdu-level"
        if vnf_id and not vdu_id:
            return "vnf-level"
        if not vnf_id and not vdu_id:
            return "ns-level"

    @staticmethod
    def _generate_backward_compatible_application_name(
        vnf_id: str, vdu_id: str, vdu_count: str
    ) -> str:
        """Generate backward compatible application name
         by limiting the app name to 50 characters.

        Args:
            vnf_id  (str):  VNF ID
            vdu_id  (str):  VDU ID
            vdu_count   (str):  vdu-count-index

        Returns:
            application_name (str): generated application name

        """
        if vnf_id is None or len(vnf_id) == 0:
            vnf_id = ""
        else:
            # Shorten the vnf_id to its last twelve characters
            vnf_id = "vnf-" + vnf_id[-12:]

        if vdu_id is None or len(vdu_id) == 0:
            vdu_id = ""
        else:
            # Shorten the vdu_id to its last twelve characters
            vdu_id = "-vdu-" + vdu_id[-12:]

        if vdu_count is None or len(vdu_count) == 0:
            vdu_count = ""
        else:
            vdu_count = "-cnt-" + vdu_count

        # Generate a random suffix with 5 characters (the default size used by K8s)
        random_suffix = generate_random_alfanum_string(size=5)

        application_name = "app-{}{}{}-{}".format(
            vnf_id, vdu_id, vdu_count, random_suffix
        )
        return application_name

    @staticmethod
    def _get_vca_record(search_key: str, vca_records: list, vdu_id: str) -> dict:
        """Get the correct VCA record dict depending on the search key

        Args:
            search_key  (str):      keyword to find the correct VCA record
            vca_records (list):     All VCA records as list
            vdu_id  (str):          VDU ID

        Returns:
            vca_record  (dict):     Dictionary which includes the correct VCA record

        """
        return next(
            filter(lambda record: record[search_key] == vdu_id, vca_records), {}
        )

    @staticmethod
    def _generate_application_name(
        charm_level: str,
        vnfrs: dict,
        vca_records: list,
        vnf_count: str = None,
        vdu_id: str = None,
        vdu_count: str = None,
    ) -> str:
        """Generate application name to make the relevant charm of VDU/KDU
        in the VNFD descriptor become clearly visible.
        Limiting the app name to 50 characters.

        Args:
            charm_level  (str):  level of charm
            vnfrs  (dict):  vnf record dict
            vca_records   (list):   db_nsr["_admin"]["deployed"]["VCA"] as list
            vnf_count   (str): vnf count index
            vdu_id   (str):  VDU ID
            vdu_count   (str):  vdu count index

        Returns:
            application_name (str): generated application name

        """
        application_name = ""
        if charm_level == "ns-level":
            if len(vca_records) != 1:
                raise N2VCException(message="One VCA record is expected.")
            # Only one VCA record is expected if it's ns-level charm.
            # Shorten the charm name to its first 40 characters.
            charm_name = vca_records[0]["charm_name"][:40]
            if not charm_name:
                raise N2VCException(message="Charm name should be provided.")
            application_name = charm_name + "-ns"

        elif charm_level == "vnf-level":
            if len(vca_records) < 1:
                raise N2VCException(message="One or more VCA record is expected.")
            # If VNF is scaled, more than one VCA record may be included in vca_records
            # but ee_descriptor_id is same.
            # Shorten the ee_descriptor_id and member-vnf-index-ref
            # to first 12 characters.
            application_name = (
                vca_records[0]["ee_descriptor_id"][:12]
                + "-"
                + vnf_count
                + "-"
                + vnfrs["member-vnf-index-ref"][:12]
                + "-vnf"
            )
        elif charm_level == "vdu-level":
            if len(vca_records) < 1:
                raise N2VCException(message="One or more VCA record is expected.")

            # Charms are also used for deployments with Helm charts.
            # If deployment unit is a Helm chart/KDU,
            # vdu_profile_id and vdu_count will be empty string.
            if vdu_count is None:
                vdu_count = ""

            # If vnf/vdu is scaled, more than one VCA record may be included in vca_records
            # but ee_descriptor_id is same.
            # Shorten the ee_descriptor_id, member-vnf-index-ref and vdu_profile_id
            # to first 12 characters.
            if not vdu_id:
                raise N2VCException(message="vdu-id should be provided.")

            vca_record = N2VCJujuConnector._get_vca_record(
                "vdu_id", vca_records, vdu_id
            )

            if not vca_record:
                vca_record = N2VCJujuConnector._get_vca_record(
                    "kdu_name", vca_records, vdu_id
                )

            application_name = (
                vca_record["ee_descriptor_id"][:12]
                + "-"
                + vnf_count
                + "-"
                + vnfrs["member-vnf-index-ref"][:12]
                + "-"
                + vdu_id[:12]
                + "-"
                + vdu_count
                + "-vdu"
            )

        return application_name

    def _get_vnf_count_and_record(
        self, charm_level: str, vnf_id_and_count: str
    ) -> Tuple[str, dict]:
        """Get the vnf count and VNF record depend on charm level

        Args:
            charm_level  (str)
            vnf_id_and_count (str)

        Returns:
            (vnf_count  (str), db_vnfr(dict)) as Tuple

        """
        vnf_count = ""
        db_vnfr = {}

        if charm_level in ("vnf-level", "vdu-level"):
            vnf_id = "-".join(vnf_id_and_count.split("-")[:-1])
            vnf_count = vnf_id_and_count.split("-")[-1]
            db_vnfr = self.db.get_one("vnfrs", {"_id": vnf_id})

        # If the charm is ns level, it returns empty vnf_count and db_vnfr
        return vnf_count, db_vnfr

    @staticmethod
    def _get_vca_records(charm_level: str, db_nsr: dict, db_vnfr: dict) -> list:
        """Get the VCA records from db_nsr dict

        Args:
            charm_level (str):  level of charm
            db_nsr  (dict):     NS record from database
            db_vnfr (dict):     VNF record from database

        Returns:
            vca_records (list):  List of VCA record dictionaries

        """
        vca_records = {}
        if charm_level == "ns-level":
            vca_records = list(
                filter(
                    lambda vca_record: vca_record["target_element"] == "ns",
                    db_nsr["_admin"]["deployed"]["VCA"],
                )
            )
        elif charm_level in ["vnf-level", "vdu-level"]:
            vca_records = list(
                filter(
                    lambda vca_record: vca_record["member-vnf-index"]
                    == db_vnfr["member-vnf-index-ref"],
                    db_nsr["_admin"]["deployed"]["VCA"],
                )
            )

        return vca_records

    def _get_application_name(self, namespace: str) -> str:
        """Build application name from namespace

        Application name structure:
            NS level: <charm-name>-ns
            VNF level: <ee-name>-z<vnf-ordinal-scale-number>-<vnf-profile-id>-vnf
            VDU level: <ee-name>-z<vnf-ordinal-scale-number>-<vnf-profile-id>-
            <vdu-profile-id>-z<vdu-ordinal-scale-number>-vdu

        Application naming for backward compatibility (old structure):
            NS level: app-<random_value>
            VNF level: app-vnf-<vnf-id>-z<ordinal-scale-number>-<random_value>
            VDU level: app-vnf-<vnf-id>-z<vnf-ordinal-scale-number>-vdu-
            <vdu-id>-cnt-<vdu-count>-z<vdu-ordinal-scale-number>-<random_value>

        Args:
            namespace   (str)

        Returns:
            application_name    (str)

        """
        # split namespace components
        (
            nsi_id,
            ns_id,
            vnf_id_and_count,
            vdu_id,
            vdu_count,
        ) = self._get_namespace_components(namespace=namespace)

        if not ns_id:
            raise N2VCException(message="ns-id should be provided.")

        charm_level = self._find_charm_level(vnf_id_and_count, vdu_id)
        db_nsr = self.db.get_one("nsrs", {"_id": ns_id})
        vnf_count, db_vnfr = self._get_vnf_count_and_record(
            charm_level, vnf_id_and_count
        )
        vca_records = self._get_vca_records(charm_level, db_nsr, db_vnfr)

        if all("charm_name" in vca_record.keys() for vca_record in vca_records):
            application_name = self._generate_application_name(
                charm_level,
                db_vnfr,
                vca_records,
                vnf_count=vnf_count,
                vdu_id=vdu_id,
                vdu_count=vdu_count,
            )
        else:
            application_name = self._generate_backward_compatible_application_name(
                vnf_id_and_count, vdu_id, vdu_count
            )

        return N2VCJujuConnector._format_app_name(application_name)

    @staticmethod
    def _format_model_name(name: str) -> str:
        """Format the name of the model.

        Model names may only contain lowercase letters, digits and hyphens
        """

        return name.replace("_", "-").replace(" ", "-").lower()

    @staticmethod
    def _format_app_name(name: str) -> str:
        """Format the name of the application (in order to assure valid application name).

        Application names have restrictions (run juju deploy --help):
            - contains lowercase letters 'a'-'z'
            - contains numbers '0'-'9'
            - contains hyphens '-'
            - starts with a lowercase letter
            - not two or more consecutive hyphens
            - after a hyphen, not a group with all numbers
        """

        def all_numbers(s: str) -> bool:
            for c in s:
                if not c.isdigit():
                    return False
            return True

        new_name = name.replace("_", "-")
        new_name = new_name.replace(" ", "-")
        new_name = new_name.lower()
        while new_name.find("--") >= 0:
            new_name = new_name.replace("--", "-")
        groups = new_name.split("-")

        # find 'all numbers' groups and prefix them with a letter
        app_name = ""
        for i in range(len(groups)):
            group = groups[i]
            if all_numbers(group):
                group = "z" + group
            if i > 0:
                app_name += "-"
            app_name += group

        if app_name[0].isdigit():
            app_name = "z" + app_name

        return app_name

    async def validate_vca(self, vca_id: str):
        """
        Validate a VCA by connecting/disconnecting to/from it

        :param: vca_id: VCA ID
        """
        vca_connection = await get_connection(self._store, vca_id=vca_id)
        libjuju = Libjuju(vca_connection, log=self.log, n2vc=self)
        controller = await libjuju.get_controller()
        await libjuju.disconnect_controller(controller)
