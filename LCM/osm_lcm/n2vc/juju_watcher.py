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
import time

from juju.client import client
from osm_lcm.n2vc.exceptions import EntityInvalidException
from osm_lcm.n2vc.n2vc_conn import N2VCConnector
from juju.model import ModelEntity, Model
from juju.client.overrides import Delta
from juju.status import derive_status
from juju.application import Application
from websockets.exceptions import ConnectionClosed
import logging

logger = logging.getLogger("__main__")


def status(application: Application) -> str:
    unit_status = []
    for unit in application.units:
        unit_status.append(unit.workload_status)
    return derive_status(unit_status)


def entity_ready(entity: ModelEntity) -> bool:
    """
    Check if the entity is ready

    :param: entity: Model entity. It can be a machine, action, or application.

    :returns: boolean saying if the entity is ready or not
    """

    entity_type = entity.entity_type
    if entity_type == "machine":
        return entity.agent_status in ["started"]
    elif entity_type == "action":
        return entity.status in ["completed", "failed", "cancelled"]
    elif entity_type == "application":
        # Workaround for bug: https://github.com/juju/python-libjuju/issues/441
        return entity.status in ["active", "blocked"]
    elif entity_type == "unit":
        return entity.agent_status in ["idle"]
    else:
        raise EntityInvalidException("Unknown entity type: {}".format(entity_type))


def application_ready(application: Application) -> bool:
    """
    Check if an application has a leader

    :param: application: Application entity.

    :returns: boolean saying if the application has a unit that is a leader.
    """
    ready_status_list = ["active", "blocked"]
    application_ready = application.status in ready_status_list
    units_ready = all(
        unit.workload_status in ready_status_list for unit in application.units
    )
    return application_ready and units_ready


class JujuModelWatcher:
    @staticmethod
    async def wait_for_model(model: Model, timeout: float = 3600):
        """
        Wait for all entities in model to reach its final state.

        :param: model:              Model to observe
        :param: timeout:            Timeout for the model applications to be active

        :raises: asyncio.TimeoutError when timeout reaches
        """

        if timeout is None:
            timeout = 3600.0

        # Coroutine to wait until the entity reaches the final state
        async def wait_until_model_ready():
            wait_for_entity = asyncio.ensure_future(
                asyncio.wait_for(
                    model.block_until(
                        lambda: all(
                            application_ready(application)
                            for application in model.applications.values()
                        ),
                    ),
                    timeout=timeout,
                )
            )

            tasks = [wait_for_entity]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                # Cancel tasks
                for task in tasks:
                    task.cancel()

        await wait_until_model_ready()
        # Check model is still ready after 10 seconds

        await asyncio.sleep(10)
        await wait_until_model_ready()

    @staticmethod
    async def wait_for(
        model: Model,
        entity: ModelEntity,
        progress_timeout: float = 3600,
        total_timeout: float = 3600,
        db_dict: dict = None,
        n2vc: N2VCConnector = None,
        vca_id: str = None,
    ):
        """
        Wait for entity to reach its final state.

        :param: model:              Model to observe
        :param: entity:             Entity object
        :param: progress_timeout:   Maximum time between two updates in the model
        :param: total_timeout:      Timeout for the entity to be active
        :param: db_dict:            Dictionary with data of the DB to write the updates
        :param: n2vc:               N2VC Connector objector
        :param: vca_id:             VCA ID

        :raises: asyncio.TimeoutError when timeout reaches
        """

        if progress_timeout is None:
            progress_timeout = 3600.0
        if total_timeout is None:
            total_timeout = 3600.0

        entity_type = entity.entity_type
        if entity_type not in ["application", "action", "machine", "unit"]:
            raise EntityInvalidException("Unknown entity type: {}".format(entity_type))

        # Coroutine to wait until the entity reaches the final state
        wait_for_entity = asyncio.ensure_future(
            asyncio.wait_for(
                model.block_until(lambda: entity_ready(entity)),
                timeout=total_timeout,
            )
        )

        # Coroutine to watch the model for changes (and write them to DB)
        watcher = asyncio.ensure_future(
            JujuModelWatcher.model_watcher(
                model,
                entity_id=entity.entity_id,
                entity_type=entity_type,
                timeout=progress_timeout,
                db_dict=db_dict,
                n2vc=n2vc,
                vca_id=vca_id,
            )
        )

        tasks = [wait_for_entity, watcher]
        try:
            # Execute tasks, and stop when the first is finished
            # The watcher task won't never finish (unless it timeouts)
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            # Cancel tasks
            for task in tasks:
                task.cancel()

    @staticmethod
    async def wait_for_units_idle(
        model: Model, application: Application, timeout: float = 60
    ):
        """
        Waits for the application and all its units to transition back to idle

        :param: model:          Model to observe
        :param: application:    The application to be observed
        :param: timeout:        Maximum time between two updates in the model

        :raises: asyncio.TimeoutError when timeout reaches
        """

        ensure_units_idle = asyncio.ensure_future(
            asyncio.wait_for(
                JujuModelWatcher.ensure_units_idle(model, application), timeout
            )
        )
        tasks = [
            ensure_units_idle,
        ]
        (done, pending) = await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )

        if ensure_units_idle in pending:
            ensure_units_idle.cancel()
            raise TimeoutError(
                "Application's units failed to return to idle after {} seconds".format(
                    timeout
                )
            )
        if ensure_units_idle.result():
            pass

    @staticmethod
    async def ensure_units_idle(model: Model, application: Application):
        """
        Waits forever until the application's units to transition back to idle

        :param: model:          Model to observe
        :param: application:    The application to be observed
        """

        try:
            allwatcher = client.AllWatcherFacade.from_connection(model.connection())
            unit_wanted_state = "executing"
            final_state_reached = False

            units = application.units
            final_state_seen = {unit.entity_id: False for unit in units}
            agent_state_seen = {unit.entity_id: False for unit in units}
            workload_state = {unit.entity_id: False for unit in units}

            try:
                while not final_state_reached:
                    change = await allwatcher.Next()

                    # Keep checking to see if new units were added during the change
                    for unit in units:
                        if unit.entity_id not in final_state_seen:
                            final_state_seen[unit.entity_id] = False
                            agent_state_seen[unit.entity_id] = False
                            workload_state[unit.entity_id] = False

                    for delta in change.deltas:
                        await asyncio.sleep(0)
                        if delta.entity != units[0].entity_type:
                            continue

                        final_state_reached = True
                        for unit in units:
                            if delta.data["name"] == unit.entity_id:
                                status = delta.data["agent-status"]["current"]
                                workload_state[unit.entity_id] = delta.data[
                                    "workload-status"
                                ]["current"]

                                if status == unit_wanted_state:
                                    agent_state_seen[unit.entity_id] = True
                                    final_state_seen[unit.entity_id] = False

                                if (
                                    status == "idle"
                                    and agent_state_seen[unit.entity_id]
                                ):
                                    final_state_seen[unit.entity_id] = True

                            final_state_reached = (
                                final_state_reached
                                and final_state_seen[unit.entity_id]
                                and workload_state[unit.entity_id]
                                in [
                                    "active",
                                    "error",
                                ]
                            )

            except ConnectionClosed:
                pass
                # This is expected to happen when the
                # entity reaches its final state, because
                # the model connection is closed afterwards
        except Exception as e:
            raise e

    @staticmethod
    async def model_watcher(
        model: Model,
        entity_id: str,
        entity_type: str,
        timeout: float,
        db_dict: dict = None,
        n2vc: N2VCConnector = None,
        vca_id: str = None,
    ):
        """
        Observes the changes related to an specific entity in a model

        :param: model:          Model to observe
        :param: entity_id:      ID of the entity to be observed
        :param: entity_type:    Entity Type (p.e. "application", "machine, and "action")
        :param: timeout:        Maximum time between two updates in the model
        :param: db_dict:        Dictionary with data of the DB to write the updates
        :param: n2vc:           N2VC Connector objector
        :param: vca_id:         VCA ID

        :raises: asyncio.TimeoutError when timeout reaches
        """

        try:
            allwatcher = client.AllWatcherFacade.from_connection(model.connection())

            # Genenerate array with entity types to listen
            entity_types = (
                [entity_type, "unit"]
                if entity_type == "application"  # TODO: Add "action" too
                else [entity_type]
            )

            # Get time when it should timeout
            timeout_end = time.time() + timeout

            try:
                while True:
                    change = await allwatcher.Next()
                    for delta in change.deltas:
                        write = False
                        delta_entity = None

                        # Get delta EntityType
                        delta_entity = delta.entity

                        if delta_entity in entity_types:
                            # Get entity id
                            id = None
                            if entity_type == "application":
                                id = (
                                    delta.data["application"]
                                    if delta_entity == "unit"
                                    else delta.data["name"]
                                )
                            else:
                                if "id" in delta.data:
                                    id = delta.data["id"]
                                else:
                                    print("No id {}".format(delta.data))

                            # Write if the entity id match
                            write = True if id == entity_id else False

                            # Update timeout
                            timeout_end = time.time() + timeout
                            (
                                status,
                                status_message,
                                vca_status,
                            ) = JujuModelWatcher.get_status(delta)

                            if write and n2vc is not None and db_dict:
                                # Write status to DB
                                status = n2vc.osm_status(delta_entity, status)
                                await n2vc.write_app_status_to_db(
                                    db_dict=db_dict,
                                    status=status,
                                    detailed_status=status_message,
                                    vca_status=vca_status,
                                    entity_type=delta_entity,
                                    vca_id=vca_id,
                                )
                    # Check if timeout
                    if time.time() > timeout_end:
                        raise asyncio.TimeoutError()
            except ConnectionClosed:
                pass
                # This is expected to happen when the
                # entity reaches its final state, because
                # the model connection is closed afterwards
        except Exception as e:
            raise e

    @staticmethod
    def get_status(delta: Delta) -> (str, str, str):
        """
        Get status from delta

        :param: delta:          Delta generated by the allwatcher
        :param: entity_type:    Entity Type (p.e. "application", "machine, and "action")

        :return (status, message, vca_status)
        """
        if delta.entity == "machine":
            return (
                delta.data["agent-status"]["current"],
                delta.data["instance-status"]["message"],
                delta.data["instance-status"]["current"],
            )
        elif delta.entity == "action":
            return (
                delta.data["status"],
                delta.data["status"],
                delta.data["status"],
            )
        elif delta.entity == "application":
            return (
                delta.data["status"]["current"],
                delta.data["status"]["message"],
                delta.data["status"]["current"],
            )
        elif delta.entity == "unit":
            return (
                delta.data["workload-status"]["current"],
                delta.data["workload-status"]["message"],
                delta.data["workload-status"]["current"],
            )
