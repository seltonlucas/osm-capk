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
from unittest.mock import Mock, MagicMock
from unittest.mock import patch


import asynctest
from osm_lcm.n2vc.definitions import Offer, RelationEndpoint
from osm_lcm.n2vc.n2vc_juju_conn import N2VCJujuConnector
from osm_common import fslocal
from osm_common.dbmemory import DbMemory
from osm_lcm.n2vc.exceptions import (
    N2VCBadArgumentsException,
    N2VCException,
    JujuApplicationNotFound,
)
from osm_lcm.n2vc.tests.unit.utils import AsyncMock
from osm_lcm.n2vc.vca.connection_data import ConnectionData
from osm_lcm.n2vc.tests.unit.testdata import test_db_descriptors as descriptors
import yaml


class N2VCJujuConnTestCase(asynctest.TestCase):
    @asynctest.mock.patch("osm_lcm.n2vc.n2vc_juju_conn.MotorStore")
    @asynctest.mock.patch("osm_lcm.n2vc.n2vc_juju_conn.get_connection")
    @asynctest.mock.patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def setUp(
        self, mock_base64_to_cacert=None, mock_get_connection=None, mock_store=None
    ):
        self.loop = asyncio.get_event_loop()
        self.db = Mock()
        mock_base64_to_cacert.return_value = """
    -----BEGIN CERTIFICATE-----
    SOMECERT
    -----END CERTIFICATE-----"""
        mock_store.return_value = AsyncMock()
        mock_vca_connection = Mock()
        mock_get_connection.return_value = mock_vca_connection
        mock_vca_connection.data.return_value = ConnectionData(
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

        N2VCJujuConnector.get_public_key = Mock()
        self.n2vc = N2VCJujuConnector(
            db=self.db,
            fs=fslocal.FsLocal(),
            log=None,
            on_update_db=None,
        )
        N2VCJujuConnector.get_public_key.assert_not_called()
        self.n2vc.libjuju = Mock()


class GetMetricssTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(GetMetricssTest, self).setUp()
        self.n2vc.libjuju.get_metrics = AsyncMock()

    def test_success(self):
        _ = self.loop.run_until_complete(self.n2vc.get_metrics("model", "application"))
        self.n2vc.libjuju.get_metrics.assert_called_once()

    def test_except(self):
        self.n2vc.libjuju.get_metrics.side_effect = Exception()
        with self.assertRaises(Exception):
            _ = self.loop.run_until_complete(
                self.n2vc.get_metrics("model", "application")
            )
        self.n2vc.libjuju.get_metrics.assert_called_once()


class UpdateVcaStatusTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(UpdateVcaStatusTest, self).setUp()
        self.n2vc.libjuju.get_controller = AsyncMock()
        self.n2vc.libjuju.get_model = AsyncMock()
        self.n2vc.libjuju.get_executed_actions = AsyncMock()
        self.n2vc.libjuju.get_actions = AsyncMock()
        self.n2vc.libjuju.get_application_configs = AsyncMock()
        self.n2vc.libjuju._get_application = AsyncMock()

    def test_success(
        self,
    ):
        self.loop.run_until_complete(
            self.n2vc.update_vca_status(
                {"model": {"applications": {"app": {"actions": {}}}}}
            )
        )
        self.n2vc.libjuju.get_executed_actions.assert_called_once()
        self.n2vc.libjuju.get_actions.assert_called_once()
        self.n2vc.libjuju.get_application_configs.assert_called_once()

    def test_exception(self):
        self.n2vc.libjuju.get_model.return_value = None
        self.n2vc.libjuju.get_executed_actions.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.n2vc.update_vca_status(
                    {"model": {"applications": {"app": {"actions": {}}}}}
                )
            )
            self.n2vc.libjuju.get_executed_actions.assert_not_called()
            self.n2vc.libjuju.get_actions.assert_not_called_once()
            self.n2vc.libjuju.get_application_configs.assert_not_called_once()


class K8sProxyCharmsTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(K8sProxyCharmsTest, self).setUp()
        self.n2vc.libjuju.model_exists = AsyncMock()
        self.n2vc.libjuju.add_model = AsyncMock()
        self.n2vc.libjuju.deploy_charm = AsyncMock()
        self.n2vc.libjuju.model_exists.return_value = False
        self.db = DbMemory()
        self.fs = fslocal.FsLocal()
        self.fs.path = "/"
        self.n2vc.fs = self.fs
        self.n2vc.db = self.db
        self.db.create_list("nsrs", yaml.safe_load(descriptors.db_nsrs_text))
        self.db.create_list("vnfrs", yaml.safe_load(descriptors.db_vnfrs_text))

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_success(self, mock_generate_random_alfanum_string):
        self.n2vc.fs.file_exists = MagicMock(create_autospec=True)
        self.n2vc.fs.file_exists.return_value = True
        ee_id = self.loop.run_until_complete(
            self.n2vc.install_k8s_proxy_charm(
                "simple",
                ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0",
                "path",
                {},
            )
        )

        self.n2vc.libjuju.add_model.assert_called_once()
        self.n2vc.libjuju.deploy_charm.assert_called_once_with(
            model_name="dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s",
            application_name="simple-ee-z0-vnf1-vnf",
            path="//path",
            machine_id=None,
            db_dict={},
            progress_timeout=None,
            total_timeout=None,
            config=None,
        )
        self.assertEqual(
            ee_id, "dbfbd751-3de4-4e68-bd40-ec5ae0a53898-k8s.simple-ee-z0-vnf1-vnf.k8s"
        )

    def test_no_artifact_path(
        self,
    ):
        with self.assertRaises(N2VCBadArgumentsException):
            ee_id = self.loop.run_until_complete(
                self.n2vc.install_k8s_proxy_charm(
                    "simple",
                    ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0",
                    "",
                    {},
                )
            )
            self.assertIsNone(ee_id)

    def test_no_db(
        self,
    ):
        with self.assertRaises(N2VCBadArgumentsException):
            ee_id = self.loop.run_until_complete(
                self.n2vc.install_k8s_proxy_charm(
                    "simple",
                    ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0",
                    "path",
                    None,
                )
            )
            self.assertIsNone(ee_id)

    def test_file_not_exists(
        self,
    ):
        self.n2vc.fs.file_exists = MagicMock(create_autospec=True)
        self.n2vc.fs.file_exists.return_value = False
        with self.assertRaises(N2VCBadArgumentsException):
            ee_id = self.loop.run_until_complete(
                self.n2vc.install_k8s_proxy_charm(
                    "simple",
                    ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0",
                    "path",
                    {},
                )
            )
            self.assertIsNone(ee_id)

    def test_exception(
        self,
    ):
        self.n2vc.fs.file_exists = MagicMock(create_autospec=True)
        self.n2vc.fs.file_exists.return_value = True
        self.n2vc.fs.path = MagicMock(create_autospec=True)
        self.n2vc.fs.path.return_value = "path"
        self.n2vc.libjuju.deploy_charm.side_effect = Exception()
        with self.assertRaises(N2VCException):
            ee_id = self.loop.run_until_complete(
                self.n2vc.install_k8s_proxy_charm(
                    "simple",
                    ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0",
                    "path",
                    {},
                )
            )
            self.assertIsNone(ee_id)


class AddRelationTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(AddRelationTest, self).setUp()
        self.n2vc.libjuju.add_relation = AsyncMock()
        self.n2vc.libjuju.offer = AsyncMock()
        self.n2vc.libjuju.get_controller = AsyncMock()
        self.n2vc.libjuju.consume = AsyncMock()

    def test_standard_relation_same_model_and_controller(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint1")
        relation_endpoint_2 = RelationEndpoint("model-1.app2.1", None, "endpoint2")
        self.loop.run_until_complete(
            self.n2vc.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.n2vc.libjuju.add_relation.assert_called_once_with(
            model_name="model-1",
            endpoint_1="app1:endpoint1",
            endpoint_2="app2:endpoint2",
        )
        self.n2vc.libjuju.offer.assert_not_called()
        self.n2vc.libjuju.consume.assert_not_called()

    def test_cmr_relation_same_controller(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint")
        relation_endpoint_2 = RelationEndpoint("model-2.app2.1", None, "endpoint")
        offer = Offer("admin/model-1.app1")
        self.n2vc.libjuju.offer.return_value = offer
        self.n2vc.libjuju.consume.return_value = "saas"
        self.loop.run_until_complete(
            self.n2vc.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.n2vc.libjuju.offer.assert_called_once_with(relation_endpoint_1)
        self.n2vc.libjuju.consume.assert_called_once()
        self.n2vc.libjuju.add_relation.assert_called_once_with(
            "model-2", "app2:endpoint", "saas"
        )

    def test_cmr_relation_different_controller(self):
        self.n2vc._get_libjuju = AsyncMock(return_value=self.n2vc.libjuju)
        relation_endpoint_1 = RelationEndpoint(
            "model-1.app1.0", "vca-id-1", "endpoint1"
        )
        relation_endpoint_2 = RelationEndpoint(
            "model-1.app2.1", "vca-id-2", "endpoint2"
        )
        offer = Offer("admin/model-1.app1")
        self.n2vc.libjuju.offer.return_value = offer
        self.n2vc.libjuju.consume.return_value = "saas"
        self.loop.run_until_complete(
            self.n2vc.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.n2vc.libjuju.offer.assert_called_once_with(relation_endpoint_1)
        self.n2vc.libjuju.consume.assert_called_once()
        self.n2vc.libjuju.add_relation.assert_called_once_with(
            "model-1", "app2:endpoint2", "saas"
        )

    def test_relation_exception(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint")
        relation_endpoint_2 = RelationEndpoint("model-2.app2.1", None, "endpoint")
        self.n2vc.libjuju.offer.side_effect = Exception()
        with self.assertRaises(N2VCException):
            self.loop.run_until_complete(
                self.n2vc.add_relation(relation_endpoint_1, relation_endpoint_2)
            )


class UpgradeCharmTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(UpgradeCharmTest, self).setUp()
        self.n2vc._get_libjuju = AsyncMock(return_value=self.n2vc.libjuju)
        N2VCJujuConnector._get_ee_id_components = Mock()
        self.n2vc.libjuju.upgrade_charm = AsyncMock()

    def test_empty_ee_id(self):
        with self.assertRaises(N2VCBadArgumentsException):
            self.loop.run_until_complete(
                self.n2vc.upgrade_charm(
                    "", "/sample_charm_path", "sample_charm_id", "native-charm", None
                )
            )
        self.n2vc._get_libjuju.assert_called()
        self.n2vc._get_ee_id_components.assert_not_called()
        self.n2vc.libjuju.upgrade_charm.assert_not_called()

    def test_wrong_ee_id(self):
        N2VCJujuConnector._get_ee_id_components.side_effect = Exception
        with self.assertRaises(N2VCBadArgumentsException):
            self.loop.run_until_complete(
                self.n2vc.upgrade_charm(
                    "ns-id-k8s.app-vnf-vnf-id-vdu-vdu-random.k8s",
                    "/sample_charm_path",
                    "sample_charm_id",
                    "native-charm",
                    500,
                )
            )
        self.n2vc._get_libjuju.assert_called()
        self.n2vc._get_ee_id_components.assert_called()
        self.n2vc.libjuju.upgrade_charm.assert_not_called()

    def test_charm_upgrade_succeded(self):
        N2VCJujuConnector._get_ee_id_components.return_value = (
            "sample_model",
            "sample_app",
            "sample_machine_id",
        )
        self.loop.run_until_complete(
            self.n2vc.upgrade_charm(
                "ns-id-k8s.app-vnf-vnf-id-vdu-vdu-random.k8s",
                "/sample_charm_path",
                "sample_charm_id",
                "native-charm",
                500,
            )
        )
        self.n2vc._get_libjuju.assert_called()
        self.n2vc._get_ee_id_components.assert_called()
        self.n2vc.libjuju.upgrade_charm.assert_called_with(
            application_name="sample_app",
            path="/sample_charm_path",
            model_name="sample_model",
            total_timeout=500,
        )

    def test_charm_upgrade_failed(self):
        N2VCJujuConnector._get_ee_id_components.return_value = (
            "sample_model",
            "sample_app",
            "sample_machine_id",
        )
        self.n2vc.libjuju.upgrade_charm.side_effect = JujuApplicationNotFound
        with self.assertRaises(N2VCException):
            self.loop.run_until_complete(
                self.n2vc.upgrade_charm(
                    "ns-id-k8s.app-vnf-vnf-id-vdu-vdu-random.k8s",
                    "/sample_charm_path",
                    "sample_charm_id",
                    "native-charm",
                    None,
                )
            )
        self.n2vc._get_libjuju.assert_called()
        self.n2vc._get_ee_id_components.assert_called()
        self.n2vc.libjuju.upgrade_charm.assert_called_with(
            application_name="sample_app",
            path="/sample_charm_path",
            model_name="sample_model",
            total_timeout=None,
        )


class GenerateApplicationNameTest(N2VCJujuConnTestCase):
    vnf_id = "dbfbd751-3de4-4e68-bd40-ec5ae0a53898"

    def setUp(self):
        super(GenerateApplicationNameTest, self).setUp()
        self.db = MagicMock(DbMemory)

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_generate_backward_compatible_application_name(
        self, mock_generate_random_alfanum
    ):
        vdu_id = "mgmtVM"
        vdu_count = "0"
        expected_result = "app-vnf-ec5ae0a53898-vdu-mgmtVM-cnt-0-random"

        application_name = self.n2vc._generate_backward_compatible_application_name(
            GenerateApplicationNameTest.vnf_id, vdu_id, vdu_count
        )
        self.assertEqual(application_name, expected_result)

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_generate_backward_compatible_application_name_without_vnf_id_vdu_id(
        self, mock_generate_random_alfanum
    ):
        vnf_id = None
        vdu_id = ""
        vdu_count = None
        expected_result = "app--random"
        application_name = self.n2vc._generate_backward_compatible_application_name(
            vnf_id, vdu_id, vdu_count
        )

        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_find_charm_level_with_vnf_id(self):
        vdu_id = ""
        expected_result = "vnf-level"
        charm_level = self.n2vc._find_charm_level(
            GenerateApplicationNameTest.vnf_id, vdu_id
        )
        self.assertEqual(charm_level, expected_result)

    def test_find_charm_level_with_vdu_id(self):
        vnf_id = ""
        vdu_id = "mgmtVM"
        with self.assertRaises(N2VCException):
            self.n2vc._find_charm_level(vnf_id, vdu_id)

    def test_find_charm_level_with_vnf_id_and_vdu_id(self):
        vdu_id = "mgmtVM"
        expected_result = "vdu-level"
        charm_level = self.n2vc._find_charm_level(
            GenerateApplicationNameTest.vnf_id, vdu_id
        )
        self.assertEqual(charm_level, expected_result)

    def test_find_charm_level_without_vnf_id_and_vdu_id(self):
        vnf_id = ""
        vdu_id = ""
        expected_result = "ns-level"
        charm_level = self.n2vc._find_charm_level(vnf_id, vdu_id)
        self.assertEqual(charm_level, expected_result)

    def test_generate_application_name_ns_charm(self):
        charm_level = "ns-level"
        vnfrs = {}
        vca_records = [
            {
                "target_element": "ns",
                "member-vnf-index": "",
                "vdu_id": None,
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": None,
                "vdu_name": None,
                "type": "proxy_charm",
                "ee_descriptor_id": None,
                "charm_name": "simple-ns-charm-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh",
                "ee_id": None,
                "application": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = ""
        vdu_count = ""
        vdu_id = None
        expected_result = "simple-ns-charm-abc-000-rrrr-nnnn-4444-h-ns"
        application_name = self.n2vc._generate_application_name(
            charm_level,
            vnfrs,
            vca_records,
            vnf_count=vnf_count,
            vdu_id=vdu_id,
            vdu_count=vdu_count,
        )
        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_generate_application_name_ns_charm_empty_vca_records(self):
        charm_level = "ns-level"
        vnfrs = {}
        vca_records = []
        vnf_count = ""
        vdu_count = ""
        vdu_id = None
        with self.assertRaises(N2VCException):
            self.n2vc._generate_application_name(
                charm_level,
                vnfrs,
                vca_records,
                vnf_count=vnf_count,
                vdu_id=vdu_id,
                vdu_count=vdu_count,
            )

    def test_generate_application_name_vnf_charm(self):
        charm_level = "vnf-level"
        vnfrs = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vca_records = [
            {
                "target_element": "vnf/vnf1",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = "1"
        vdu_count = ""
        vdu_id = None
        expected_result = "simple-ee-ab-1-vnf111-xxx-y-vnf"
        application_name = self.n2vc._generate_application_name(
            charm_level,
            vnfrs,
            vca_records,
            vnf_count=vnf_count,
            vdu_id=vdu_id,
            vdu_count=vdu_count,
        )
        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_generate_application_name_vdu_charm_kdu_name_in_vca_record_is_none(self):
        charm_level = "vdu-level"
        vnfrs = {
            "member-vnf-index-ref": "vnf111-xxx-yyy-zzz",
            "vdur": [
                {"_id": "38912ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "mgmtVM"},
                {"_id": "45512ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "dataVM"},
            ],
        }
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtvm",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": "mgmtVM",
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            },
            {
                "target_element": "vnf/vnf1/dataVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": "dataVM",
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "datavm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-8888-hhh-3333-yyyy-888-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            },
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = "mgmtVM"
        expected_result = "simple-ee-ab-2-vnf111-xxx-y-mgmtVM-0-vdu"
        application_name = self.n2vc._generate_application_name(
            charm_level,
            vnfrs,
            vca_records,
            vnf_count=vnf_count,
            vdu_id=vdu_id,
            vdu_count=vdu_count,
        )
        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_generate_application_name_vdu_charm_vdu_id_kdu_name_in_vca_record_are_both_set(
        self,
    ):
        charm_level = "vdu-level"
        vnfrs = {
            "member-vnf-index-ref": "vnf111-xxx-yyy-zzz",
            "vdur": [
                {"_id": "38912ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "mgmtVM"},
                {"_id": "45512ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "dataVM"},
            ],
        }
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": "mgmtVM",
                "kdu_name": "mgmtVM",
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            },
            {
                "target_element": "vnf/vnf1/dataVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": "dataVM",
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "datavm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-8888-hhh-3333-yyyy-888-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            },
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = "mgmtVM"
        expected_result = "simple-ee-ab-2-vnf111-xxx-y-mgmtVM-0-vdu"
        application_name = self.n2vc._generate_application_name(
            charm_level,
            vnfrs,
            vca_records,
            vnf_count=vnf_count,
            vdu_id=vdu_id,
            vdu_count=vdu_count,
        )
        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_generate_application_name_vdu_charm_both_vdu_id_kdu_name_in_vca_record_are_none(
        self,
    ):
        charm_level = "vdu-level"
        vnfrs = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": None,
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = "mgmtVM"
        with self.assertRaises(KeyError):
            self.n2vc._generate_application_name(
                charm_level,
                vnfrs,
                vca_records,
                vnf_count=vnf_count,
                vdu_id=vdu_id,
                vdu_count=vdu_count,
            )

    def test_generate_application_name_vdu_charm_given_vdu_id_is_none(self):
        charm_level = "vdu-level"
        vnfrs = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtvVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": None,
                "kdu_name": "mgmtVM",
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = None
        with self.assertRaises(N2VCException):
            self.n2vc._generate_application_name(
                charm_level,
                vnfrs,
                vca_records,
                vnf_count=vnf_count,
                vdu_id=vdu_id,
                vdu_count=vdu_count,
            )

    def test_generate_application_name_vdu_charm_vdu_id_does_not_match_with_the_key_in_vca_record(
        self,
    ):
        charm_level = "vdu-level"
        vnfrs = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": None,
                "kdu_name": "mgmtVM",
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = "mgmtvm"
        with self.assertRaises(KeyError):
            self.n2vc._generate_application_name(
                charm_level,
                vnfrs,
                vca_records,
                vnf_count=vnf_count,
                vdu_id=vdu_id,
                vdu_count=vdu_count,
            )

    def test_generate_application_name_vdu_charm_vdu_id_in_vca_record_is_none(self):
        charm_level = "vdu-level"
        vnfrs = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vca_records = [
            {
                "target_element": "vnf/vnf1/mgmtVM",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": None,
                "kdu_name": "mgmtVM",
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vnf_count = "2"
        vdu_count = "0"
        vdu_id = "mgmtVM"
        expected_result = "simple-ee-ab-2-vnf111-xxx-y-mgmtVM-0-vdu"
        application_name = self.n2vc._generate_application_name(
            charm_level,
            vnfrs,
            vca_records,
            vnf_count=vnf_count,
            vdu_id=vdu_id,
            vdu_count=vdu_count,
        )
        self.assertEqual(application_name, expected_result)
        self.assertLess(len(application_name), 50)

    def test_get_vnf_count_db_vnfr_ns_charm(self):
        self.db.get_one.return_value = {"member-vnf-index-ref": "sample-ref"}
        charm_level = "ns-level"
        vnf_id_and_count = "m7fbd751-3de4-4e68-bd40-ec5ae0a53898-4"
        with patch.object(self.n2vc, "db", self.db):
            vnf_count, db_vnfr = self.n2vc._get_vnf_count_and_record(
                charm_level, vnf_id_and_count
            )
        self.assertEqual(vnf_count, "")
        self.assertEqual(db_vnfr, {})

    def test_get_vnf_count_db_vnfr_vnf_charm(self):
        self.db.get_one.return_value = {"member-vnf-index-ref": "sample-ref"}
        charm_level = "vnf-level"
        vnf_id_and_count = "m7fbd751-3de4-4e68-bd40-ec5ae0a53898-4"
        with patch.object(self.n2vc, "db", self.db):
            vnf_count, db_vnfr = self.n2vc._get_vnf_count_and_record(
                charm_level, vnf_id_and_count
            )
        self.assertEqual(vnf_count, "4")
        self.assertEqual(db_vnfr, {"member-vnf-index-ref": "sample-ref"})

    def test_get_vnf_count_db_vnfr_vdu_charm(self):
        self.db.get_one.return_value = {"member-vnf-index-ref": "sample-ref"}
        charm_level = "vdu-level"
        vnf_id_and_count = "m7fbd751-3de4-4e68-bd40-ec5ae0a53898-2"
        with patch.object(self.n2vc, "db", self.db):
            vnf_count, db_vnfr = self.n2vc._get_vnf_count_and_record(
                charm_level, vnf_id_and_count
            )
        self.assertEqual(vnf_count, "2")
        self.assertEqual(db_vnfr, {"member-vnf-index-ref": "sample-ref"})

    def test_get_vca_records_vdu_charm(self):
        charm_level = "vdu-level"
        db_vnfr = {
            "member-vnf-index-ref": "vnf111-xxx-yyy-zzz",
            "vdur": [
                {"_id": "38912ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "mgmtVM"},
                {"_id": "45512ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "dataVM"},
            ],
        }
        db_nsr = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "vnf/vnf2/datavm",
                            "member-vnf-index": "vnf222-xxx-yyy-zzz",
                            "vdu_id": "45512ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "datavm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-8888-hhh-3333-yyyy-888-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        expected_result = [
            {
                "target_element": "vnf/vnf1/mgmtvm",
                "member-vnf-index": "vnf111-xxx-yyy-zzz",
                "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                "vdu_name": "mgmtvm",
                "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vca_records = self.n2vc._get_vca_records(charm_level, db_nsr, db_vnfr)
        self.assertEqual(vca_records, expected_result)

    def test_get_vca_records_vnf_charm_member_vnf_index_mismatch(self):
        charm_level = "vnf-level"
        db_vnfr = {"member-vnf-index-ref": "vnf222-xxx-yyy-zzz"}
        db_nsr = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "45512ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "datavm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-8888-hhh-3333-yyyy-888-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        expected_result = []
        vca_records = self.n2vc._get_vca_records(charm_level, db_nsr, db_vnfr)
        self.assertEqual(vca_records, expected_result)

    def test_get_vca_records_ns_charm(self):
        charm_level = "ns-level"
        db_vnfr = {"member-vnf-index-ref": "vnf222-xxx-yyy-zzz"}
        db_nsr = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "simple-ns-charm-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        expected_result = [
            {
                "target_element": "ns",
                "member-vnf-index": None,
                "vdu_id": None,
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "",
                "vdu_name": "",
                "ee_descriptor_id": "",
                "charm_name": "simple-ns-charm-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vca_records = self.n2vc._get_vca_records(charm_level, db_nsr, db_vnfr)
        self.assertEqual(vca_records, expected_result)

    def test_get_vca_records_ns_charm_empty_charm_name(self):
        charm_level = "ns-level"
        db_vnfr = {"member-vnf-index-ref": "vnf222-xxx-yyy-zzz"}
        db_nsr = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        expected_result = [
            {
                "target_element": "ns",
                "member-vnf-index": None,
                "vdu_id": None,
                "kdu_name": None,
                "vdu_count_index": None,
                "vnfd_id": "",
                "vdu_name": "",
                "ee_descriptor_id": "",
                "charm_name": "",
                "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
            }
        ]
        vca_records = self.n2vc._get_vca_records(charm_level, db_nsr, db_vnfr)
        self.assertEqual(vca_records, expected_result)

    def test_get_application_name_vnf_charm(self):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "simple-ee-ab-z0-vnf111-xxx-y-vnf"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with(
                "vnf-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
            )
            self.db.get_one.assert_called_once()

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_get_application_name_vnf_charm_old_naming(
        self, mock_generate_random_alfanum
    ):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {"member-vnf-index-ref": "vnf111-xxx-yyy-zzz"}
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "app-vnf-eb3161eec0-z0-random"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            mock_vnf_count_and_record.assert_called_once_with(
                "vnf-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
            )
            self.db.get_one.assert_called_once()

    def test_get_application_name_vnf_charm_vnf_index_ref_mismatch(self):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "38912ff7-5bdd-4228-911f-c2bee259c44a",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {"member-vnf-index-ref": "vnf222-xxx-yyy-zzz"}
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            with self.assertRaises(N2VCException):
                self.n2vc._get_application_name(namespace)
                mock_vnf_count_and_record.assert_called_once_with(
                    "vnf-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
                )
                self.db.get_one.assert_called_once()

    def test_get_application_name_vdu_charm(self):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0.mgmtVM-0"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtvm",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "mgmtVM",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {
            "member-vnf-index-ref": "vnf111-xxx-yyy-zzz",
            "vdur": [
                {"_id": "38912ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "mgmtVM"},
                {"_id": "45512ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "dataVM"},
            ],
        }
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "simple-ee-ab-z0-vnf111-xxx-y-mgmtvm-z0-vdu"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with(
                "vdu-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
            )
            self.db.get_one.assert_called_once()

    def test_get_application_name_kdu_charm(self):
        namespace = ".82b11965-e580-47c0-9ee0-329f318a305b.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0.ldap"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/openldap/kdu/ldap",
                            "member-vnf-index": "openldap",
                            "vdu_id": None,
                            "kdu_name": "ldap",
                            "vdu_count_index": 0,
                            "operational-status": "init",
                            "detailed-status": "",
                            "step": "initial-deploy",
                            "vnfd_id": "openldap_knf",
                            "vdu_name": None,
                            "type": "lxc_proxy_charm",
                            "ee_descriptor_id": "openldap-ee",
                            "charm_name": "",
                            "ee_id": "",
                            "application": "openldap-ee-z0-openldap-vdu",
                            "model": "82b11965-e580-47c0-9ee0-329f318a305b",
                            "config_sw_installed": True,
                        }
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {"member-vnf-index-ref": "openldap", "vdur": {}}
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "openldap-ee-z0-openldap-ldap-vdu"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with(
                "vdu-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
            )
            self.db.get_one.assert_called_once()

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_get_application_name_vdu_charm_old_naming(
        self, mock_generate_random_alfanum
    ):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898.1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0.mgmtVM-0"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "vnf/vnf1/mgmtVM",
                            "member-vnf-index": "vnf111-xxx-yyy-zzz",
                            "vdu_id": "mgmtVM",
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "r7fbd751-3de4-4e68-bd40-ec5ae0a53898",
                            "vdu_name": "mgmtvm",
                            "ee_descriptor_id": "simple-ee-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        },
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {
            "member-vnf-index-ref": "vnf111-xxx-yyy-zzz",
            "vdur": [
                {"_id": "38912ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "mgmtVM"},
                {"_id": "45512ff7-5bdd-4228-911f-c2bee259c44a", "vdu-id-ref": "dataVM"},
            ],
        }
        vnf_count = "0"
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "app-vnf-eb3161eec0-z0-vdu-mgmtvm-cnt-z0-random"

        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with(
                "vdu-level", "1b6a4eb3-4fbf-415e-985c-4aeb3161eec0-0"
            )
            self.db.get_one.assert_called_once()

    def test_get_application_name_ns_charm(self):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "simple-ns-charm-abc-000-rrrr-nnnn-4444-hhh-3333-yyyy-333-hhh-ttt-444",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        }
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {}
        vnf_count = ""
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "simple-ns-charm-abc-z000-rrrr-nnnn-z4444-h-ns"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with("ns-level", None)
            self.db.get_one.assert_called_once()

    def test_get_application_name_ns_charm_empty_charm_name(self):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "charm_name": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        }
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {}
        vnf_count = ""
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            with self.assertRaises(N2VCException):
                self.n2vc._get_application_name(namespace)
                mock_vnf_count_and_record.assert_called_once_with("ns-level", None)
                self.db.get_one.assert_called_once()

    @patch(
        "osm_lcm.n2vc.n2vc_juju_conn.generate_random_alfanum_string",
        **{"return_value": "random"}
    )
    def test_get_application_name_ns_charm_old_naming(
        self, mock_generate_random_alfanum
    ):
        namespace = ".dbfbd751-3de4-4e68-bd40-ec5ae0a53898"
        self.db.get_one.return_value = {
            "_admin": {
                "deployed": {
                    "VCA": [
                        {
                            "target_element": "ns",
                            "member-vnf-index": None,
                            "vdu_id": None,
                            "kdu_name": None,
                            "vdu_count_index": None,
                            "vnfd_id": "",
                            "vdu_name": "",
                            "ee_descriptor_id": "",
                            "model": "dbfbd751-3de4-4e68-bd40-ec5ae0a53898",
                        }
                    ]
                }
            }
        }
        mock_vnf_count_and_record = MagicMock()
        db_vnfr = {}
        vnf_count = ""
        mock_vnf_count_and_record.return_value = (vnf_count, db_vnfr)
        expected_result = "app-random"
        with patch.object(self.n2vc, "db", self.db), patch.object(
            self.n2vc, "_get_vnf_count_and_record", mock_vnf_count_and_record
        ):
            application_name = self.n2vc._get_application_name(namespace)
            self.assertEqual(application_name, expected_result)
            self.assertLess(len(application_name), 50)
            mock_vnf_count_and_record.assert_called_once_with("ns-level", None)
            self.db.get_one.assert_called_once()


class DeleteExecutionEnvironmentTest(N2VCJujuConnTestCase):
    def setUp(self):
        super(DeleteExecutionEnvironmentTest, self).setUp()
        self.n2vc.libjuju.get_controller = AsyncMock()
        self.n2vc.libjuju.destroy_model = AsyncMock()
        self.n2vc.libjuju.destroy_application = AsyncMock()

    def test_remove_ee__target_application_exists__model_is_deleted(self):
        get_ee_id_components = MagicMock()
        get_ee_id_components.return_value = ("my_model", "my_app", None)
        model = MagicMock(create_autospec=True)
        model.applications = {}
        self.n2vc.libjuju.get_model = AsyncMock()
        self.n2vc.libjuju.get_model.return_value = model
        with patch.object(self.n2vc, "_get_ee_id_components", get_ee_id_components):
            self.loop.run_until_complete(
                self.n2vc.delete_execution_environment(
                    "my_ee", application_to_delete="my_app"
                )
            )
        self.n2vc.libjuju.destroy_application.assert_called_with(
            model_name="my_model",
            application_name="my_app",
            total_timeout=None,
        )
        self.n2vc.libjuju.destroy_model.assert_called_with(
            model_name="my_model",
            total_timeout=None,
        )

    def test_remove_ee__multiple_applications_exist__model_is_not_deleted(self):
        get_ee_id_components = MagicMock()
        get_ee_id_components.return_value = ("my_model", "my_app", None)
        model = MagicMock(create_autospec=True)
        model.applications = {MagicMock(create_autospec=True)}
        self.n2vc.libjuju.get_model = AsyncMock()
        self.n2vc.libjuju.get_model.return_value = model
        with patch.object(self.n2vc, "_get_ee_id_components", get_ee_id_components):
            self.loop.run_until_complete(
                self.n2vc.delete_execution_environment(
                    "my_ee", application_to_delete="my_app"
                )
            )
        self.n2vc.libjuju.destroy_application.assert_called_with(
            model_name="my_model",
            application_name="my_app",
            total_timeout=None,
        )
        self.n2vc.libjuju.destroy_model.assert_not_called()

    def test_remove_ee__target_application_does_not_exist__model_is_deleted(self):
        get_ee_id_components = MagicMock()
        get_ee_id_components.return_value = ("my_model", "my_app", None)
        with patch.object(self.n2vc, "_get_ee_id_components", get_ee_id_components):
            self.loop.run_until_complete(
                self.n2vc.delete_execution_environment("my_ee")
            )
        self.n2vc.libjuju.destroy_model.assert_called_with(
            model_name="my_model",
            total_timeout=None,
        )
