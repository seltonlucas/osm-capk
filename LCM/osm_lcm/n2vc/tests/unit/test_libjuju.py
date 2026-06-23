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
import asynctest
import tempfile
from unittest.mock import Mock, patch
import juju
import kubernetes
from juju.errors import JujuAPIError
import logging

from osm_lcm.n2vc.definitions import Offer, RelationEndpoint
from .utils import (
    FakeApplication,
    FakeMachine,
    FakeManualMachine,
    FakeUnit,
)
from osm_lcm.n2vc.libjuju import Libjuju
from osm_lcm.n2vc.exceptions import (
    JujuControllerFailedConnecting,
    JujuMachineNotFound,
    JujuApplicationNotFound,
    JujuActionNotFound,
    JujuApplicationExists,
    JujuInvalidK8sConfiguration,
    JujuLeaderUnitNotFound,
    JujuError,
)
from osm_lcm.n2vc.k8s_juju_conn import generate_rbac_id
from osm_lcm.n2vc.tests.unit.utils import AsyncMock
from osm_lcm.n2vc.vca.connection import Connection
from osm_lcm.n2vc.vca.connection_data import ConnectionData


cacert = """-----BEGIN CERTIFICATE-----
SOMECERT
-----END CERTIFICATE-----"""


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Controller")
class LibjujuTestCase(asynctest.TestCase):
    @asynctest.mock.patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def setUp(
        self,
        mock_base64_to_cacert=None,
    ):
        self.loop = asyncio.get_event_loop()
        self.db = Mock()
        mock_base64_to_cacert.return_value = cacert
        # Connection._load_vca_connection_data = Mock()
        vca_connection = Connection(AsyncMock())
        vca_connection._data = ConnectionData(
            **{
                "endpoints": ["1.2.3.4:17070"],
                "user": "user",
                "secret": "secret",
                "cacert": "cacert",
                "pubkey": "pubkey",
                "lxd-cloud": "cloud",
                "lxd-credentials": "credentials",
                "k8s-cloud": "k8s_cloud",
                "k8s-credentials": "k8s_credentials",
                "model-config": {},
                "api-proxy": "api_proxy",
            }
        )
        logging.disable(logging.CRITICAL)
        self.libjuju = Libjuju(vca_connection)
        self.loop.run_until_complete(self.libjuju.disconnect())


@asynctest.mock.patch("juju.controller.Controller.connect")
@asynctest.mock.patch(
    "juju.controller.Controller.api_endpoints",
    new_callable=asynctest.CoroutineMock(return_value=["127.0.0.1:17070"]),
)
class GetControllerTest(LibjujuTestCase):
    def setUp(self):
        super(GetControllerTest, self).setUp()

    def test_diff_endpoint(self, mock_api_endpoints, mock_connect):
        self.libjuju.endpoints = []
        controller = self.loop.run_until_complete(self.libjuju.get_controller())
        self.assertIsInstance(controller, juju.controller.Controller)

    @asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
    def test_exception(
        self,
        mock_disconnect_controller,
        mock_api_endpoints,
        mock_connect,
    ):
        self.libjuju.endpoints = []

        mock_connect.side_effect = Exception()
        controller = None
        with self.assertRaises(JujuControllerFailedConnecting):
            controller = self.loop.run_until_complete(self.libjuju.get_controller())
        self.assertIsNone(controller)
        mock_disconnect_controller.assert_called()

    def test_same_endpoint_get_controller(self, mock_api_endpoints, mock_connect):
        self.libjuju.endpoints = ["127.0.0.1:17070"]
        controller = self.loop.run_until_complete(self.libjuju.get_controller())
        self.assertIsInstance(controller, juju.controller.Controller)


class DisconnectTest(LibjujuTestCase):
    def setUp(self):
        super(DisconnectTest, self).setUp()

    @asynctest.mock.patch("juju.model.Model.disconnect")
    def test_disconnect_model(self, mock_disconnect):
        self.loop.run_until_complete(self.libjuju.disconnect_model(juju.model.Model()))
        mock_disconnect.assert_called_once()

    @asynctest.mock.patch("juju.controller.Controller.disconnect")
    def test_disconnect_controller(self, mock_disconnect):
        self.loop.run_until_complete(
            self.libjuju.disconnect_controller(juju.controller.Controller())
        )
        mock_disconnect.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.model_exists")
@asynctest.mock.patch("juju.controller.Controller.add_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
class AddModelTest(LibjujuTestCase):
    def setUp(self):
        super(AddModelTest, self).setUp()

    def test_existing_model(
        self,
        mock_disconnect_model,
        mock_disconnect_controller,
        mock_add_model,
        mock_model_exists,
        mock_get_controller,
    ):
        mock_model_exists.return_value = True

        # This should not raise an exception
        self.loop.run_until_complete(self.libjuju.add_model("existing_model", "cloud"))

        mock_disconnect_controller.assert_called()

    # TODO Check two job executing at the same time and one returning without doing anything.

    def test_non_existing_model(
        self,
        mock_disconnect_model,
        mock_disconnect_controller,
        mock_add_model,
        mock_model_exists,
        mock_get_controller,
    ):
        mock_model_exists.return_value = False
        mock_get_controller.return_value = juju.controller.Controller()

        self.loop.run_until_complete(
            self.libjuju.add_model("nonexisting_model", Mock())
        )

        mock_add_model.assert_called_once()
        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch(
    "juju.model.Model.applications", new_callable=asynctest.PropertyMock
)
@asynctest.mock.patch("juju.model.Model.get_action_status")
@asynctest.mock.patch("juju.model.Model.get_action_output")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_actions")
class GetExecutedActionsTest(LibjujuTestCase):
    def setUp(self):
        super(GetExecutedActionsTest, self).setUp()

    def test_exception(
        self,
        mock_get_actions,
        mock_get_action_output,
        mock_get_action_status,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = None
        with self.assertRaises(JujuError):
            self.loop.run_until_complete(self.libjuju.get_executed_actions("model"))

        mock_get_controller.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_model.assert_not_called()

    def test_success(
        self,
        mock_get_actions,
        mock_get_action_output,
        mock_get_action_status,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_applications.return_value = {"existing_app"}
        mock_get_actions.return_value = {"action_name": "description"}
        mock_get_action_status.return_value = {"id": "status"}
        mock_get_action_output.return_value = {"output": "completed"}

        executed_actions = self.loop.run_until_complete(
            self.libjuju.get_executed_actions("model")
        )
        expected_result = [
            {
                "id": "id",
                "action": "action_name",
                "status": "status",
                "output": "completed",
            }
        ]
        self.assertListEqual(expected_result, executed_actions)
        self.assertIsInstance(executed_actions, list)

        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class GetApplicationConfigsTest(LibjujuTestCase):
    def setUp(self):
        super(GetApplicationConfigsTest, self).setUp()

    def test_exception(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = None
        with self.assertRaises(JujuError):
            self.loop.run_until_complete(
                self.libjuju.get_application_configs("model", "app")
            )

        mock_get_controller.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_model.assert_not_called()

    def test_success(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.return_value = FakeApplication()
        application_configs = self.loop.run_until_complete(
            self.libjuju.get_application_configs("model", "app")
        )

        self.assertEqual(application_configs, ["app_config"])

        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


@asynctest.mock.patch("juju.controller.Controller.get_model")
class GetModelTest(LibjujuTestCase):
    def setUp(self):
        super(GetModelTest, self).setUp()

    def test_get_model(
        self,
        mock_get_model,
    ):
        mock_get_model.return_value = juju.model.Model()
        model = self.loop.run_until_complete(
            self.libjuju.get_model(juju.controller.Controller(), "model")
        )
        self.assertIsInstance(model, juju.model.Model)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("juju.controller.Controller.list_models")
class ModelExistsTest(LibjujuTestCase):
    def setUp(self):
        super(ModelExistsTest, self).setUp()

    async def test_existing_model(
        self,
        mock_list_models,
        mock_get_controller,
    ):
        mock_list_models.return_value = ["existing_model"]
        self.assertTrue(
            await self.libjuju.model_exists(
                "existing_model", juju.controller.Controller()
            )
        )

    @asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
    async def test_no_controller(
        self,
        mock_disconnect_controller,
        mock_list_models,
        mock_get_controller,
    ):
        mock_list_models.return_value = ["existing_model"]
        mock_get_controller.return_value = juju.controller.Controller()
        self.assertTrue(await self.libjuju.model_exists("existing_model"))
        mock_disconnect_controller.assert_called_once()

    async def test_non_existing_model(
        self,
        mock_list_models,
        mock_get_controller,
    ):
        mock_list_models.return_value = ["existing_model"]
        self.assertFalse(
            await self.libjuju.model_exists(
                "not_existing_model", juju.controller.Controller()
            )
        )


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.model.Model.get_status")
class GetModelStatusTest(LibjujuTestCase):
    def setUp(self):
        super(GetModelStatusTest, self).setUp()

    def test_success(
        self,
        mock_get_status,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_status.return_value = {"status"}

        status = self.loop.run_until_complete(self.libjuju.get_model_status("model"))

        mock_get_status.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

        self.assertEqual(status, {"status"})

    def test_exception(
        self,
        mock_get_status,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_status.side_effect = Exception()
        status = None
        with self.assertRaises(Exception):
            status = self.loop.run_until_complete(
                self.libjuju.get_model_status("model")
            )

        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

        self.assertIsNone(status)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.model.Model.get_machines")
@asynctest.mock.patch("juju.model.Model.add_machine")
@asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for")
class CreateMachineTest(LibjujuTestCase):
    def setUp(self):
        super(CreateMachineTest, self).setUp()

    def test_existing_machine(
        self,
        mock_wait_for,
        mock_add_machine,
        mock_get_machines,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_machines.return_value = {"existing_machine": FakeMachine()}
        machine, bool_res = self.loop.run_until_complete(
            self.libjuju.create_machine("model", "existing_machine")
        )

        self.assertIsInstance(machine, FakeMachine)
        self.assertFalse(bool_res)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_non_existing_machine(
        self,
        mock_wait_for,
        mock_add_machine,
        mock_get_machines,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        machine = None
        bool_res = None
        mock_get_model.return_value = juju.model.Model()
        with self.assertRaises(JujuMachineNotFound):
            machine, bool_res = self.loop.run_until_complete(
                self.libjuju.create_machine("model", "non_existing_machine")
            )
        self.assertIsNone(machine)
        self.assertIsNone(bool_res)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_no_machine(
        self,
        mock_wait_for,
        mock_add_machine,
        mock_get_machines,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_add_machine.return_value = FakeMachine()

        machine, bool_res = self.loop.run_until_complete(
            self.libjuju.create_machine("model")
        )

        self.assertIsInstance(machine, FakeMachine)
        self.assertTrue(bool_res)

        mock_wait_for.assert_called_once()
        mock_add_machine.assert_called_once()

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()


# TODO test provision machine


@asynctest.mock.patch("os.remove")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.yaml.dump")
@asynctest.mock.patch("builtins.open", create=True)
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for_model")
@asynctest.mock.patch("juju.model.Model.deploy")
@asynctest.mock.patch("juju.model.CharmhubDeployType.resolve")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.BundleHandler")
@asynctest.mock.patch("juju.url.URL.parse")
class DeployTest(LibjujuTestCase):
    def setUp(self):
        super(DeployTest, self).setUp()
        self.instantiation_params = {"applications": {"squid": {"scale": 2}}}
        self.architecture = "amd64"
        self.uri = "cs:osm"
        self.url = AsyncMock()
        self.url.schema = juju.url.Schema.CHARM_HUB
        self.bundle_instance = None

    def setup_bundle_download_mocks(
        self, mock_url_parse, mock_bundle, mock_resolve, mock_get_model
    ):
        mock_url_parse.return_value = self.url
        mock_bundle.return_value = AsyncMock()
        mock_resolve.return_value = AsyncMock()
        mock_resolve.origin = AsyncMock()
        mock_get_model.return_value = juju.model.Model()
        self.bundle_instance = mock_bundle.return_value
        self.bundle_instance.applications = {"squid"}

    def assert_overlay_file_is_written(self, filename, mocked_file, mock_yaml, mock_os):
        mocked_file.assert_called_once_with(filename, "w")
        mock_yaml.assert_called_once_with(
            self.instantiation_params, mocked_file.return_value.__enter__.return_value
        )
        mock_os.assert_called_once_with(filename)

    def assert_overlay_file_is_not_written(self, mocked_file, mock_yaml, mock_os):
        mocked_file.assert_not_called()
        mock_yaml.assert_not_called()
        mock_os.assert_not_called()

    def assert_bundle_is_downloaded(self, mock_resolve, mock_url_parse):
        mock_resolve.assert_called_once_with(
            self.url, self.architecture, entity_url=self.uri
        )
        mock_url_parse.assert_called_once_with(self.uri)
        self.bundle_instance.fetch_plan.assert_called_once_with(
            self.url, mock_resolve.origin
        )

    def assert_bundle_is_not_downloaded(self, mock_resolve, mock_url_parse):
        mock_resolve.assert_not_called()
        mock_url_parse.assert_not_called()
        self.bundle_instance.fetch_plan.assert_not_called()

    def test_deploy(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )
        model_name = "model1"

        self.loop.run_until_complete(
            self.libjuju.deploy(
                "cs:osm",
                model_name,
                wait=True,
                timeout=0,
                instantiation_params=None,
            )
        )
        self.assert_overlay_file_is_not_written(mocked_file, mock_yaml, mock_os)
        self.assert_bundle_is_not_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with("cs:osm", trust=True, overlays=[])
        mock_wait_for_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_no_wait(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )
        self.loop.run_until_complete(
            self.libjuju.deploy(
                "cs:osm", "model", wait=False, timeout=0, instantiation_params={}
            )
        )
        self.assert_overlay_file_is_not_written(mocked_file, mock_yaml, mock_os)
        self.assert_bundle_is_not_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with("cs:osm", trust=True, overlays=[])
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_exception(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )
        mock_deploy.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.deploy("cs:osm", "model"))
        self.assert_overlay_file_is_not_written(mocked_file, mock_yaml, mock_os)
        self.assert_bundle_is_not_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once()
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_with_instantiation_params(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )
        model_name = "model1"
        expected_filename = "{}-overlay.yaml".format(model_name)
        self.loop.run_until_complete(
            self.libjuju.deploy(
                self.uri,
                model_name,
                wait=True,
                timeout=0,
                instantiation_params=self.instantiation_params,
            )
        )
        self.assert_overlay_file_is_written(
            expected_filename, mocked_file, mock_yaml, mock_os
        )
        self.assert_bundle_is_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with(
            self.uri, trust=True, overlays=[expected_filename]
        )
        mock_wait_for_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_with_instantiation_params_no_applications(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.instantiation_params = {"applications": {}}
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )

        model_name = "model3"
        expected_filename = "{}-overlay.yaml".format(model_name)
        self.loop.run_until_complete(
            self.libjuju.deploy(
                self.uri,
                model_name,
                wait=False,
                timeout=0,
                instantiation_params=self.instantiation_params,
            )
        )

        self.assert_overlay_file_is_written(
            expected_filename, mocked_file, mock_yaml, mock_os
        )
        self.assert_bundle_is_not_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with(
            self.uri, trust=True, overlays=[expected_filename]
        )
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_with_instantiation_params_applications_not_found(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.instantiation_params = {"some_key": {"squid": {"scale": 2}}}
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )

        with self.assertRaises(JujuError):
            self.loop.run_until_complete(
                self.libjuju.deploy(
                    self.uri,
                    "model1",
                    wait=True,
                    timeout=0,
                    instantiation_params=self.instantiation_params,
                )
            )

        self.assert_overlay_file_is_not_written(mocked_file, mock_yaml, mock_os)
        self.assert_bundle_is_not_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_not_called()
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_overlay_contains_invalid_app(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )
        self.bundle_instance.applications = {"new_app"}

        with self.assertRaises(JujuApplicationNotFound) as error:
            self.loop.run_until_complete(
                self.libjuju.deploy(
                    self.uri,
                    "model2",
                    wait=True,
                    timeout=0,
                    instantiation_params=self.instantiation_params,
                )
            )
        error_msg = "Cannot find application ['squid'] in original bundle {'new_app'}"
        self.assertEqual(str(error.exception), error_msg)

        self.assert_overlay_file_is_not_written(mocked_file, mock_yaml, mock_os)
        self.assert_bundle_is_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_not_called()
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_deploy_exception_with_instantiation_params(
        self,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )

        mock_deploy.side_effect = Exception()
        model_name = "model2"
        expected_filename = "{}-overlay.yaml".format(model_name)
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.deploy(
                    self.uri,
                    model_name,
                    instantiation_params=self.instantiation_params,
                )
            )

        self.assert_overlay_file_is_written(
            expected_filename, mocked_file, mock_yaml, mock_os
        )
        self.assert_bundle_is_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with(
            self.uri, trust=True, overlays=[expected_filename]
        )
        mock_wait_for_model.assert_not_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    @asynctest.mock.patch("logging.Logger.warning")
    def test_deploy_exception_when_deleting_file_is_not_propagated(
        self,
        mock_warning,
        mock_url_parse,
        mock_bundle,
        mock_resolve,
        mock_deploy,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
        mocked_file,
        mock_yaml,
        mock_os,
    ):
        self.setup_bundle_download_mocks(
            mock_url_parse, mock_bundle, mock_resolve, mock_get_model
        )

        mock_os.side_effect = OSError("Error")
        model_name = "model2"
        expected_filename = "{}-overlay.yaml".format(model_name)
        self.loop.run_until_complete(
            self.libjuju.deploy(
                self.uri,
                model_name,
                instantiation_params=self.instantiation_params,
            )
        )

        self.assert_overlay_file_is_written(
            expected_filename, mocked_file, mock_yaml, mock_os
        )
        self.assert_bundle_is_downloaded(mock_resolve, mock_url_parse)
        mock_deploy.assert_called_once_with(
            self.uri, trust=True, overlays=[expected_filename]
        )
        mock_wait_for_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()
        mock_warning.assert_called_with(
            "Overlay file {} could not be removed: Error".format(expected_filename)
        )


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch(
    "juju.model.Model.applications", new_callable=asynctest.PropertyMock
)
@asynctest.mock.patch("juju.model.Model.machines", new_callable=asynctest.PropertyMock)
@asynctest.mock.patch("juju.model.Model.deploy")
@asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.create_machine")
class DeployCharmTest(LibjujuTestCase):
    def setUp(self):
        super(DeployCharmTest, self).setUp()

    def test_existing_app(
        self,
        mock_create_machine,
        mock_wait_for,
        mock_deploy,
        mock_machines,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_applications.return_value = {"existing_app"}

        application = None
        with self.assertRaises(JujuApplicationExists):
            application = self.loop.run_until_complete(
                self.libjuju.deploy_charm(
                    "existing_app",
                    "path",
                    "model",
                    "machine",
                )
            )
        self.assertIsNone(application)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_non_existing_machine(
        self,
        mock_create_machine,
        mock_wait_for,
        mock_deploy,
        mock_machines,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_machines.return_value = {"existing_machine": FakeMachine()}
        application = None
        with self.assertRaises(JujuMachineNotFound):
            application = self.loop.run_until_complete(
                self.libjuju.deploy_charm(
                    "app",
                    "path",
                    "model",
                    "machine",
                )
            )

        self.assertIsNone(application)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_2_units(
        self,
        mock_create_machine,
        mock_wait_for,
        mock_deploy,
        mock_machines,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_machines.return_value = {"existing_machine": FakeMachine()}
        mock_create_machine.return_value = (FakeMachine(), "other")
        mock_deploy.return_value = FakeApplication()
        application = self.loop.run_until_complete(
            self.libjuju.deploy_charm(
                "app",
                "path",
                "model",
                "existing_machine",
                num_units=2,
            )
        )

        self.assertIsInstance(application, FakeApplication)

        mock_deploy.assert_called_once()
        mock_wait_for.assert_called_once()

        mock_create_machine.assert_called_once()

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_1_unit(
        self,
        mock_create_machine,
        mock_wait_for,
        mock_deploy,
        mock_machines,
        mock_applications,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_machines.return_value = {"existing_machine": FakeMachine()}
        mock_deploy.return_value = FakeApplication()
        application = self.loop.run_until_complete(
            self.libjuju.deploy_charm("app", "path", "model", "existing_machine")
        )

        self.assertIsInstance(application, FakeApplication)

        mock_deploy.assert_called_once()
        mock_wait_for.assert_called_once()

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()


@asynctest.mock.patch(
    "juju.model.Model.applications", new_callable=asynctest.PropertyMock
)
class GetApplicationTest(LibjujuTestCase):
    def setUp(self):
        super(GetApplicationTest, self).setUp()

    def test_existing_application(
        self,
        mock_applications,
    ):
        mock_applications.return_value = {"existing_app": "exists"}
        model = juju.model.Model()
        result = self.libjuju._get_application(model, "existing_app")
        self.assertEqual(result, "exists")

    def test_non_existing_application(
        self,
        mock_applications,
    ):
        mock_applications.return_value = {"existing_app": "exists"}
        model = juju.model.Model()
        result = self.libjuju._get_application(model, "nonexisting_app")
        self.assertIsNone(result)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
@asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for")
@asynctest.mock.patch("juju.model.Model.get_action_output")
@asynctest.mock.patch("juju.model.Model.get_action_status")
class ExecuteActionTest(LibjujuTestCase):
    def setUp(self):
        super(ExecuteActionTest, self).setUp()

    def test_no_application(
        self,
        mock_get_action_status,
        mock_get_action_output,
        mock_wait_for,
        mock__get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock__get_application.return_value = None
        mock_get_model.return_value = juju.model.Model()
        output = None
        status = None
        with self.assertRaises(JujuApplicationNotFound):
            output, status = self.loop.run_until_complete(
                self.libjuju.execute_action(
                    "app",
                    "model",
                    "action",
                )
            )
        self.assertIsNone(output)
        self.assertIsNone(status)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_no_action(
        self,
        mock_get_action_status,
        mock_get_action_output,
        mock_wait_for,
        mock__get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock__get_application.return_value = FakeApplication()
        output = None
        status = None
        with self.assertRaises(JujuActionNotFound):
            output, status = self.loop.run_until_complete(
                self.libjuju.execute_action(
                    "app",
                    "model",
                    "action",
                )
            )
        self.assertIsNone(output)
        self.assertIsNone(status)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    @asynctest.mock.patch("asyncio.sleep")
    @asynctest.mock.patch(
        "osm_lcm.n2vc.tests.unit.utils.FakeUnit.is_leader_from_status"
    )
    def test_no_leader(
        self,
        mock_is_leader_from_status,
        mock_sleep,
        mock_get_action_status,
        mock_get_action_output,
        mock_wait_for,
        mock__get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock__get_application.return_value = FakeApplication()
        mock_is_leader_from_status.return_value = False
        output = None
        status = None
        with self.assertRaises(JujuLeaderUnitNotFound):
            output, status = self.loop.run_until_complete(
                self.libjuju.execute_action(
                    "app",
                    "model",
                    "action",
                )
            )
        self.assertIsNone(output)
        self.assertIsNone(status)

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_successful_exec(
        self,
        mock_get_action_status,
        mock_get_action_output,
        mock_wait_for,
        mock__get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock__get_application.return_value = FakeApplication()
        mock_get_action_output.return_value = "output"
        mock_get_action_status.return_value = {"id": "status"}
        output, status = self.loop.run_until_complete(
            self.libjuju.execute_action("app", "model", "existing_action")
        )
        self.assertEqual(output, "output")
        self.assertEqual(status, "status")

        mock_wait_for.assert_called_once()

        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class GetActionTest(LibjujuTestCase):
    def setUp(self):
        super(GetActionTest, self).setUp()

    def test_exception(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.side_effect = Exception()
        actions = None
        with self.assertRaises(Exception):
            actions = self.loop.run_until_complete(
                self.libjuju.get_actions("app", "model")
            )

        self.assertIsNone(actions)
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_success(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.return_value = FakeApplication()

        actions = self.loop.run_until_complete(self.libjuju.get_actions("app", "model"))

        self.assertEqual(actions, ["existing_action"])

        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.application.Application.get_metrics")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class GetMetricsTest(LibjujuTestCase):
    def setUp(self):
        super(GetMetricsTest, self).setUp()

    def test_get_metrics_success(
        self,
        mock_get_application,
        mock_get_metrics,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.return_value = FakeApplication()
        mock_get_model.return_value = juju.model.Model()

        self.loop.run_until_complete(self.libjuju.get_metrics("model", "app1"))

        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_get_metrics_exception(
        self,
        mock_get_application,
        mock_get_metrics,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_metrics.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.get_metrics("model", "app1"))

        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_missing_args_exception(
        self,
        mock_get_application,
        mock_get_metrics,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()

        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.get_metrics("", ""))

        mock_get_controller.assert_not_called()
        mock_get_model.assert_not_called()
        mock_disconnect_controller.assert_not_called()
        mock_disconnect_model.assert_not_called()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.model.Model.add_relation")
class AddRelationTest(LibjujuTestCase):
    def setUp(self):
        super(AddRelationTest, self).setUp()

    @asynctest.mock.patch("logging.Logger.warning")
    def test_not_found(
        self,
        mock_warning,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        # TODO in libjuju.py should this fail only with a log message?
        result = {"error": "not found", "response": "response", "request-id": 1}

        mock_get_model.return_value = juju.model.Model()
        mock_add_relation.side_effect = JujuAPIError(result)

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "app2:relation2",
            )
        )

        mock_warning.assert_called_with("Relation not found: not found")
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    @asynctest.mock.patch("logging.Logger.warning")
    def test_not_found_in_error_code(
        self,
        mock_warning,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        result = {
            "error": "relation cannot be added",
            "error-code": "not found",
            "response": "response",
            "request-id": 1,
        }

        mock_get_model.return_value = juju.model.Model()
        mock_add_relation.side_effect = JujuAPIError(result)

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "app2:relation2",
            )
        )

        mock_warning.assert_called_with("Relation not found: relation cannot be added")
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    @asynctest.mock.patch("logging.Logger.warning")
    def test_already_exists(
        self,
        mock_warning,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        # TODO in libjuju.py should this fail silently?
        result = {"error": "already exists", "response": "response", "request-id": 1}

        mock_get_model.return_value = juju.model.Model()
        mock_add_relation.side_effect = JujuAPIError(result)

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "app2:relation2",
            )
        )

        mock_warning.assert_called_with("Relation already exists: already exists")
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    @asynctest.mock.patch("logging.Logger.warning")
    def test_already_exists_error_code(
        self,
        mock_warning,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        result = {
            "error": "relation cannot be added",
            "error-code": "already exists",
            "response": "response",
            "request-id": 1,
        }

        mock_get_model.return_value = juju.model.Model()
        mock_add_relation.side_effect = JujuAPIError(result)

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "app2:relation2",
            )
        )

        mock_warning.assert_called_with(
            "Relation already exists: relation cannot be added"
        )
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_exception(
        self,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        result = {"error": "", "response": "response", "request-id": 1}
        mock_add_relation.side_effect = JujuAPIError(result)

        with self.assertRaises(JujuAPIError):
            self.loop.run_until_complete(
                self.libjuju.add_relation(
                    "model",
                    "app1:relation1",
                    "app2:relation2",
                )
            )

        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_success(
        self,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "app2:relation2",
            )
        )

        mock_add_relation.assert_called_with("app1:relation1", "app2:relation2")
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_saas(
        self,
        mock_add_relation,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()

        self.loop.run_until_complete(
            self.libjuju.add_relation(
                "model",
                "app1:relation1",
                "saas_name",
            )
        )

        mock_add_relation.assert_called_with("app1:relation1", "saas_name")
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


# TODO destroy_model testcase


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
class DestroyApplicationTest(LibjujuTestCase):
    def setUp(self):
        super(DestroyApplicationTest, self).setUp()

    def test_success(
        self,
        mock_get_controller,
        mock_get_model,
        mock_disconnect_controller,
        mock_get_application,
        mock_disconnect_model,
    ):
        mock_get_application.return_value = FakeApplication()
        mock_get_model.return_value = None
        self.loop.run_until_complete(
            self.libjuju.destroy_application(
                "existing_model",
                "existing_app",
                3600,
            )
        )
        mock_get_application.assert_called()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_application(
        self,
        mock_get_controller,
        mock_get_model,
        mock_disconnect_controller,
        mock_get_application,
        mock_disconnect_model,
    ):
        mock_get_model.return_value = None
        mock_get_application.return_value = None

        self.loop.run_until_complete(
            self.libjuju.destroy_application(
                "existing_model",
                "existing_app",
                3600,
            )
        )
        mock_get_application.assert_called()

    def test_exception(
        self,
        mock_get_controller,
        mock_get_model,
        mock_disconnect_controller,
        mock_get_application,
        mock_disconnect_model,
    ):
        mock_get_application.return_value = FakeApplication
        mock_get_model.return_value = None

        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.destroy_application(
                    "existing_model",
                    "existing_app",
                    0,
                )
            )
            mock_get_application.assert_called_once()


# @asynctest.mock.patch("juju.model.Model.get_machines")
# @asynctest.mock.patch("logging.Logger.debug")
# class DestroyMachineTest(LibjujuTestCase):
#     def setUp(self):
#         super(DestroyMachineTest, self).setUp()

#     def test_success_manual_machine(
#         self, mock_debug, mock_get_machines,
#     ):
#         mock_get_machines.side_effect = [
#             {"machine": FakeManualMachine()},
#             {"machine": FakeManualMachine()},
#             {},
#         ]
#         self.loop.run_until_complete(
#             self.libjuju.destroy_machine(juju.model.Model(), "machine", 2,)
#         )
#         calls = [
#             asynctest.call("Waiting for machine machine is destroyed"),
#             asynctest.call("Machine destroyed: machine"),
#         ]
#         mock_debug.assert_has_calls(calls)

#     def test_no_machine(
#         self, mock_debug, mock_get_machines,
#     ):
#         mock_get_machines.return_value = {}
#         self.loop.run_until_complete(
#             self.libjuju.destroy_machine(juju.model.Model(), "machine", 2)
#         )
#         mock_debug.assert_called_with("Machine not found: machine")


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class ConfigureApplicationTest(LibjujuTestCase):
    def setUp(self):
        super(ConfigureApplicationTest, self).setUp()

    def test_success(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.return_value = FakeApplication()

        self.loop.run_until_complete(
            self.libjuju.configure_application(
                "model",
                "app",
                {"config"},
            )
        )
        mock_get_application.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_exception(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.side_effect = Exception()

        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.configure_application(
                    "model",
                    "app",
                    {"config"},
                )
            )
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_controller_exception(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        result = {"error": "not found", "response": "response", "request-id": 1}

        mock_get_controller.side_effect = JujuAPIError(result)

        with self.assertRaises(JujuAPIError):
            self.loop.run_until_complete(
                self.libjuju.configure_application(
                    "model",
                    "app",
                    {"config"},
                )
            )
        mock_get_model.assert_not_called()
        mock_disconnect_controller.assert_not_called()
        mock_disconnect_model.assert_not_called()

    def test_get_model_exception(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        result = {"error": "not found", "response": "response", "request-id": 1}
        mock_get_model.side_effect = JujuAPIError(result)

        with self.assertRaises(JujuAPIError):
            self.loop.run_until_complete(
                self.libjuju.configure_application(
                    "model",
                    "app",
                    {"config"},
                )
            )
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_not_called()


# TODO _get_api_endpoints_db test case
# TODO _update_api_endpoints_db test case
# TODO healthcheck test case


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.controller.Controller.list_models")
class ListModelsTest(LibjujuTestCase):
    def setUp(self):
        super(ListModelsTest, self).setUp()

    def test_containing(
        self,
        mock_list_models,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_list_models.return_value = ["existingmodel"]
        models = self.loop.run_until_complete(self.libjuju.list_models("existing"))

        mock_disconnect_controller.assert_called_once()
        self.assertEquals(models, ["existingmodel"])

    def test_not_containing(
        self,
        mock_list_models,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_list_models.return_value = ["existingmodel", "model"]
        models = self.loop.run_until_complete(self.libjuju.list_models("mdl"))

        mock_disconnect_controller.assert_called_once()
        self.assertEquals(models, [])

    def test_no_contains_arg(
        self,
        mock_list_models,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_list_models.return_value = ["existingmodel", "model"]
        models = self.loop.run_until_complete(self.libjuju.list_models())

        mock_disconnect_controller.assert_called_once()
        self.assertEquals(models, ["existingmodel", "model"])


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.list_models")
class ModelsExistTest(LibjujuTestCase):
    def setUp(self):
        super(ModelsExistTest, self).setUp()

    def test_model_names_none(self, mock_list_models):
        mock_list_models.return_value = []
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.models_exist(None))

    def test_model_names_empty(self, mock_list_models):
        mock_list_models.return_value = []
        with self.assertRaises(Exception):
            (exist, non_existing_models) = self.loop.run_until_complete(
                self.libjuju.models_exist([])
            )

    def test_model_names_not_existing(self, mock_list_models):
        mock_list_models.return_value = ["prometheus", "grafana"]
        (exist, non_existing_models) = self.loop.run_until_complete(
            self.libjuju.models_exist(["prometheus2", "grafana"])
        )
        self.assertFalse(exist)
        self.assertEqual(non_existing_models, ["prometheus2"])

    def test_model_names_exist(self, mock_list_models):
        mock_list_models.return_value = ["prometheus", "grafana"]
        (exist, non_existing_models) = self.loop.run_until_complete(
            self.libjuju.models_exist(["prometheus", "grafana"])
        )
        self.assertTrue(exist)
        self.assertEqual(non_existing_models, [])


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.controller.Controller.list_offers")
class ListOffers(LibjujuTestCase):
    def setUp(self):
        super(ListOffers, self).setUp()

    def test_disconnect_controller(
        self,
        mock_list_offers,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_list_offers.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju._list_offers("model"))
        mock_disconnect_controller.assert_called_once()

    def test_empty_list(
        self,
        mock_list_offers,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        offer_results = Mock()
        offer_results.results = []
        mock_list_offers.return_value = offer_results
        offers = self.loop.run_until_complete(self.libjuju._list_offers("model"))
        self.assertEqual(offers, [])
        mock_disconnect_controller.assert_called_once()

    def test_non_empty_list(
        self,
        mock_list_offers,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        offer = Mock()
        offer_results = Mock()
        offer_results.results = [offer]
        mock_list_offers.return_value = offer_results
        offers = self.loop.run_until_complete(self.libjuju._list_offers("model"))
        self.assertEqual(offers, [offer])
        mock_disconnect_controller.assert_called_once()

    def test_matching_offer_name(
        self,
        mock_list_offers,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        offer_1 = Mock()
        offer_1.offer_name = "offer1"
        offer_2 = Mock()
        offer_2.offer_name = "offer2"
        offer_results = Mock()
        offer_results.results = [offer_1, offer_2]
        mock_list_offers.return_value = offer_results
        offers = self.loop.run_until_complete(
            self.libjuju._list_offers("model", offer_name="offer2")
        )
        self.assertEqual(offers, [offer_2])
        mock_disconnect_controller.assert_called_once()

    def test_not_matching_offer_name(
        self,
        mock_list_offers,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        offer_1 = Mock()
        offer_1.offer_name = "offer1"
        offer_2 = Mock()
        offer_2.offer_name = "offer2"
        offer_results = Mock()
        offer_results.results = [offer_1, offer_2]
        mock_list_offers.return_value = offer_results
        offers = self.loop.run_until_complete(
            self.libjuju._list_offers("model", offer_name="offer3")
        )
        self.assertEqual(offers, [])
        mock_disconnect_controller.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("juju.controller.Controller.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._list_offers")
@asynctest.mock.patch("juju.model.Model.create_offer")
class OfferTest(LibjujuTestCase):
    def setUp(self):
        super(OfferTest, self).setUp()

    def test_offer(
        self,
        mock_create_offer,
        mock__list_offers,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        controller = juju.controller.Controller()
        model = juju.model.Model()
        mock_get_controller.return_value = controller
        mock_get_model.return_value = model
        endpoint = RelationEndpoint("model.app-name.0", "vca", "endpoint")
        self.loop.run_until_complete(self.libjuju.offer(endpoint))
        mock_create_offer.assert_called_with(
            "app-name:endpoint", offer_name="app-name-endpoint"
        )
        mock_disconnect_model.assert_called_once_with(model)
        mock_disconnect_controller.assert_called_once_with(controller)

    def test_offer_exception(
        self,
        mock_create_offer,
        mock__list_offers,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        controller = juju.controller.Controller()
        model = juju.model.Model()
        mock_get_controller.return_value = controller
        mock_get_model.return_value = model
        mock__list_offers.return_value = []
        endpoint = RelationEndpoint("model.app-name.0", "vca", "endpoint")
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.offer(endpoint))
        mock_create_offer.assert_called_with(
            "app-name:endpoint", offer_name="app-name-endpoint"
        )
        mock_disconnect_model.assert_called_once_with(model)
        mock_disconnect_controller.assert_called_once_with(controller)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("juju.controller.Controller.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.model.Model.consume")
class ConsumeTest(LibjujuTestCase):
    def setUp(self):
        self.offer_url = "admin/model.offer_name"
        super(ConsumeTest, self).setUp()
        self.provider_libjuju = self.libjuju

    def test_consume(
        self,
        mock_consume,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        self_controller = juju.controller.Controller()
        provider_controller = juju.controller.Controller()
        mock_get_controller.side_effect = [self_controller, provider_controller]
        mock_get_model.return_value = juju.model.Model()

        self.loop.run_until_complete(
            self.libjuju.consume(
                "model_name",
                Offer(self.offer_url, vca_id="vca-id"),
                self.provider_libjuju,
            )
        )
        mock_consume.assert_called_once_with(
            "admin/model.offer_name",
            application_alias="offer_name-model-vca-id",
            controller=provider_controller,
        )
        mock_disconnect_model.assert_called_once()
        self.assertEqual(mock_disconnect_controller.call_count, 2)

    def test_parsing_error_exception(
        self,
        mock_consume,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_get_model.return_value = juju.model.Model()
        mock_consume.side_effect = juju.offerendpoints.ParseError("")

        with self.assertRaises(juju.offerendpoints.ParseError):
            self.loop.run_until_complete(
                self.libjuju.consume(
                    "model_name", Offer(self.offer_url), self.provider_libjuju
                )
            )
        mock_consume.assert_called_once()
        mock_disconnect_model.assert_called_once()
        self.assertEqual(mock_disconnect_controller.call_count, 2)

    def test_juju_error_exception(
        self,
        mock_consume,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_get_model.return_value = juju.model.Model()
        mock_consume.side_effect = juju.errors.JujuError("")

        with self.assertRaises(juju.errors.JujuError):
            self.loop.run_until_complete(
                self.libjuju.consume(
                    "model_name", Offer(self.offer_url), self.provider_libjuju
                )
            )
        mock_consume.assert_called_once()
        mock_disconnect_model.assert_called_once()
        self.assertEqual(mock_disconnect_controller.call_count, 2)

    def test_juju_api_error_exception(
        self,
        mock_consume,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_get_model.return_value = juju.model.Model()
        mock_consume.side_effect = juju.errors.JujuAPIError(
            {"error": "", "response": "", "request-id": ""}
        )

        with self.assertRaises(juju.errors.JujuAPIError):
            self.loop.run_until_complete(
                self.libjuju.consume(
                    "model_name", Offer(self.offer_url), self.provider_libjuju
                )
            )
        mock_consume.assert_called_once()
        mock_disconnect_model.assert_called_once()
        self.assertEqual(mock_disconnect_controller.call_count, 2)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_k8s_cloud_credential")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.add_cloud")
class AddK8sTest(LibjujuTestCase):
    def setUp(self):
        super(AddK8sTest, self).setUp()
        name = "cloud"
        rbac_id = generate_rbac_id()
        token = "token"
        client_cert_data = "cert"
        configuration = kubernetes.client.configuration.Configuration()
        storage_class = "storage_class"
        credential_name = name

        self._add_k8s_args = {
            "name": name,
            "rbac_id": rbac_id,
            "token": token,
            "client_cert_data": client_cert_data,
            "configuration": configuration,
            "storage_class": storage_class,
            "credential_name": credential_name,
        }

    def test_add_k8s(self, mock_add_cloud, mock_get_k8s_cloud_credential):
        self.loop.run_until_complete(self.libjuju.add_k8s(**self._add_k8s_args))
        mock_add_cloud.assert_called_once()
        mock_get_k8s_cloud_credential.assert_called_once()

    def test_add_k8s_exception(self, mock_add_cloud, mock_get_k8s_cloud_credential):
        mock_add_cloud.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.add_k8s(**self._add_k8s_args))
        mock_add_cloud.assert_called_once()
        mock_get_k8s_cloud_credential.assert_called_once()

    def test_add_k8s_missing_name(self, mock_add_cloud, mock_get_k8s_cloud_credential):
        self._add_k8s_args["name"] = ""
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.add_k8s(**self._add_k8s_args))
        mock_add_cloud.assert_not_called()

    def test_add_k8s_missing_storage_name(
        self, mock_add_cloud, mock_get_k8s_cloud_credential
    ):
        self._add_k8s_args["storage_class"] = ""
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.add_k8s(**self._add_k8s_args))
        mock_add_cloud.assert_not_called()

    def test_add_k8s_missing_configuration_keys(
        self, mock_add_cloud, mock_get_k8s_cloud_credential
    ):
        self._add_k8s_args["configuration"] = None
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.add_k8s(**self._add_k8s_args))
        mock_add_cloud.assert_not_called()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.controller.Controller.add_cloud")
@asynctest.mock.patch("juju.controller.Controller.add_credential")
class AddCloudTest(LibjujuTestCase):
    def setUp(self):
        super(AddCloudTest, self).setUp()
        self.cloud = juju.client.client.Cloud()
        self.credential = juju.client.client.CloudCredential()

    def test_add_cloud_with_credential(
        self,
        mock_add_credential,
        mock_add_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()

        cloud = self.loop.run_until_complete(
            self.libjuju.add_cloud("cloud", self.cloud, credential=self.credential)
        )
        self.assertEqual(cloud, self.cloud)
        mock_add_cloud.assert_called_once_with("cloud", self.cloud)
        mock_add_credential.assert_called_once_with(
            "cloud", credential=self.credential, cloud="cloud"
        )
        mock_disconnect_controller.assert_called_once()

    def test_add_cloud_no_credential(
        self,
        mock_add_credential,
        mock_add_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()

        cloud = self.loop.run_until_complete(
            self.libjuju.add_cloud("cloud", self.cloud)
        )
        self.assertEqual(cloud, self.cloud)
        mock_add_cloud.assert_called_once_with("cloud", self.cloud)
        mock_add_credential.assert_not_called()
        mock_disconnect_controller.assert_called_once()

    def test_add_cloud_exception(
        self,
        mock_add_credential,
        mock_add_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_add_cloud.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.add_cloud("cloud", self.cloud, credential=self.credential)
            )

        mock_add_cloud.assert_called_once_with("cloud", self.cloud)
        mock_add_credential.assert_not_called()
        mock_disconnect_controller.assert_called_once()

    def test_add_credential_exception(
        self,
        mock_add_credential,
        mock_add_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_add_credential.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.add_cloud("cloud", self.cloud, credential=self.credential)
            )

        mock_add_cloud.assert_called_once_with("cloud", self.cloud)
        mock_add_credential.assert_called_once_with(
            "cloud", credential=self.credential, cloud="cloud"
        )
        mock_disconnect_controller.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("juju.controller.Controller.remove_cloud")
class RemoveCloudTest(LibjujuTestCase):
    def setUp(self):
        super(RemoveCloudTest, self).setUp()

    def test_remove_cloud(
        self,
        mock_remove_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()

        self.loop.run_until_complete(self.libjuju.remove_cloud("cloud"))
        mock_remove_cloud.assert_called_once_with("cloud")
        mock_disconnect_controller.assert_called_once()

    def test_remove_cloud_exception(
        self,
        mock_remove_cloud,
        mock_disconnect_controller,
        mock_get_controller,
    ):
        mock_get_controller.return_value = juju.controller.Controller()
        mock_remove_cloud.side_effect = Exception()

        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.libjuju.remove_cloud("cloud"))
        mock_remove_cloud.assert_called_once_with("cloud")
        mock_disconnect_controller.assert_called_once()


@asynctest.mock.patch("kubernetes.client.configuration.Configuration")
class GetK8sCloudCredentials(LibjujuTestCase):
    def setUp(self):
        super(GetK8sCloudCredentials, self).setUp()
        self.cert_data = "cert"
        self.token = "token"

    @asynctest.mock.patch("osm_lcm.n2vc.exceptions.JujuInvalidK8sConfiguration")
    def test_not_supported(self, mock_exception, mock_configuration):
        mock_configuration.username = ""
        mock_configuration.password = ""
        mock_configuration.ssl_ca_cert = None
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        exception_raised = False
        self.token = None
        self.cert_data = None
        try:
            _ = self.libjuju.get_k8s_cloud_credential(
                mock_configuration,
                self.cert_data,
                self.token,
            )
        except JujuInvalidK8sConfiguration as e:
            exception_raised = True
            self.assertEqual(
                e.message,
                "authentication method not supported",
            )
        self.assertTrue(exception_raised)

    def test_user_pass(self, mock_configuration):
        mock_configuration.username = "admin"
        mock_configuration.password = "admin"
        mock_configuration.ssl_ca_cert = None
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        self.token = None
        self.cert_data = None
        credential = self.libjuju.get_k8s_cloud_credential(
            mock_configuration,
            self.cert_data,
            self.token,
        )
        self.assertEqual(
            credential,
            juju.client._definitions.CloudCredential(
                attrs={"username": "admin", "password": "admin"}, auth_type="userpass"
            ),
        )

    def test_user_pass_with_cert(self, mock_configuration):
        mock_configuration.username = "admin"
        mock_configuration.password = "admin"
        mock_configuration.ssl_ca_cert = None
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        self.token = None
        credential = self.libjuju.get_k8s_cloud_credential(
            mock_configuration,
            self.cert_data,
            self.token,
        )
        self.assertEqual(
            credential,
            juju.client._definitions.CloudCredential(
                attrs={
                    "ClientCertificateData": self.cert_data,
                    "username": "admin",
                    "password": "admin",
                },
                auth_type="userpasswithcert",
            ),
        )

    def test_user_no_pass(self, mock_configuration):
        mock_configuration.username = "admin"
        mock_configuration.password = ""
        mock_configuration.ssl_ca_cert = None
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        self.token = None
        self.cert_data = None
        with patch.object(self.libjuju.log, "debug") as mock_debug:
            credential = self.libjuju.get_k8s_cloud_credential(
                mock_configuration,
                self.cert_data,
                self.token,
            )
            self.assertEqual(
                credential,
                juju.client._definitions.CloudCredential(
                    attrs={"username": "admin", "password": ""}, auth_type="userpass"
                ),
            )
            mock_debug.assert_called_once_with(
                "credential for user admin has empty password"
            )

    def test_cert(self, mock_configuration):
        mock_configuration.username = ""
        mock_configuration.password = ""
        mock_configuration.api_key = {"authorization": "Bearer Token"}
        ssl_ca_cert = tempfile.NamedTemporaryFile()
        with open(ssl_ca_cert.name, "w") as ssl_ca_cert_file:
            ssl_ca_cert_file.write("cacert")
        mock_configuration.ssl_ca_cert = ssl_ca_cert.name
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        credential = self.libjuju.get_k8s_cloud_credential(
            mock_configuration,
            self.cert_data,
            self.token,
        )
        self.assertEqual(
            credential,
            juju.client._definitions.CloudCredential(
                attrs={"ClientCertificateData": self.cert_data, "Token": self.token},
                auth_type="certificate",
            ),
        )

    # TODO: Fix this test when oauth authentication is supported
    # def test_oauth2(self, mock_configuration):
    #     mock_configuration.username = ""
    #     mock_configuration.password = ""
    #     mock_configuration.api_key = {"authorization": "Bearer Token"}
    #     key = tempfile.NamedTemporaryFile()
    #     with open(key.name, "w") as key_file:
    #         key_file.write("key")
    #     mock_configuration.ssl_ca_cert = None
    #     mock_configuration.cert_file = None
    #     mock_configuration.key_file = key.name
    #     credential = self.libjuju.get_k8s_cloud_credential(
    #         mock_configuration,
    #         self.cert_data,
    #         self.token,
    #     )
    #     self.assertEqual(
    #         credential,
    #         juju.client._definitions.CloudCredential(
    #             attrs={"ClientKeyData": "key", "Token": "Token"},
    #             auth_type="oauth2",
    #         ),
    #     )

    # @asynctest.mock.patch("osm_lcm.n2vc.exceptions.JujuInvalidK8sConfiguration")
    # def test_oauth2_missing_token(self, mock_exception, mock_configuration):
    #     mock_configuration.username = ""
    #     mock_configuration.password = ""
    #     key = tempfile.NamedTemporaryFile()
    #     with open(key.name, "w") as key_file:
    #         key_file.write("key")
    #     mock_configuration.ssl_ca_cert = None
    #     mock_configuration.cert_file = None
    #     mock_configuration.key_file = key.name
    #     exception_raised = False
    #     try:
    #         _ = self.libjuju.get_k8s_cloud_credential(
    #             mock_configuration,
    #             self.cert_data,
    #             self.token,
    #         )
    #     except JujuInvalidK8sConfiguration as e:
    #         exception_raised = True
    #         self.assertEqual(
    #             e.message,
    #             "missing token for auth type oauth2",
    #         )
    #     self.assertTrue(exception_raised)

    def test_exception_cannot_set_token_and_userpass(self, mock_configuration):
        mock_configuration.username = "admin"
        mock_configuration.password = "pass"
        mock_configuration.api_key = {"authorization": "No_bearer_token"}
        mock_configuration.ssl_ca_cert = None
        mock_configuration.cert_file = None
        mock_configuration.key_file = None
        exception_raised = False
        try:
            _ = self.libjuju.get_k8s_cloud_credential(
                mock_configuration,
                self.cert_data,
                self.token,
            )
        except JujuInvalidK8sConfiguration as e:
            exception_raised = True
            self.assertEqual(
                e.message,
                "Cannot set both token and user/pass",
            )
        self.assertTrue(exception_raised)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for_model")
class ScaleApplicationTest(LibjujuTestCase):
    def setUp(self):
        super(ScaleApplicationTest, self).setUp()

    @asynctest.mock.patch("asyncio.sleep")
    def test_scale_application(
        self,
        mock_sleep,
        mock_wait_for_model,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_application,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()
        self.loop.run_until_complete(self.libjuju.scale_application("model", "app", 2))
        mock_wait_for_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_application(
        self,
        mock_wait_for,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_application,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_application.return_value = None
        mock_get_model.return_value = juju.model.Model()
        with self.assertRaises(JujuApplicationNotFound):
            self.loop.run_until_complete(
                self.libjuju.scale_application("model", "app", 2)
            )
        mock_disconnect_controller.assert_called()
        mock_disconnect_model.assert_called()

    def test_exception(
        self,
        mock_wait_for,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_application,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = None
        mock_get_application.return_value = FakeApplication()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.libjuju.scale_application("model", "app", 2, total_timeout=0)
            )
        mock_disconnect_controller.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class GetUnitNumberTest(LibjujuTestCase):
    def setUp(self):
        super(GetUnitNumberTest, self).setUp()

    def test_successful_get_unit_number(
        self,
        mock_get_applications,
    ):
        mock_get_applications.return_value = FakeApplication()
        model = juju.model.Model()
        result = self.libjuju._get_application_count(model, "app")
        self.assertEqual(result, 2)

    def test_non_existing_application(
        self,
        mock_get_applications,
    ):
        mock_get_applications.return_value = None
        model = juju.model.Model()
        result = self.libjuju._get_application_count(model, "app")
        self.assertEqual(result, None)


@asynctest.mock.patch("juju.model.Model.machines", new_callable=asynctest.PropertyMock)
class GetMachineInfoTest(LibjujuTestCase):
    def setUp(self):
        super(GetMachineInfoTest, self).setUp()

    def test_successful(
        self,
        mock_machines,
    ):
        machine_id = "existing_machine"
        model = juju.model.Model()
        mock_machines.return_value = {"existing_machine": FakeManualMachine()}
        machine, series = self.libjuju._get_machine_info(
            machine_id=machine_id,
            model=model,
        )
        self.assertIsNotNone(machine, series)

    def test_exception(
        self,
        mock_machines,
    ):
        machine_id = "not_existing_machine"
        machine = series = None
        model = juju.model.Model()
        mock_machines.return_value = {"existing_machine": FakeManualMachine()}
        with self.assertRaises(JujuMachineNotFound):
            machine, series = self.libjuju._get_machine_info(
                machine_id=machine_id,
                model=model,
            )
        self.assertIsNone(machine, series)


class GetUnitTest(LibjujuTestCase):
    def setUp(self):
        super(GetUnitTest, self).setUp()

    def test_successful(self):
        result = self.libjuju._get_unit(FakeApplication(), "existing_machine_id")
        self.assertIsInstance(result, FakeUnit)

    def test_return_none(self):
        result = self.libjuju._get_unit(FakeApplication(), "not_existing_machine_id")
        self.assertIsNone(result)


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
class CheckApplicationExists(LibjujuTestCase):
    def setUp(self):
        super(CheckApplicationExists, self).setUp()

    def test_successful(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()
        result = self.loop.run_until_complete(
            self.libjuju.check_application_exists(
                "model",
                "app",
            )
        )
        self.assertEqual(result, True)

        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_application(
        self,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = None
        result = self.loop.run_until_complete(
            self.libjuju.check_application_exists(
                "model",
                "app",
            )
        )
        self.assertEqual(result, False)

        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_machine_info")
class AddUnitTest(LibjujuTestCase):
    def setUp(self):
        super(AddUnitTest, self).setUp()

    @asynctest.mock.patch("osm_lcm.n2vc.juju_watcher.JujuModelWatcher.wait_for")
    @asynctest.mock.patch("asyncio.sleep")
    def test_successful(
        self,
        mock_sleep,
        mock_wait_for,
        mock_get_machine_info,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()
        mock_get_machine_info.return_value = FakeMachine(), "series"
        self.loop.run_until_complete(
            self.libjuju.add_unit(
                "existing_app",
                "model",
                "machine",
            )
        )

        mock_wait_for.assert_called_once()
        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_app(
        self,
        mock_get_machine_info,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = None
        with self.assertRaises(JujuApplicationNotFound):
            self.loop.run_until_complete(
                self.libjuju.add_unit(
                    "existing_app",
                    "model",
                    "machine",
                )
            )

        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_machine(
        self,
        mock_get_machine_info,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()
        mock_get_machine_info.side_effect = JujuMachineNotFound()
        with self.assertRaises(JujuMachineNotFound):
            self.loop.run_until_complete(
                self.libjuju.add_unit(
                    "existing_app",
                    "model",
                    "machine",
                )
            )

        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()


@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.get_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_model")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju.disconnect_controller")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_application")
@asynctest.mock.patch("osm_lcm.n2vc.libjuju.Libjuju._get_unit")
class DestroyUnitTest(LibjujuTestCase):
    def setUp(self):
        super(DestroyUnitTest, self).setUp()

    @asynctest.mock.patch("asyncio.sleep")
    def test_successful(
        self,
        mock_sleep,
        mock_get_unit,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()

        self.loop.run_until_complete(
            self.libjuju.destroy_unit("app", "model", "machine", 0)
        )

        mock_get_unit.assert_called()
        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_app(
        self,
        mock_get_unit,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = None

        with self.assertRaises(JujuApplicationNotFound):
            self.loop.run_until_complete(
                self.libjuju.destroy_unit("app", "model", "machine")
            )

        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()

    def test_no_unit(
        self,
        mock_get_unit,
        mock_get_application,
        mock_disconnect_controller,
        mock_disconnect_model,
        mock_get_model,
        mock_get_controller,
    ):
        mock_get_model.return_value = juju.model.Model()
        mock_get_application.return_value = FakeApplication()
        mock_get_unit.return_value = None

        with self.assertRaises(JujuError):
            self.loop.run_until_complete(
                self.libjuju.destroy_unit("app", "model", "machine")
            )

        mock_get_unit.assert_called_once()
        mock_get_application.assert_called_once()
        mock_get_controller.assert_called_once()
        mock_get_model.assert_called_once()
        mock_disconnect_controller.assert_called_once()
        mock_disconnect_model.assert_called_once()
