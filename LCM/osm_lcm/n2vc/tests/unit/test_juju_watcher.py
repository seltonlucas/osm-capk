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

import json
import os
from time import sleep
import asynctest
import asyncio

from osm_lcm.n2vc.juju_watcher import JujuModelWatcher, entity_ready, status
from osm_lcm.n2vc.exceptions import EntityInvalidException
from .utils import FakeN2VC, AsyncMock, Deltas, FakeWatcher
from juju.application import Application
from juju.action import Action
from juju.annotation import Annotation
from juju.client._definitions import AllWatcherNextResults
from juju.machine import Machine
from juju.model import Model
from juju.unit import Unit
from unittest import mock, TestCase
from unittest.mock import Mock


class JujuWatcherTest(asynctest.TestCase):
    def setUp(self):
        self.n2vc = FakeN2VC()
        self.model = Mock()
        self.loop = asyncio.new_event_loop()

    def test_get_status(self):
        tests = Deltas
        for test in tests:
            (status, message, vca_status) = JujuModelWatcher.get_status(test.delta)
            self.assertEqual(status, test.entity_status.status)
            self.assertEqual(message, test.entity_status.message)
            self.assertEqual(vca_status, test.entity_status.vca_status)

    @mock.patch("osm_lcm.n2vc.juju_watcher.client.AllWatcherFacade.from_connection")
    def test_model_watcher(self, allwatcher):
        tests = Deltas
        allwatcher.return_value = FakeWatcher()
        n2vc = AsyncMock()
        for test in tests:
            with self.assertRaises(asyncio.TimeoutError):
                allwatcher.return_value.delta_to_return = [test.delta]
                self.loop.run_until_complete(
                    JujuModelWatcher.model_watcher(
                        self.model,
                        test.filter.entity_id,
                        test.filter.entity_type,
                        timeout=0,
                        db_dict={"something"},
                        n2vc=n2vc,
                        vca_id=None,
                    )
                )

            n2vc.write_app_status_to_db.assert_called()

    @mock.patch("osm_lcm.n2vc.juju_watcher.asyncio.wait")
    def test_wait_for(self, wait):
        wait.return_value = asyncio.Future()
        wait.return_value.set_result(None)

        machine = AsyncMock()
        self.loop.run_until_complete(JujuModelWatcher.wait_for(self.model, machine))

    @mock.patch("osm_lcm.n2vc.juju_watcher.asyncio.wait")
    def test_wait_for_exception(self, wait):
        wait.return_value = asyncio.Future()
        wait.return_value.set_result(None)
        wait.side_effect = Exception("error")

        machine = AsyncMock()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(JujuModelWatcher.wait_for(self.model, machine))

    def test_wait_for_invalid_entity_exception(self):
        with self.assertRaises(EntityInvalidException):
            self.loop.run_until_complete(
                JujuModelWatcher.wait_for(
                    self.model,
                    Annotation(0, self.model),
                    total_timeout=None,
                    progress_timeout=None,
                )
            )


class EntityReadyTest(TestCase):
    @mock.patch("juju.application.Application.units")
    def setUp(self, mock_units):
        self.model = Model()
        self.model._connector = mock.MagicMock()

    def test_invalid_entity(self):
        with self.assertRaises(EntityInvalidException):
            entity_ready(Annotation(0, self.model))

    @mock.patch("juju.machine.Machine.agent_status")
    def test_machine_entity(self, mock_machine_agent_status):
        entity = Machine(0, self.model)
        self.assertEqual(entity.entity_type, "machine")
        self.assertTrue(isinstance(entity_ready(entity), bool))

    @mock.patch("juju.action.Action.status")
    def test_action_entity(self, mock_action_status):
        entity = Action(0, self.model)
        self.assertEqual(entity.entity_type, "action")
        self.assertTrue(isinstance(entity_ready(entity), bool))

    @mock.patch("juju.application.Application.status")
    def test_application_entity(self, mock_application_status):
        entity = Application(0, self.model)
        self.assertEqual(entity.entity_type, "application")
        self.assertTrue(isinstance(entity_ready(entity), bool))


@mock.patch("osm_lcm.n2vc.juju_watcher.client.AllWatcherFacade.from_connection")
class EntityStateTest(TestCase):
    def setUp(self):
        self.model = Model()
        self.model._connector = mock.MagicMock()
        self.loop = asyncio.new_event_loop()
        self.application = Mock(Application)
        self.upgrade_file = None
        self.line_number = 1

    def _fetch_next_delta(self):
        delta = None
        while delta is None:
            raw_data = self.upgrade_file.readline()
            if not raw_data:
                raise EOFError("Log file is out of events")
            try:
                delta = json.loads(raw_data)
            except ValueError:
                continue

        if delta[0] == "unit":
            if delta[2]["life"] == "dead":
                # Remove the unit from the application
                for unit in self.application.units:
                    if unit.entity_id == delta[2]["name"]:
                        self.application.units.remove(unit)
            else:
                unit_present = False
                for unit in self.application.units:
                    if unit.entity_id == delta[2]["name"]:
                        unit_present = True

                if not unit_present:
                    print("Application gets a new unit: {}".format(delta[2]["name"]))
                    unit = Mock(Unit)
                    unit.entity_id = delta[2]["name"]
                    unit.entity_type = "unit"
                    self.application.units.append(unit)

        print("{}  {}".format(self.line_number, delta))
        self.line_number = self.line_number + 1

        return AllWatcherNextResults(
            deltas=[
                delta,
            ]
        )

    def _ensure_state(self, filename, mock_all_watcher):
        with open(
            os.path.join(os.path.dirname(__file__), "testdata", filename),
            "r",
        ) as self.upgrade_file:
            all_changes = AsyncMock()
            all_changes.Next.side_effect = self._fetch_next_delta
            mock_all_watcher.return_value = all_changes

            self.loop.run_until_complete(
                JujuModelWatcher.ensure_units_idle(
                    model=self.model, application=self.application
                )
            )

            with self.assertRaises(EOFError, msg="Not all events consumed"):
                change = self._fetch_next_delta()
                print(change.deltas[0].deltas)

    def _slow_changes(self):
        sleep(0.1)
        return AllWatcherNextResults(
            deltas=[
                json.loads(
                    """["unit","change",
                {
                    "name": "app-vnf-7a49ace2b6-z0/2",
                    "application": "app-vnf-7a49ace2b6-z0",
                    "workload-status": {
                        "current": "active",
                        "message": "",
                        "since": "2022-04-26T18:50:27.579802723Z"},
                    "agent-status": {
                        "current": "idle",
                        "message": "",
                        "since": "2022-04-26T18:50:28.592142816Z"}
                }]"""
                ),
            ]
        )

    def test_timeout(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "app-vnf-7a49ace2b6-z0/0"
        unit1.entity_type = "unit"
        self.application.units = [
            unit1,
        ]

        all_changes = AsyncMock()
        all_changes.Next.side_effect = self._slow_changes
        mock_all_watcher.return_value = all_changes

        with self.assertRaises(TimeoutError):
            self.loop.run_until_complete(
                JujuModelWatcher.wait_for_units_idle(
                    model=self.model, application=self.application, timeout=0.01
                )
            )

    def test_machine_unit_upgrade(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "app-vnf-7a49ace2b6-z0/0"
        unit1.entity_type = "unit"
        unit2 = Mock(Unit)
        unit2.entity_id = "app-vnf-7a49ace2b6-z0/1"
        unit2.entity_type = "unit"
        unit3 = Mock(Unit)
        unit3.entity_id = "app-vnf-7a49ace2b6-z0/2"
        unit3.entity_type = "unit"

        self.application.units = [unit1, unit2, unit3]

        self._ensure_state("upgrade-machine.log", mock_all_watcher)

    def test_operator_upgrade(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "sshproxy/0"
        unit1.entity_type = "unit"
        self.application.units = [
            unit1,
        ]
        self._ensure_state("upgrade-operator.log", mock_all_watcher)

    def test_podspec_stateful_upgrade(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "mongodb/0"
        unit1.entity_type = "unit"
        self.application.units = [
            unit1,
        ]
        self._ensure_state("upgrade-podspec-stateful.log", mock_all_watcher)

    def test_podspec_stateless_upgrade(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "lcm/9"
        unit1.entity_type = "unit"
        self.application.units = [
            unit1,
        ]
        self._ensure_state("upgrade-podspec-stateless.log", mock_all_watcher)

    def test_sidecar_upgrade(self, mock_all_watcher):
        unit1 = Mock(Unit)
        unit1.entity_id = "kafka/0"
        unit1.entity_type = "unit"
        self.application.units = [
            unit1,
        ]
        self._ensure_state("upgrade-sidecar.log", mock_all_watcher)


class StatusTest(TestCase):
    def setUp(self):
        self.model = Model()
        self.model._connector = mock.MagicMock()

    @mock.patch("osm_lcm.n2vc.juju_watcher.derive_status")
    def test_invalid_entity(self, mock_derive_status):
        application = mock.MagicMock()
        mock_derive_status.return_value = "active"

        class FakeUnit:
            @property
            def workload_status(self):
                return "active"

        application.units = [FakeUnit()]
        value = status(application)
        mock_derive_status.assert_called_once()
        self.assertTrue(isinstance(value, str))


@asynctest.mock.patch("asyncio.sleep")
class WaitForModelTest(asynctest.TestCase):
    @asynctest.mock.patch("juju.client.connector.Connector.connect")
    def setUp(self, mock_connect=None):
        self.loop = asyncio.new_event_loop()
        self.model = Model()

    @asynctest.mock.patch("juju.model.Model.block_until")
    def test_wait_for_model(self, mock_block_until, mock_sleep):
        self.loop.run_until_complete(
            JujuModelWatcher.wait_for_model(self.model, timeout=None)
        )
        mock_block_until.assert_called()

    @asynctest.mock.patch("asyncio.ensure_future")
    @asynctest.mock.patch("asyncio.wait")
    def test_wait_for_model_exception(self, mock_wait, mock_ensure_future, mock_sleep):
        task = Mock()
        mock_ensure_future.return_value = task
        mock_wait.side_effect = Exception
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                JujuModelWatcher.wait_for_model(self.model, timeout=None)
            )
        task.cancel.assert_called()
