# Copyright 2020 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import asyncio
import logging
import os
import typing
import yaml

import time

import juju.errors
from juju.bundle import BundleHandler
from juju.model import Model
from juju.machine import Machine
from juju.application import Application
from juju.unit import Unit
from juju.url import URL
from juju.version import DEFAULT_ARCHITECTURE
from juju.client._definitions import (
    FullStatus,
    QueryApplicationOffersResults,
    Cloud,
    CloudCredential,
)
from juju.controller import Controller
from juju.client import client
from juju import tag

from osm_lcm.n2vc.definitions import Offer, RelationEndpoint
from osm_lcm.n2vc.juju_watcher import JujuModelWatcher
from osm_lcm.n2vc.provisioner import AsyncSSHProvisioner
from osm_lcm.n2vc.n2vc_conn import N2VCConnector
from osm_lcm.n2vc.exceptions import (
    JujuMachineNotFound,
    JujuApplicationNotFound,
    JujuLeaderUnitNotFound,
    JujuActionNotFound,
    JujuControllerFailedConnecting,
    JujuApplicationExists,
    JujuInvalidK8sConfiguration,
    JujuError,
)
from osm_lcm.n2vc.vca.cloud import Cloud as VcaCloud
from osm_lcm.n2vc.vca.connection import Connection
from kubernetes.client.configuration import Configuration
from retrying_async import retry


RBAC_LABEL_KEY_NAME = "rbac-id"


@asyncio.coroutine
def retry_callback(attempt, exc, args, kwargs, delay=0.5, *, loop):
    # Specifically overridden from upstream implementation so it can
    # continue to work with Python 3.10
    yield from asyncio.sleep(attempt * delay)
    return retry


class Libjuju:
    def __init__(
        self,
        vca_connection: Connection,
        log: logging.Logger = None,
        n2vc: N2VCConnector = None,
    ):
        """
        Constructor

        :param: vca_connection:         n2vc.vca.connection object
        :param: log:                    Logger
        :param: n2vc:                   N2VC object
        """

        self.log = log or logging.getLogger("Libjuju")
        self.n2vc = n2vc
        self.vca_connection = vca_connection

        self.creating_model = asyncio.Lock()

        if self.vca_connection.is_default:
            self.health_check_task = self._create_health_check_task()

    def _create_health_check_task(self):
        return asyncio.get_event_loop().create_task(self.health_check())

    async def get_controller(self, timeout: float = 60.0) -> Controller:
        """
        Get controller

        :param: timeout: Time in seconds to wait for controller to connect
        """
        controller = None
        try:
            controller = Controller()
            await asyncio.wait_for(
                controller.connect(
                    endpoint=self.vca_connection.data.endpoints,
                    username=self.vca_connection.data.user,
                    password=self.vca_connection.data.secret,
                    cacert=self.vca_connection.data.cacert,
                ),
                timeout=timeout,
            )
            if self.vca_connection.is_default:
                endpoints = await controller.api_endpoints
                if not all(
                    endpoint in self.vca_connection.endpoints for endpoint in endpoints
                ):
                    await self.vca_connection.update_endpoints(endpoints)
            return controller
        except asyncio.CancelledError as e:
            raise e
        except Exception as e:
            self.log.error(
                "Failed connecting to controller: {}... {}".format(
                    self.vca_connection.data.endpoints, e
                )
            )
            if controller:
                await self.disconnect_controller(controller)

            raise JujuControllerFailedConnecting(
                f"Error connecting to Juju controller: {e}"
            )

    async def disconnect(self):
        """Disconnect"""
        # Cancel health check task
        self.health_check_task.cancel()
        self.log.debug("Libjuju disconnected!")

    async def disconnect_model(self, model: Model):
        """
        Disconnect model

        :param: model: Model that will be disconnected
        """
        await model.disconnect()

    async def disconnect_controller(self, controller: Controller):
        """
        Disconnect controller

        :param: controller: Controller that will be disconnected
        """
        if controller:
            await controller.disconnect()

    @retry(attempts=3, delay=5, timeout=None, callback=retry_callback)
    async def add_model(self, model_name: str, cloud: VcaCloud):
        """
        Create model

        :param: model_name: Model name
        :param: cloud: Cloud object
        """

        # Get controller
        controller = await self.get_controller()
        model = None
        try:
            # Block until other workers have finished model creation
            while self.creating_model.locked():
                await asyncio.sleep(0.1)

            # Create the model
            async with self.creating_model:
                if await self.model_exists(model_name, controller=controller):
                    return
                self.log.debug("Creating model {}".format(model_name))
                model = await controller.add_model(
                    model_name,
                    config=self.vca_connection.data.model_config,
                    cloud_name=cloud.name,
                    credential_name=cloud.credential_name,
                )
        except juju.errors.JujuAPIError as e:
            if "already exists" in e.message:
                pass
            else:
                raise e
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def get_executed_actions(self, model_name: str) -> list:
        """
        Get executed/history of actions for a model.

        :param: model_name: Model name, str.
        :return: List of executed actions for a model.
        """
        model = None
        executed_actions = []
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)
            # Get all unique action names
            actions = {}
            for application in model.applications:
                application_actions = await self.get_actions(application, model_name)
                actions.update(application_actions)
            # Get status of all actions
            for application_action in actions:
                app_action_status_list = await model.get_action_status(
                    name=application_action
                )
                for action_id, action_status in app_action_status_list.items():
                    executed_action = {
                        "id": action_id,
                        "action": application_action,
                        "status": action_status,
                    }
                    # Get action output by id
                    action_status = await model.get_action_output(executed_action["id"])
                    for k, v in action_status.items():
                        executed_action[k] = v
                    executed_actions.append(executed_action)
        except Exception as e:
            raise JujuError(
                "Error in getting executed actions for model: {}. Error: {}".format(
                    model_name, str(e)
                )
            )
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)
        return executed_actions

    async def get_application_configs(
        self, model_name: str, application_name: str
    ) -> dict:
        """
        Get available configs for an application.

        :param: model_name: Model name, str.
        :param: application_name: Application name, str.

        :return: A dict which has key - action name, value - action description
        """
        model = None
        application_configs = {}
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)
            application = self._get_application(
                model, application_name=application_name
            )
            application_configs = await application.get_config()
        except Exception as e:
            raise JujuError(
                "Error in getting configs for application: {} in model: {}. Error: {}".format(
                    application_name, model_name, str(e)
                )
            )
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)
        return application_configs

    @retry(attempts=3, delay=5, callback=retry_callback)
    async def get_model(self, controller: Controller, model_name: str) -> Model:
        """
        Get model from controller

        :param: controller: Controller
        :param: model_name: Model name

        :return: Model: The created Juju model object
        """
        return await controller.get_model(model_name)

    async def model_exists(
        self, model_name: str, controller: Controller = None
    ) -> bool:
        """
        Check if model exists

        :param: controller: Controller
        :param: model_name: Model name

        :return bool
        """
        need_to_disconnect = False

        # Get controller if not passed
        if not controller:
            controller = await self.get_controller()
            need_to_disconnect = True

        # Check if model exists
        try:
            return model_name in await controller.list_models()
        finally:
            if need_to_disconnect:
                await self.disconnect_controller(controller)

    async def models_exist(self, model_names: [str]) -> (bool, list):
        """
        Check if models exists

        :param: model_names: List of strings with model names

        :return (bool, list[str]): (True if all models exists, List of model names that don't exist)
        """
        if not model_names:
            raise Exception(
                "model_names must be a non-empty array. Given value: {}".format(
                    model_names
                )
            )
        non_existing_models = []
        models = await self.list_models()
        existing_models = list(set(models).intersection(model_names))
        non_existing_models = list(set(model_names) - set(existing_models))

        return (
            len(non_existing_models) == 0,
            non_existing_models,
        )

    async def get_model_status(self, model_name: str) -> FullStatus:
        """
        Get model status

        :param: model_name: Model name

        :return: Full status object
        """
        controller = await self.get_controller()
        model = await self.get_model(controller, model_name)
        try:
            return await model.get_status()
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def create_machine(
        self,
        model_name: str,
        machine_id: str = None,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        series: str = "bionic",
        wait: bool = True,
    ) -> (Machine, bool):
        """
        Create machine

        :param: model_name:         Model name
        :param: machine_id:         Machine id
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active
        :param: series:             Series of the machine (xenial, bionic, focal, ...)
        :param: wait:               Wait until machine is ready

        :return: (juju.machine.Machine, bool):  Machine object and a boolean saying
                                                if the machine is new or it already existed
        """
        new = False
        machine = None

        self.log.debug(
            "Creating machine (id={}) in model: {}".format(machine_id, model_name)
        )

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)
        try:
            if machine_id is not None:
                self.log.debug(
                    "Searching machine (id={}) in model {}".format(
                        machine_id, model_name
                    )
                )

                # Get machines from model and get the machine with machine_id if exists
                machines = await model.get_machines()
                if machine_id in machines:
                    self.log.debug(
                        "Machine (id={}) found in model {}".format(
                            machine_id, model_name
                        )
                    )
                    machine = machines[machine_id]
                else:
                    raise JujuMachineNotFound("Machine {} not found".format(machine_id))

            if machine is None:
                self.log.debug("Creating a new machine in model {}".format(model_name))

                # Create machine
                machine = await model.add_machine(
                    spec=None, constraints=None, disks=None, series=series
                )
                new = True

                # Wait until the machine is ready
                self.log.debug(
                    "Wait until machine {} is ready in model {}".format(
                        machine.entity_id, model_name
                    )
                )
                if wait:
                    await JujuModelWatcher.wait_for(
                        model=model,
                        entity=machine,
                        progress_timeout=progress_timeout,
                        total_timeout=total_timeout,
                        db_dict=db_dict,
                        n2vc=self.n2vc,
                        vca_id=self.vca_connection._vca_id,
                    )
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

        self.log.debug(
            "Machine {} ready at {} in model {}".format(
                machine.entity_id, machine.dns_name, model_name
            )
        )
        return machine, new

    async def provision_machine(
        self,
        model_name: str,
        hostname: str,
        username: str,
        private_key_path: str,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
    ) -> str:
        """
        Manually provisioning of a machine

        :param: model_name:         Model name
        :param: hostname:           IP to access the machine
        :param: username:           Username to login to the machine
        :param: private_key_path:   Local path for the private key
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active

        :return: (Entity): Machine id
        """
        self.log.debug(
            "Provisioning machine. model: {}, hostname: {}, username: {}".format(
                model_name, hostname, username
            )
        )

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        try:
            # Get provisioner
            provisioner = AsyncSSHProvisioner(
                host=hostname,
                user=username,
                private_key_path=private_key_path,
                log=self.log,
            )

            # Provision machine
            params = await provisioner.provision_machine()

            params.jobs = ["JobHostUnits"]

            self.log.debug("Adding machine to model")
            connection = model.connection()
            client_facade = client.ClientFacade.from_connection(connection)

            results = await client_facade.AddMachines(params=[params])
            error = results.machines[0].error

            if error:
                msg = "Error adding machine: {}".format(error.message)
                self.log.error(msg=msg)
                raise ValueError(msg)

            machine_id = results.machines[0].machine

            self.log.debug("Installing Juju agent into machine {}".format(machine_id))
            asyncio.ensure_future(
                provisioner.install_agent(
                    connection=connection,
                    nonce=params.nonce,
                    machine_id=machine_id,
                    proxy=self.vca_connection.data.api_proxy,
                    series=params.series,
                )
            )

            machine = None
            for _ in range(10):
                machine_list = await model.get_machines()
                if machine_id in machine_list:
                    self.log.debug("Machine {} found in model!".format(machine_id))
                    machine = model.machines.get(machine_id)
                    break
                await asyncio.sleep(2)

            if machine is None:
                msg = "Machine {} not found in model".format(machine_id)
                self.log.error(msg=msg)
                raise JujuMachineNotFound(msg)

            self.log.debug(
                "Wait until machine {} is ready in model {}".format(
                    machine.entity_id, model_name
                )
            )
            await JujuModelWatcher.wait_for(
                model=model,
                entity=machine,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
                db_dict=db_dict,
                n2vc=self.n2vc,
                vca_id=self.vca_connection._vca_id,
            )
        except Exception as e:
            raise e
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

        self.log.debug(
            "Machine provisioned {} in model {}".format(machine_id, model_name)
        )

        return machine_id

    async def deploy(
        self,
        uri: str,
        model_name: str,
        wait: bool = True,
        timeout: float = 3600,
        instantiation_params: dict = None,
    ):
        """
        Deploy bundle or charm: Similar to the juju CLI command `juju deploy`

        :param uri:            Path or Charm Store uri in which the charm or bundle can be found
        :param model_name:     Model name
        :param wait:           Indicates whether to wait or not until all applications are active
        :param timeout:        Time in seconds to wait until all applications are active
        :param instantiation_params: To be applied as overlay bundle over primary bundle.
        """
        controller = await self.get_controller()
        model = await self.get_model(controller, model_name)
        overlays = []
        try:
            await self._validate_instantiation_params(uri, model, instantiation_params)
            overlays = self._get_overlays(model_name, instantiation_params)
            await model.deploy(uri, trust=True, overlays=overlays)
            if wait:
                await JujuModelWatcher.wait_for_model(model, timeout=timeout)
                self.log.debug("All units active in model {}".format(model_name))
        finally:
            self._remove_overlay_file(overlays)
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def _validate_instantiation_params(
        self, uri: str, model, instantiation_params: dict
    ) -> None:
        """Checks if all the applications in instantiation_params
        exist ins the original bundle.

        Raises:
            JujuApplicationNotFound if there is an invalid app in
            the instantiation params.
        """
        overlay_apps = self._get_apps_in_instantiation_params(instantiation_params)
        if not overlay_apps:
            return
        original_apps = await self._get_apps_in_original_bundle(uri, model)
        if not all(app in original_apps for app in overlay_apps):
            raise JujuApplicationNotFound(
                "Cannot find application {} in original bundle {}".format(
                    overlay_apps, original_apps
                )
            )

    async def _get_apps_in_original_bundle(self, uri: str, model) -> set:
        """Bundle is downloaded in BundleHandler.fetch_plan.
        That method takes care of opening and exception handling.

        Resolve method gets all the information regarding the channel,
        track, revision, type, source.

        Returns:
            Set with the names of the applications in original bundle.
        """
        url = URL.parse(uri)
        architecture = DEFAULT_ARCHITECTURE  # only AMD64 is allowed
        res = await model.deploy_types[str(url.schema)].resolve(
            url, architecture, entity_url=uri
        )
        handler = BundleHandler(model, trusted=True, forced=False)
        await handler.fetch_plan(url, res.origin)
        return handler.applications

    def _get_apps_in_instantiation_params(self, instantiation_params: dict) -> list:
        """Extract applications key in instantiation params.

        Returns:
            List with the names of the applications in instantiation params.

        Raises:
            JujuError if applications key is not found.
        """
        if not instantiation_params:
            return []
        try:
            return [key for key in instantiation_params.get("applications")]
        except Exception as e:
            raise JujuError("Invalid overlay format. {}".format(str(e)))

    def _get_overlays(self, model_name: str, instantiation_params: dict) -> list:
        """Creates a temporary overlay file which includes the instantiation params.
        Only one overlay file is created.

        Returns:
            List with one overlay filename. Empty list if there are no instantiation params.
        """
        if not instantiation_params:
            return []
        file_name = model_name + "-overlay.yaml"
        self._write_overlay_file(file_name, instantiation_params)
        return [file_name]

    def _write_overlay_file(self, file_name: str, instantiation_params: dict) -> None:
        with open(file_name, "w") as file:
            yaml.dump(instantiation_params, file)

    def _remove_overlay_file(self, overlay: list) -> None:
        """Overlay contains either one or zero file names."""
        if not overlay:
            return
        try:
            filename = overlay[0]
            os.remove(filename)
        except OSError as e:
            self.log.warning(
                "Overlay file {} could not be removed: {}".format(filename, e)
            )

    async def add_unit(
        self,
        application_name: str,
        model_name: str,
        machine_id: str,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
    ):
        """Add unit

        :param: application_name:   Application name
        :param: model_name:         Model name
        :param: machine_id          Machine id
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active

        :return: None
        """

        model = None
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)
            application = self._get_application(model, application_name)

            if application is not None:
                # Checks if the given machine id in the model,
                # otherwise function raises an error
                _machine, _series = self._get_machine_info(model, machine_id)

                self.log.debug(
                    "Adding unit (machine {}) to application {} in model ~{}".format(
                        machine_id, application_name, model_name
                    )
                )

                await application.add_unit(to=machine_id)

                await JujuModelWatcher.wait_for(
                    model=model,
                    entity=application,
                    progress_timeout=progress_timeout,
                    total_timeout=total_timeout,
                    db_dict=db_dict,
                    n2vc=self.n2vc,
                    vca_id=self.vca_connection._vca_id,
                )
                self.log.debug(
                    "Unit is added to application {} in model {}".format(
                        application_name, model_name
                    )
                )
            else:
                raise JujuApplicationNotFound(
                    "Application {} not exists".format(application_name)
                )
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def destroy_unit(
        self,
        application_name: str,
        model_name: str,
        machine_id: str,
        total_timeout: float = None,
    ):
        """Destroy unit

        :param: application_name:   Application name
        :param: model_name:         Model name
        :param: machine_id          Machine id
        :param: total_timeout:      Timeout for the entity to be active

        :return: None
        """

        model = None
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)
            application = self._get_application(model, application_name)

            if application is None:
                raise JujuApplicationNotFound(
                    "Application not found: {} (model={})".format(
                        application_name, model_name
                    )
                )

            unit = self._get_unit(application, machine_id)
            if not unit:
                raise JujuError(
                    "A unit with machine id {} not in available units".format(
                        machine_id
                    )
                )

            unit_name = unit.name

            self.log.debug(
                "Destroying unit {} from application {} in model {}".format(
                    unit_name, application_name, model_name
                )
            )
            await application.destroy_unit(unit_name)

            self.log.debug(
                "Waiting for unit {} to be destroyed in application {} (model={})...".format(
                    unit_name, application_name, model_name
                )
            )

            # TODO: Add functionality in the Juju watcher to replace this kind of blocks
            if total_timeout is None:
                total_timeout = 3600
            end = time.time() + total_timeout
            while time.time() < end:
                if not self._get_unit(application, machine_id):
                    self.log.debug(
                        "The unit {} was destroyed in application {} (model={}) ".format(
                            unit_name, application_name, model_name
                        )
                    )
                    return
                await asyncio.sleep(5)
            self.log.debug(
                "Unit {} is destroyed from application {} in model {}".format(
                    unit_name, application_name, model_name
                )
            )
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def deploy_charm(
        self,
        application_name: str,
        path: str,
        model_name: str,
        machine_id: str,
        db_dict: dict = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        config: dict = None,
        series: str = None,
        num_units: int = 1,
    ):
        """Deploy charm

        :param: application_name:   Application name
        :param: path:               Local path to the charm
        :param: model_name:         Model name
        :param: machine_id          ID of the machine
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active
        :param: config:             Config for the charm
        :param: series:             Series of the charm
        :param: num_units:          Number of units

        :return: (juju.application.Application): Juju application
        """
        self.log.debug(
            "Deploying charm {} to machine {} in model ~{}".format(
                application_name, machine_id, model_name
            )
        )
        self.log.debug("charm: {}".format(path))

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        try:
            if application_name not in model.applications:
                if machine_id is not None:
                    machine, series = self._get_machine_info(model, machine_id)

                application = await model.deploy(
                    entity_url=path,
                    application_name=application_name,
                    channel="stable",
                    num_units=1,
                    series=series,
                    to=machine_id,
                    config=config,
                )

                self.log.debug(
                    "Wait until application {} is ready in model {}".format(
                        application_name, model_name
                    )
                )
                if num_units > 1:
                    for _ in range(num_units - 1):
                        m, _ = await self.create_machine(model_name, wait=False)
                        await application.add_unit(to=m.entity_id)

                await JujuModelWatcher.wait_for(
                    model=model,
                    entity=application,
                    progress_timeout=progress_timeout,
                    total_timeout=total_timeout,
                    db_dict=db_dict,
                    n2vc=self.n2vc,
                    vca_id=self.vca_connection._vca_id,
                )
                self.log.debug(
                    "Application {} is ready in model {}".format(
                        application_name, model_name
                    )
                )
            else:
                raise JujuApplicationExists(
                    "Application {} exists".format(application_name)
                )
        except juju.errors.JujuError as e:
            if "already exists" in e.message:
                raise JujuApplicationExists(
                    "Application {} exists".format(application_name)
                )
            else:
                raise e
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

        return application

    async def upgrade_charm(
        self,
        application_name: str,
        path: str,
        model_name: str,
        total_timeout: float = None,
        **kwargs,
    ):
        """Upgrade Charm

        :param: application_name:   Application name
        :param: model_name:         Model name
        :param: path:               Local path to the charm
        :param: total_timeout:      Timeout for the entity to be active

        :return: (str, str): (output and status)
        """

        self.log.debug(
            "Upgrading charm {} in model {} from path {}".format(
                application_name, model_name, path
            )
        )

        await self.resolve_application(
            model_name=model_name, application_name=application_name
        )

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        try:
            # Get application
            application = self._get_application(
                model,
                application_name=application_name,
            )
            if application is None:
                raise JujuApplicationNotFound(
                    "Cannot find application {} to upgrade".format(application_name)
                )

            await application.refresh(path=path)

            self.log.debug(
                "Wait until charm upgrade is completed for application {} (model={})".format(
                    application_name, model_name
                )
            )

            await JujuModelWatcher.ensure_units_idle(
                model=model, application=application
            )

            if application.status == "error":
                error_message = "Unknown"
                for unit in application.units:
                    if (
                        unit.workload_status == "error"
                        and unit.workload_status_message != ""  # pylint: disable=E1101
                    ):
                        error_message = (
                            unit.workload_status_message  # pylint: disable=E1101
                        )

                message = "Application {} failed update in {}: {}".format(
                    application_name, model_name, error_message
                )
                self.log.error(message)
                raise JujuError(message=message)

            self.log.debug(
                "Application {} is ready in model {}".format(
                    application_name, model_name
                )
            )

        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

        return application

    async def resolve_application(self, model_name: str, application_name: str):
        controller = await self.get_controller()
        model = await self.get_model(controller, model_name)

        try:
            application = self._get_application(
                model,
                application_name=application_name,
            )
            if application is None:
                raise JujuApplicationNotFound(
                    "Cannot find application {} to resolve".format(application_name)
                )

            while application.status == "error":
                for unit in application.units:
                    if unit.workload_status == "error":
                        self.log.debug(
                            "Model {}, Application {}, Unit {} in error state, resolving".format(
                                model_name, application_name, unit.entity_id
                            )
                        )
                        try:
                            await unit.resolved(retry=False)  # pylint: disable=E1101
                        except Exception:
                            pass

                await asyncio.sleep(1)

        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def resolve(self, model_name: str):
        controller = await self.get_controller()
        model = await self.get_model(controller, model_name)
        all_units_active = False
        try:
            while not all_units_active:
                all_units_active = True
                for application_name, application in model.applications.items():
                    if application.status == "error":
                        for unit in application.units:
                            if unit.workload_status == "error":
                                self.log.debug(
                                    "Model {}, Application {}, Unit {} in error state, resolving".format(
                                        model_name, application_name, unit.entity_id
                                    )
                                )
                                try:
                                    await unit.resolved(retry=False)
                                    all_units_active = False
                                except Exception:
                                    pass

                if not all_units_active:
                    await asyncio.sleep(5)
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def scale_application(
        self,
        model_name: str,
        application_name: str,
        scale: int = 1,
        total_timeout: float = None,
    ):
        """
        Scale application (K8s)

        :param: model_name:         Model name
        :param: application_name:   Application name
        :param: scale:              Scale to which to set this application
        :param: total_timeout:      Timeout for the entity to be active
        """

        model = None
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)

            self.log.debug(
                "Scaling application {} in model {}".format(
                    application_name, model_name
                )
            )
            application = self._get_application(model, application_name)
            if application is None:
                raise JujuApplicationNotFound("Cannot scale application")
            await application.scale(scale=scale)
            # Wait until application is scaled in model
            self.log.debug(
                "Waiting for application {} to be scaled in model {}...".format(
                    application_name, model_name
                )
            )
            if total_timeout is None:
                total_timeout = 1800
            end = time.time() + total_timeout
            while time.time() < end:
                application_scale = self._get_application_count(model, application_name)
                # Before calling wait_for_model function,
                # wait until application unit count and scale count are equal.
                # Because there is a delay before scaling triggers in Juju model.
                if application_scale == scale:
                    await JujuModelWatcher.wait_for_model(
                        model=model, timeout=total_timeout
                    )
                    self.log.debug(
                        "Application {} is scaled in model {}".format(
                            application_name, model_name
                        )
                    )
                    return
                await asyncio.sleep(5)
            raise Exception(
                "Timeout waiting for application {} in model {} to be scaled".format(
                    application_name, model_name
                )
            )
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    def _get_application_count(self, model: Model, application_name: str) -> int:
        """Get number of units of the application

        :param: model:              Model object
        :param: application_name:   Application name

        :return: int (or None if application doesn't exist)
        """
        application = self._get_application(model, application_name)
        if application is not None:
            return len(application.units)

    def _get_application(self, model: Model, application_name: str) -> Application:
        """Get application

        :param: model:              Model object
        :param: application_name:   Application name

        :return: juju.application.Application (or None if it doesn't exist)
        """
        if model.applications and application_name in model.applications:
            return model.applications[application_name]

    def _get_unit(self, application: Application, machine_id: str) -> Unit:
        """Get unit

        :param: application:        Application object
        :param: machine_id:         Machine id

        :return: Unit
        """
        unit = None
        for u in application.units:
            if u.machine_id == machine_id:
                unit = u
                break
        return unit

    def _get_machine_info(
        self,
        model,
        machine_id: str,
    ) -> (str, str):
        """Get machine info

        :param: model:          Model object
        :param: machine_id:     Machine id

        :return: (str, str): (machine, series)
        """
        if machine_id not in model.machines:
            msg = "Machine {} not found in model".format(machine_id)
            self.log.error(msg=msg)
            raise JujuMachineNotFound(msg)
        machine = model.machines[machine_id]
        return machine, machine.series

    async def execute_action(
        self,
        application_name: str,
        model_name: str,
        action_name: str,
        db_dict: dict = None,
        machine_id: str = None,
        progress_timeout: float = None,
        total_timeout: float = None,
        **kwargs,
    ):
        """Execute action

        :param: application_name:   Application name
        :param: model_name:         Model name
        :param: action_name:        Name of the action
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: machine_id          Machine id
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active

        :return: (str, str): (output and status)
        """
        self.log.debug(
            "Executing action {} using params {}".format(action_name, kwargs)
        )
        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        try:
            # Get application
            application = self._get_application(
                model,
                application_name=application_name,
            )
            if application is None:
                raise JujuApplicationNotFound("Cannot execute action")
            # Racing condition:
            #   Ocassionally, self._get_leader_unit() will return None
            #   because the leader elected hook has not been triggered yet.
            #   Therefore, we are doing some retries. If it happens again,
            #   re-open bug 1236
            if machine_id is None:
                unit = await self._get_leader_unit(application)
                self.log.debug(
                    "Action {} is being executed on the leader unit {}".format(
                        action_name, unit.name
                    )
                )
            else:
                unit = self._get_unit(application, machine_id)
                if not unit:
                    raise JujuError(
                        "A unit with machine id {} not in available units".format(
                            machine_id
                        )
                    )
                self.log.debug(
                    "Action {} is being executed on {} unit".format(
                        action_name, unit.name
                    )
                )

            actions = await application.get_actions()

            if action_name not in actions:
                raise JujuActionNotFound(
                    "Action {} not in available actions".format(action_name)
                )

            action = await unit.run_action(action_name, **kwargs)

            self.log.debug(
                "Wait until action {} is completed in application {} (model={})".format(
                    action_name, application_name, model_name
                )
            )
            await JujuModelWatcher.wait_for(
                model=model,
                entity=action,
                progress_timeout=progress_timeout,
                total_timeout=total_timeout,
                db_dict=db_dict,
                n2vc=self.n2vc,
                vca_id=self.vca_connection._vca_id,
            )

            output = await model.get_action_output(action_uuid=action.entity_id)
            status = await model.get_action_status(uuid_or_prefix=action.entity_id)
            status = (
                status[action.entity_id] if action.entity_id in status else "failed"
            )

            self.log.debug(
                "Action {} completed with status {} in application {} (model={})".format(
                    action_name, action.status, application_name, model_name
                )
            )
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

        return output, status

    async def get_actions(self, application_name: str, model_name: str) -> dict:
        """Get list of actions

        :param: application_name: Application name
        :param: model_name: Model name

        :return: Dict with this format
            {
                "action_name": "Description of the action",
                ...
            }
        """
        self.log.debug(
            "Getting list of actions for application {}".format(application_name)
        )

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        try:
            # Get application
            application = self._get_application(
                model,
                application_name=application_name,
            )

            # Return list of actions
            return await application.get_actions()

        finally:
            # Disconnect from model and controller
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def get_metrics(self, model_name: str, application_name: str) -> dict:
        """Get the metrics collected by the VCA.

        :param model_name The name or unique id of the network service
        :param application_name The name of the application
        """
        if not model_name or not application_name:
            raise Exception("model_name and application_name must be non-empty strings")
        metrics = {}
        controller = await self.get_controller()
        model = await self.get_model(controller, model_name)
        try:
            application = self._get_application(model, application_name)
            if application is not None:
                metrics = await application.get_metrics()
        finally:
            self.disconnect_model(model)
            self.disconnect_controller(controller)
        return metrics

    async def add_relation(
        self,
        model_name: str,
        endpoint_1: str,
        endpoint_2: str,
    ):
        """Add relation

        :param: model_name:     Model name
        :param: endpoint_1      First endpoint name
                                ("app:endpoint" format or directly the saas name)
        :param: endpoint_2:     Second endpoint name (^ same format)
        """

        self.log.debug("Adding relation: {} -> {}".format(endpoint_1, endpoint_2))

        # Get controller
        controller = await self.get_controller()

        # Get model
        model = await self.get_model(controller, model_name)

        # Add relation
        try:
            await model.add_relation(endpoint_1, endpoint_2)
        except juju.errors.JujuAPIError as e:
            if self._relation_is_not_found(e):
                self.log.warning("Relation not found: {}".format(e.message))
                return
            if self._relation_already_exist(e):
                self.log.warning("Relation already exists: {}".format(e.message))
                return
            # another exception, raise it
            raise e
        finally:
            await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    def _relation_is_not_found(self, juju_error):
        text = "not found"
        return (text in juju_error.message) or (
            juju_error.error_code and text in juju_error.error_code
        )

    def _relation_already_exist(self, juju_error):
        text = "already exists"
        return (text in juju_error.message) or (
            juju_error.error_code and text in juju_error.error_code
        )

    async def offer(self, endpoint: RelationEndpoint) -> Offer:
        """
        Create an offer from a RelationEndpoint

        :param: endpoint: Relation endpoint

        :return: Offer object
        """
        model_name = endpoint.model_name
        offer_name = f"{endpoint.application_name}-{endpoint.endpoint_name}"
        controller = await self.get_controller()
        model = None
        try:
            model = await self.get_model(controller, model_name)
            await model.create_offer(endpoint.endpoint, offer_name=offer_name)
            offer_list = await self._list_offers(model_name, offer_name=offer_name)
            if offer_list:
                return Offer(offer_list[0].offer_url)
            else:
                raise Exception("offer was not created")
        except juju.errors.JujuError as e:
            if "application offer already exists" not in e.message:
                raise e
        finally:
            if model:
                self.disconnect_model(model)
            self.disconnect_controller(controller)

    async def consume(
        self,
        model_name: str,
        offer: Offer,
        provider_libjuju: "Libjuju",
    ) -> str:
        """
        Consumes a remote offer in the model. Relations can be created later using "juju relate".

        :param: model_name:             Model name
        :param: offer:                  Offer object to consume
        :param: provider_libjuju:       Libjuju object of the provider endpoint

        :raises ParseError if there's a problem parsing the offer_url
        :raises JujuError if remote offer includes and endpoint
        :raises JujuAPIError if the operation is not successful

        :returns: Saas name. It is the application name in the model that reference the remote application.
        """
        saas_name = f'{offer.name}-{offer.model_name.replace("-", "")}'
        if offer.vca_id:
            saas_name = f"{saas_name}-{offer.vca_id}"
        controller = await self.get_controller()
        model = None
        provider_controller = None
        try:
            model = await controller.get_model(model_name)
            provider_controller = await provider_libjuju.get_controller()
            await model.consume(
                offer.url, application_alias=saas_name, controller=provider_controller
            )
            return saas_name
        finally:
            if model:
                await self.disconnect_model(model)
            if provider_controller:
                await provider_libjuju.disconnect_controller(provider_controller)
            await self.disconnect_controller(controller)

    async def destroy_model(self, model_name: str, total_timeout: float = 1800):
        """
        Destroy model

        :param: model_name:     Model name
        :param: total_timeout:  Timeout
        """

        controller = await self.get_controller()
        model = None
        try:
            if not await self.model_exists(model_name, controller=controller):
                self.log.warn(f"Model {model_name} doesn't exist")
                return

            self.log.debug(f"Getting model {model_name} to be destroyed")
            model = await self.get_model(controller, model_name)
            self.log.debug(f"Destroying manual machines in model {model_name}")
            # Destroy machines that are manually provisioned
            # and still are in pending state
            await self._destroy_pending_machines(model, only_manual=True)
            await self.disconnect_model(model)

            await asyncio.wait_for(
                self._destroy_model(model_name, controller),
                timeout=total_timeout,
            )
        except Exception as e:
            if not await self.model_exists(model_name, controller=controller):
                self.log.warn(
                    f"Failed deleting model {model_name}: model doesn't exist"
                )
                return
            self.log.warn(f"Failed deleting model {model_name}: {e}")
            raise e
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def _destroy_model(
        self,
        model_name: str,
        controller: Controller,
    ):
        """
        Destroy model from controller

        :param: model: Model name to be removed
        :param: controller: Controller object
        :param: timeout: Timeout in seconds
        """
        self.log.debug(f"Destroying model {model_name}")

        async def _destroy_model_gracefully(model_name: str, controller: Controller):
            self.log.info(f"Gracefully deleting model {model_name}")
            resolved = False
            while model_name in await controller.list_models():
                if not resolved:
                    await self.resolve(model_name)
                    resolved = True
                await controller.destroy_model(model_name, destroy_storage=True)

                await asyncio.sleep(5)
            self.log.info(f"Model {model_name} deleted gracefully")

        async def _destroy_model_forcefully(model_name: str, controller: Controller):
            self.log.info(f"Forcefully deleting model {model_name}")
            while model_name in await controller.list_models():
                await controller.destroy_model(
                    model_name, destroy_storage=True, force=True, max_wait=60
                )
                await asyncio.sleep(5)
            self.log.info(f"Model {model_name} deleted forcefully")

        try:
            try:
                await asyncio.wait_for(
                    _destroy_model_gracefully(model_name, controller), timeout=120
                )
            except asyncio.TimeoutError:
                await _destroy_model_forcefully(model_name, controller)
        except juju.errors.JujuError as e:
            if any("has been removed" in error for error in e.errors):
                return
            if any("model not found" in error for error in e.errors):
                return
            raise e

    async def destroy_application(
        self, model_name: str, application_name: str, total_timeout: float
    ):
        """
        Destroy application

        :param: model_name:         Model name
        :param: application_name:   Application name
        :param: total_timeout:      Timeout
        """

        controller = await self.get_controller()
        model = None

        try:
            model = await self.get_model(controller, model_name)
            self.log.debug(
                "Destroying application {} in model {}".format(
                    application_name, model_name
                )
            )
            application = self._get_application(model, application_name)
            if application:
                await application.destroy()
            else:
                self.log.warning("Application not found: {}".format(application_name))

            self.log.debug(
                "Waiting for application {} to be destroyed in model {}...".format(
                    application_name, model_name
                )
            )
            if total_timeout is None:
                total_timeout = 3600
            end = time.time() + total_timeout
            while time.time() < end:
                if not self._get_application(model, application_name):
                    self.log.debug(
                        "The application {} was destroyed in model {} ".format(
                            application_name, model_name
                        )
                    )
                    return
                await asyncio.sleep(5)
            raise Exception(
                "Timeout waiting for application {} to be destroyed in model {}".format(
                    application_name, model_name
                )
            )
        finally:
            if model is not None:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)

    async def _destroy_pending_machines(self, model: Model, only_manual: bool = False):
        """
        Destroy pending machines in a given model

        :param: only_manual:    Bool that indicates only manually provisioned
                                machines should be destroyed (if True), or that
                                all pending machines should be destroyed
        """
        status = await model.get_status()
        for machine_id in status.machines:
            machine_status = status.machines[machine_id]
            if machine_status.agent_status.status == "pending":
                if only_manual and not machine_status.instance_id.startswith("manual:"):
                    break
                machine = model.machines[machine_id]
                await machine.destroy(force=True)

    async def configure_application(
        self, model_name: str, application_name: str, config: dict = None
    ):
        """Configure application

        :param: model_name:         Model name
        :param: application_name:   Application name
        :param: config:             Config to apply to the charm
        """
        self.log.debug("Configuring application {}".format(application_name))

        if config:
            controller = await self.get_controller()
            model = None
            try:
                model = await self.get_model(controller, model_name)
                application = self._get_application(
                    model,
                    application_name=application_name,
                )
                await application.set_config(config)
            finally:
                if model:
                    await self.disconnect_model(model)
                await self.disconnect_controller(controller)

    async def health_check(self, interval: float = 300.0):
        """
        Health check to make sure controller and controller_model connections are OK

        :param: interval: Time in seconds between checks
        """
        controller = None
        while True:
            try:
                controller = await self.get_controller()
                # self.log.debug("VCA is alive")
            except Exception as e:
                self.log.error("Health check to VCA failed: {}".format(e))
            finally:
                await self.disconnect_controller(controller)
            await asyncio.sleep(interval)

    async def list_models(self, contains: str = None) -> [str]:
        """List models with certain names

        :param: contains:   String that is contained in model name

        :retur: [models] Returns list of model names
        """

        controller = await self.get_controller()
        try:
            models = await controller.list_models()
            if contains:
                models = [model for model in models if contains in model]
            return models
        finally:
            await self.disconnect_controller(controller)

    async def _list_offers(
        self, model_name: str, offer_name: str = None
    ) -> QueryApplicationOffersResults:
        """
        List offers within a model

        :param: model_name: Model name
        :param: offer_name: Offer name to filter.

        :return: Returns application offers results in the model
        """

        controller = await self.get_controller()
        try:
            offers = (await controller.list_offers(model_name)).results
            if offer_name:
                matching_offer = []
                for offer in offers:
                    if offer.offer_name == offer_name:
                        matching_offer.append(offer)
                        break
                offers = matching_offer
            return offers
        finally:
            await self.disconnect_controller(controller)

    async def add_k8s(
        self,
        name: str,
        rbac_id: str,
        token: str,
        client_cert_data: str,
        configuration: Configuration,
        storage_class: str,
        credential_name: str = None,
    ):
        """
        Add a Kubernetes cloud to the controller

        Similar to the `juju add-k8s` command in the CLI

        :param: name:               Name for the K8s cloud
        :param: configuration:      Kubernetes configuration object
        :param: storage_class:      Storage Class to use in the cloud
        :param: credential_name:    Storage Class to use in the cloud
        """

        if not storage_class:
            raise Exception("storage_class must be a non-empty string")
        if not name:
            raise Exception("name must be a non-empty string")
        if not configuration:
            raise Exception("configuration must be provided")

        endpoint = configuration.host
        credential = self.get_k8s_cloud_credential(
            configuration,
            client_cert_data,
            token,
        )
        credential.attrs[RBAC_LABEL_KEY_NAME] = rbac_id
        cloud = client.Cloud(
            type_="kubernetes",
            auth_types=[credential.auth_type],
            endpoint=endpoint,
            ca_certificates=[client_cert_data],
            config={
                "operator-storage": storage_class,
                "workload-storage": storage_class,
            },
        )

        return await self.add_cloud(
            name, cloud, credential, credential_name=credential_name
        )

    def get_k8s_cloud_credential(
        self,
        configuration: Configuration,
        client_cert_data: str,
        token: str = None,
    ) -> client.CloudCredential:
        attrs = {}
        # TODO: Test with AKS
        key = None  # open(configuration.key_file, "r").read()
        username = configuration.username
        password = configuration.password

        if client_cert_data:
            attrs["ClientCertificateData"] = client_cert_data
        if key:
            attrs["ClientKeyData"] = key
        if token:
            if username or password:
                raise JujuInvalidK8sConfiguration("Cannot set both token and user/pass")
            attrs["Token"] = token

        auth_type = None
        if key:
            auth_type = "oauth2"
            if client_cert_data:
                auth_type = "oauth2withcert"
            if not token:
                raise JujuInvalidK8sConfiguration(
                    "missing token for auth type {}".format(auth_type)
                )
        elif username:
            if not password:
                self.log.debug(
                    "credential for user {} has empty password".format(username)
                )
            attrs["username"] = username
            attrs["password"] = password
            if client_cert_data:
                auth_type = "userpasswithcert"
            else:
                auth_type = "userpass"
        elif client_cert_data and token:
            auth_type = "certificate"
        else:
            raise JujuInvalidK8sConfiguration("authentication method not supported")
        return client.CloudCredential(auth_type=auth_type, attrs=attrs)

    async def add_cloud(
        self,
        name: str,
        cloud: Cloud,
        credential: CloudCredential = None,
        credential_name: str = None,
    ) -> Cloud:
        """
        Add cloud to the controller

        :param: name:               Name of the cloud to be added
        :param: cloud:              Cloud object
        :param: credential:         CloudCredentials object for the cloud
        :param: credential_name:    Credential name.
                                    If not defined, cloud of the name will be used.
        """
        controller = await self.get_controller()
        try:
            _ = await controller.add_cloud(name, cloud)
            if credential:
                await controller.add_credential(
                    credential_name or name, credential=credential, cloud=name
                )
            # Need to return the object returned by the controller.add_cloud() function
            # I'm returning the original value now until this bug is fixed:
            #   https://github.com/juju/python-libjuju/issues/443
            return cloud
        finally:
            await self.disconnect_controller(controller)

    async def remove_cloud(self, name: str):
        """
        Remove cloud

        :param: name:   Name of the cloud to be removed
        """
        controller = await self.get_controller()
        try:
            await controller.remove_cloud(name)
        except juju.errors.JujuError as e:
            if len(e.errors) == 1 and f'cloud "{name}" not found' == e.errors[0]:
                self.log.warning(f"Cloud {name} not found, so it could not be deleted.")
            else:
                raise e
        finally:
            await self.disconnect_controller(controller)

    @retry(
        attempts=20, delay=5, fallback=JujuLeaderUnitNotFound(), callback=retry_callback
    )
    async def _get_leader_unit(self, application: Application) -> Unit:
        unit = None
        for u in application.units:
            if await u.is_leader_from_status():
                unit = u
                break
        if not unit:
            raise Exception()
        return unit

    async def get_cloud_credentials(self, cloud: Cloud) -> typing.List:
        """
        Get cloud credentials

        :param: cloud: Cloud object. The returned credentials will be from this cloud.

        :return: List of credentials object associated to the specified cloud

        """
        controller = await self.get_controller()
        try:
            facade = client.CloudFacade.from_connection(controller.connection())
            cloud_cred_tag = tag.credential(
                cloud.name, self.vca_connection.data.user, cloud.credential_name
            )
            params = [client.Entity(cloud_cred_tag)]
            return (await facade.Credential(params)).results
        finally:
            await self.disconnect_controller(controller)

    async def check_application_exists(self, model_name, application_name) -> bool:
        """Check application exists

        :param: model_name:         Model Name
        :param: application_name:   Application Name

        :return: Boolean
        """

        model = None
        controller = await self.get_controller()
        try:
            model = await self.get_model(controller, model_name)
            self.log.debug(
                "Checking if application {} exists in model {}".format(
                    application_name, model_name
                )
            )
            return self._get_application(model, application_name) is not None
        finally:
            if model:
                await self.disconnect_model(model)
            await self.disconnect_controller(controller)
