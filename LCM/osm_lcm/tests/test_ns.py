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
# contact: alfonso.tiernosepulveda@telefonica.com
##


import asynctest  # pip3 install asynctest --user
import asyncio
from copy import deepcopy
import yaml
import copy
from osm_lcm.n2vc.exceptions import N2VCException
from os import getenv
from osm_lcm import ns
from osm_common.msgkafka import MsgKafka

from osm_lcm.data_utils.lcm_config import LcmCfg
from osm_lcm.lcm_utils import TaskRegistry
from osm_lcm.ng_ro import NgRoClient
from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem
from osm_lcm.data_utils.vca import Relation, EERelation, DeployedVCA
from osm_lcm.data_utils.vnfd import find_software_version
from osm_lcm.lcm_utils import check_juju_bundle_existence, get_charm_artifact_path
from osm_lcm.lcm_utils import LcmException
from uuid import uuid4
from unittest.mock import Mock, patch

from osm_lcm.tests import test_db_descriptors as descriptors

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"

""" Perform unittests using asynctest of osm_lcm.ns module
It allows, if some testing ENV are supplied, testing without mocking some external libraries for debugging:
    OSMLCMTEST_NS_PUBKEY: public ssh-key returned by N2VC to inject to VMs
    OSMLCMTEST_NS_NAME: change name of NS
    OSMLCMTEST_PACKAGES_PATH: path where the vnf-packages are stored (de-compressed), each one on a 'vnfd_id' folder
    OSMLCMTEST_NS_IPADDRESS: IP address where emulated VMs are reached. Comma separate list
    OSMLCMTEST_RO_VIMID: VIM id of RO target vim IP. Obtain it with openmano datcenter-list on RO container
    OSMLCMTEST_VCA_NOMOCK: Do no mock the VCA, N2VC library, for debugging it
    OSMLCMTEST_RO_NOMOCK: Do no mock the ROClient library, for debugging it
    OSMLCMTEST_DB_NOMOCK: Do no mock the database library, for debugging it
    OSMLCMTEST_FS_NOMOCK: Do no mock the File Storage library, for debugging it
    OSMLCMTEST_LOGGING_NOMOCK: Do no mock the logging
    OSMLCM_VCA_XXX: configuration of N2VC
    OSMLCM_RO_XXX: configuration of RO
"""

lcm_config_dict = {
    "global": {"loglevel": "DEBUG"},
    "timeout": {},
    "VCA": {  # TODO replace with os.get_env to get other configurations
        "host": getenv("OSMLCM_VCA_HOST", "vca"),
        "port": getenv("OSMLCM_VCA_PORT", 17070),
        "user": getenv("OSMLCM_VCA_USER", "admin"),
        "secret": getenv("OSMLCM_VCA_SECRET", "vca"),
        "public_key": getenv("OSMLCM_VCA_PUBKEY", None),
        "ca_cert": getenv("OSMLCM_VCA_CACERT", None),
        "apiproxy": getenv("OSMLCM_VCA_APIPROXY", "192.168.1.1"),
    },
    "RO": {
        "uri": "http://{}:{}/openmano".format(
            getenv("OSMLCM_RO_HOST", "ro"), getenv("OSMLCM_RO_PORT", "9090")
        ),
        "tenant": getenv("OSMLCM_RO_TENANT", "osm"),
        "logger_name": "lcm.ROclient",
        "loglevel": "DEBUG",
        "ng": True,
    },
}

lcm_config = LcmCfg()
lcm_config.set_from_dict(lcm_config_dict)
lcm_config.transform()

nsr_id = descriptors.test_ids["TEST-A"]["ns"]
nslcmop_id = descriptors.test_ids["TEST-A"]["update"]
vnfr_id = "6421c7c9-d865-4fb4-9a13-d4275d243e01"
vnfd_id = "7637bcf8-cf14-42dc-ad70-c66fcf1e6e77"
update_fs = Mock(autospec=True)
update_fs.path.__add__ = Mock()
update_fs.path.side_effect = ["/", "/", "/", "/"]
update_fs.sync.side_effect = [None, None]


def callable(a):
    return a


class TestBaseNS(asynctest.TestCase):
    async def _n2vc_DeployCharms(
        self,
        model_name,
        application_name,
        vnfd,
        charm_path,
        params={},
        machine_spec={},
        callback=None,
        *callback_args,
    ):
        if callback:
            for status, message in (
                ("maintenance", "installing sofwware"),
                ("active", "Ready!"),
            ):
                # call callback after some time
                asyncio.sleep(5)
                callback(model_name, application_name, status, message, *callback_args)

    @staticmethod
    def _n2vc_FormatApplicationName(*args):
        num_calls = 0
        while True:
            yield "app_name-{}".format(num_calls)
            num_calls += 1

    def _n2vc_CreateExecutionEnvironment(
        self, namespace, reuse_ee_id, db_dict, *args, **kwargs
    ):
        k_list = namespace.split(".")
        ee_id = k_list[1] + "."
        if len(k_list) >= 2:
            for k in k_list[2:4]:
                ee_id += k[:8]
        else:
            ee_id += "_NS_"
        return ee_id, {}

    def _ro_status(self, *args, **kwargs):
        print("Args > {}".format(args))
        print("kwargs > {}".format(kwargs))
        if args:
            if "update" in args:
                ro_ns_desc = yaml.safe_load(descriptors.ro_update_action_text)
                while True:
                    yield ro_ns_desc
        if kwargs.get("delete"):
            ro_ns_desc = yaml.safe_load(descriptors.ro_delete_action_text)
            while True:
                yield ro_ns_desc

        ro_ns_desc = yaml.safe_load(descriptors.ro_ns_text)

        # if ip address provided, replace descriptor
        ip_addresses = getenv("OSMLCMTEST_NS_IPADDRESS", "")
        if ip_addresses:
            ip_addresses_list = ip_addresses.split(",")
            for vnf in ro_ns_desc["vnfs"]:
                if not ip_addresses_list:
                    break
                vnf["ip_address"] = ip_addresses_list[0]
                for vm in vnf["vms"]:
                    if not ip_addresses_list:
                        break
                    vm["ip_address"] = ip_addresses_list.pop(0)

        while True:
            yield ro_ns_desc
            for net in ro_ns_desc["nets"]:
                if net["status"] != "ACTIVE":
                    net["status"] = "ACTIVE"
                    break
            else:
                for vnf in ro_ns_desc["vnfs"]:
                    for vm in vnf["vms"]:
                        if vm["status"] != "ACTIVE":
                            vm["status"] = "ACTIVE"
                            break

    def _ro_deploy(self, *args, **kwargs):
        return {"action_id": args[1]["action_id"], "nsr_id": args[0], "status": "ok"}

    def _return_uuid(self, *args, **kwargs):
        return str(uuid4())

    async def setUp(self):
        self.mock_db()
        self.mock_kafka()
        self.mock_filesystem()
        self.mock_task_registry()
        self.mock_vca_k8s()
        self.create_nslcm_class()
        self.mock_logging()
        self.mock_vca_n2vc()
        self.mock_ro()

    def mock_db(self):
        if not getenv("OSMLCMTEST_DB_NOMOCK"):
            # Cleanup singleton Database instance
            Database.instance = None

            self.db = Database({"database": {"driver": "memory"}}).instance.db
            self.db.create_list("vnfds", yaml.safe_load(descriptors.db_vnfds_text))
            self.db.create_list(
                "vnfds_revisions", yaml.safe_load(descriptors.db_vnfds_revisions_text)
            )
            self.db.create_list("nsds", yaml.safe_load(descriptors.db_nsds_text))
            self.db.create_list("nsrs", yaml.safe_load(descriptors.db_nsrs_text))
            self.db.create_list(
                "vim_accounts", yaml.safe_load(descriptors.db_vim_accounts_text)
            )
            self.db.create_list(
                "k8sclusters", yaml.safe_load(descriptors.db_k8sclusters_text)
            )
            self.db.create_list(
                "nslcmops", yaml.safe_load(descriptors.db_nslcmops_text)
            )
            self.db.create_list("vnfrs", yaml.safe_load(descriptors.db_vnfrs_text))
            self.db_vim_accounts = yaml.safe_load(descriptors.db_vim_accounts_text)

    def mock_kafka(self):
        self.msg = asynctest.Mock(MsgKafka())

    def mock_filesystem(self):
        if not getenv("OSMLCMTEST_FS_NOMOCK"):
            self.fs = asynctest.Mock(
                Filesystem({"storage": {"driver": "local", "path": "/"}}).instance.fs
            )
            self.fs.get_params.return_value = {
                "path": getenv("OSMLCMTEST_PACKAGES_PATH", "./test/temp/packages")
            }
            self.fs.file_open = asynctest.mock_open()
            # self.fs.file_open.return_value.__enter__.return_value = asynctest.MagicMock()  # called on a python "with"
            # self.fs.file_open.return_value.__enter__.return_value.read.return_value = ""   # empty file

    def mock_task_registry(self):
        self.lcm_tasks = asynctest.Mock(TaskRegistry())
        self.lcm_tasks.lock_HA.return_value = True
        self.lcm_tasks.waitfor_related_HA.return_value = None
        self.lcm_tasks.lookfor_related.return_value = ("", [])

    def mock_vca_k8s(self):
        if not getenv("OSMLCMTEST_VCA_K8s_NOMOCK"):
            ns.K8sJujuConnector = asynctest.MagicMock(ns.K8sJujuConnector)
            # ns.K8sHelmConnector = asynctest.MagicMock(ns.K8sHelmConnector)
            ns.K8sHelm3Connector = asynctest.MagicMock(ns.K8sHelm3Connector)

        if not getenv("OSMLCMTEST_VCA_NOMOCK"):
            ns.N2VCJujuConnector = asynctest.MagicMock(ns.N2VCJujuConnector)
            ns.LCMHelmConn = asynctest.MagicMock(ns.LCMHelmConn)

    def create_nslcm_class(self):
        self.my_ns = ns.NsLcm(self.msg, self.lcm_tasks, lcm_config)
        self.my_ns.fs = self.fs
        self.my_ns.db = self.db
        self.my_ns._wait_dependent_n2vc = asynctest.CoroutineMock()

    def mock_logging(self):
        if not getenv("OSMLCMTEST_LOGGING_NOMOCK"):
            self.my_ns.logger = asynctest.Mock(self.my_ns.logger)

    def mock_vca_n2vc(self):
        if not getenv("OSMLCMTEST_VCA_NOMOCK"):
            pub_key = getenv("OSMLCMTEST_NS_PUBKEY", "ssh-rsa test-pub-key t@osm.com")
            # self.my_ns.n2vc = asynctest.Mock(N2VC())
            self.my_ns.n2vc.GetPublicKey.return_value = getenv(
                "OSMLCM_VCA_PUBKEY", "public_key"
            )
            # allow several versions of n2vc
            self.my_ns.n2vc.FormatApplicationName = asynctest.Mock(
                side_effect=self._n2vc_FormatApplicationName()
            )
            self.my_ns.n2vc.DeployCharms = asynctest.CoroutineMock(
                side_effect=self._n2vc_DeployCharms
            )
            self.my_ns.n2vc.create_execution_environment = asynctest.CoroutineMock(
                side_effect=self._n2vc_CreateExecutionEnvironment
            )
            self.my_ns.n2vc.install_configuration_sw = asynctest.CoroutineMock(
                return_value=pub_key
            )
            self.my_ns.n2vc.get_ee_ssh_public__key = asynctest.CoroutineMock(
                return_value=pub_key
            )
            self.my_ns.n2vc.exec_primitive = asynctest.CoroutineMock(
                side_effect=self._return_uuid
            )
            self.my_ns.n2vc.exec_primitive = asynctest.CoroutineMock(
                side_effect=self._return_uuid
            )
            self.my_ns.n2vc.GetPrimitiveStatus = asynctest.CoroutineMock(
                return_value="completed"
            )
            self.my_ns.n2vc.GetPrimitiveOutput = asynctest.CoroutineMock(
                return_value={"result": "ok", "pubkey": pub_key}
            )
            self.my_ns.n2vc.delete_execution_environment = asynctest.CoroutineMock(
                return_value=None
            )
            self.my_ns.n2vc.get_public_key = asynctest.CoroutineMock(
                return_value=getenv("OSMLCM_VCA_PUBKEY", "public_key")
            )
            self.my_ns.n2vc.delete_namespace = asynctest.CoroutineMock(
                return_value=None
            )
            self.my_ns.n2vc.register_execution_environment = asynctest.CoroutineMock(
                return_value="model-name.application-name.k8s"
            )

    def mock_ro(self):
        if not getenv("OSMLCMTEST_RO_NOMOCK"):
            self.my_ns.RO = asynctest.Mock(NgRoClient(**lcm_config.RO.to_dict()))
            # TODO first time should be empty list, following should return a dict
            # self.my_ns.RO.get_list = asynctest.CoroutineMock(self.my_ns.RO.get_list, return_value=[])
            self.my_ns.RO.deploy = asynctest.CoroutineMock(
                self.my_ns.RO.deploy, side_effect=self._ro_deploy
            )
            # self.my_ns.RO.status = asynctest.CoroutineMock(self.my_ns.RO.status, side_effect=self._ro_status)
            # self.my_ns.RO.create_action = asynctest.CoroutineMock(self.my_ns.RO.create_action,
            #                                                      return_value={"vm-id": {"vim_result": 200,
            #                                                                              "description": "done"}})
            self.my_ns.RO.delete = asynctest.CoroutineMock(self.my_ns.RO.delete)


class TestMyNS(TestBaseNS):
    @asynctest.fail_on(active_handles=True)
    async def test_start_stop_rebuild_pass(self):
        nsr_id = descriptors.test_ids["TEST-OP-VNF"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-OP-VNF"]["nslcmops"]
        vnf_id = descriptors.test_ids["TEST-OP-VNF"]["vnfrs"]
        additional_param = {"count-index": "0"}
        operation_type = "start"
        await self.my_ns.rebuild_start_stop(
            nsr_id, nslcmop_id, vnf_id, additional_param, operation_type
        )
        expected_value = "COMPLETED"
        return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        self.assertEqual(return_value, expected_value)

    @asynctest.fail_on(active_handles=True)
    async def test_start_stop_rebuild_fail(self):
        nsr_id = descriptors.test_ids["TEST-OP-VNF"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-OP-VNF"]["nslcmops1"]
        vnf_id = descriptors.test_ids["TEST-OP-VNF"]["vnfrs"]
        additional_param = {"count-index": "0"}
        operation_type = "stop"
        await self.my_ns.rebuild_start_stop(
            nsr_id, nslcmop_id, vnf_id, additional_param, operation_type
        )
        expected_value = "Error"
        return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        self.assertEqual(return_value, expected_value)

    # Test scale() and related methods
    @asynctest.fail_on(active_handles=True)  # all async tasks must be completed
    async def test_scale(self):
        # print("Test scale started")

        # TODO: Add more higher-lever tests here, for example:
        # scale-out/scale-in operations with success/error result

        # Test scale() with missing 'scaleVnfData', should return operationState = 'FAILED'
        nsr_id = descriptors.test_ids["TEST-A"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        await self.my_ns.scale(nsr_id, nslcmop_id)
        expected_value = "FAILED"
        return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        self.assertEqual(return_value, expected_value)
        # print("scale_result: {}".format(self.db.get_one("nslcmops", {"_id": nslcmop_id}).get("detailed-status")))

        # Test scale() for native kdu
        # this also includes testing _scale_kdu()
        nsr_id = descriptors.test_ids["TEST-NATIVE-KDU"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-NATIVE-KDU"]["instantiate"]

        self.my_ns.k8sclusterjuju.scale = asynctest.mock.CoroutineMock()
        self.my_ns.k8sclusterjuju.exec_primitive = asynctest.mock.CoroutineMock()
        self.my_ns.k8sclusterjuju.get_scale_count = asynctest.mock.CoroutineMock(
            return_value=1
        )
        await self.my_ns.scale(nsr_id, nslcmop_id)
        expected_value = "COMPLETED"
        return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        self.assertEqual(return_value, expected_value)
        self.my_ns.k8sclusterjuju.scale.assert_called_once()

        # Test scale() for native kdu with 2 resource
        nsr_id = descriptors.test_ids["TEST-NATIVE-KDU-2"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-NATIVE-KDU-2"]["instantiate"]

        self.my_ns.k8sclusterjuju.get_scale_count.return_value = 2
        await self.my_ns.scale(nsr_id, nslcmop_id)
        expected_value = "COMPLETED"
        return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        self.assertEqual(return_value, expected_value)
        self.my_ns.k8sclusterjuju.scale.assert_called()

    async def test_vca_status_refresh(self):
        nsr_id = descriptors.test_ids["TEST-A"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        await self.my_ns.vca_status_refresh(nsr_id, nslcmop_id)
        expected_value = dict()
        return_value = dict()
        vnf_descriptors = self.db.get_list("vnfds")
        for i, _ in enumerate(vnf_descriptors):
            for j, value in enumerate(vnf_descriptors[i]["df"]):
                if "lcm-operations-configuration" in vnf_descriptors[i]["df"][j]:
                    if (
                        "day1-2"
                        in value["lcm-operations-configuration"][
                            "operate-vnf-op-config"
                        ]
                    ):
                        for k, v in enumerate(
                            value["lcm-operations-configuration"][
                                "operate-vnf-op-config"
                            ]["day1-2"]
                        ):
                            if (
                                v.get("execution-environment-list")
                                and "juju" in v["execution-environment-list"][0]
                            ):
                                expected_value = self.db.get_list("nsrs")[i][
                                    "vcaStatus"
                                ]
                                await self.my_ns._on_update_n2vc_db(
                                    "nsrs",
                                    {"_id": nsr_id},
                                    "_admin.deployed.VCA.{}".format(k),
                                    {},
                                )
                                return_value = self.db.get_list("nsrs")[i]["vcaStatus"]
        self.assertEqual(return_value, expected_value)

    # Test _retry_or_skip_suboperation()
    # Expected result:
    # - if a suboperation's 'operationState' is marked as 'COMPLETED', SUBOPERATION_STATUS_SKIP is expected
    # - if marked as anything but 'COMPLETED', the suboperation index is expected
    def test_scale_retry_or_skip_suboperation(self):
        # Load an alternative 'nslcmops' YAML for this test
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
        op_index = 2
        # Test when 'operationState' is 'COMPLETED'
        db_nslcmop["_admin"]["operations"][op_index]["operationState"] = "COMPLETED"
        return_value = self.my_ns._retry_or_skip_suboperation(db_nslcmop, op_index)
        expected_value = self.my_ns.SUBOPERATION_STATUS_SKIP
        self.assertEqual(return_value, expected_value)
        # Test when 'operationState' is not 'COMPLETED'
        db_nslcmop["_admin"]["operations"][op_index]["operationState"] = None
        return_value = self.my_ns._retry_or_skip_suboperation(db_nslcmop, op_index)
        expected_value = op_index
        self.assertEqual(return_value, expected_value)

    # Test _find_suboperation()
    # Expected result: index of the found sub-operation, or SUBOPERATION_STATUS_NOT_FOUND if not found
    def test_scale_find_suboperation(self):
        # Load an alternative 'nslcmops' YAML for this test
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
        # Find this sub-operation
        op_index = 2
        vnf_index = db_nslcmop["_admin"]["operations"][op_index]["member_vnf_index"]
        primitive = db_nslcmop["_admin"]["operations"][op_index]["primitive"]
        primitive_params = db_nslcmop["_admin"]["operations"][op_index][
            "primitive_params"
        ]
        match = {
            "member_vnf_index": vnf_index,
            "primitive": primitive,
            "primitive_params": primitive_params,
        }
        found_op_index = self.my_ns._find_suboperation(db_nslcmop, match)
        self.assertEqual(found_op_index, op_index)
        # Test with not-matching params
        match = {
            "member_vnf_index": vnf_index,
            "primitive": "",
            "primitive_params": primitive_params,
        }
        found_op_index = self.my_ns._find_suboperation(db_nslcmop, match)
        self.assertEqual(found_op_index, self.my_ns.SUBOPERATION_STATUS_NOT_FOUND)
        # Test with None
        match = None
        found_op_index = self.my_ns._find_suboperation(db_nslcmop, match)
        self.assertEqual(found_op_index, self.my_ns.SUBOPERATION_STATUS_NOT_FOUND)

    # Test _update_suboperation_status()
    def test_scale_update_suboperation_status(self):
        self.db.set_one = asynctest.Mock()
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
        op_index = 0
        # Force the initial values to be distinct from the updated ones
        q_filter = {"_id": db_nslcmop["_id"]}
        # Test to change 'operationState' and 'detailed-status'
        operationState = "COMPLETED"
        detailed_status = "Done"
        expected_update_dict = {
            "_admin.operations.0.operationState": operationState,
            "_admin.operations.0.detailed-status": detailed_status,
        }
        self.my_ns._update_suboperation_status(
            db_nslcmop, op_index, operationState, detailed_status
        )
        self.db.set_one.assert_called_once_with(
            "nslcmops",
            q_filter=q_filter,
            update_dict=expected_update_dict,
            fail_on_empty=False,
        )

    def test_scale_add_suboperation(self):
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
        vnf_index = "1"
        num_ops_before = len(db_nslcmop.get("_admin", {}).get("operations", [])) - 1
        vdu_id = None
        vdu_count_index = None
        vdu_name = None
        primitive = "touch"
        mapped_primitive_params = {
            "parameter": [
                {
                    "data-type": "STRING",
                    "name": "filename",
                    "default-value": "<touch_filename2>",
                }
            ],
            "name": "touch",
        }
        operationState = "PROCESSING"
        detailed_status = "In progress"
        operationType = "PRE-SCALE"
        # Add a 'pre-scale' suboperation
        op_index_after = self.my_ns._add_suboperation(
            db_nslcmop,
            vnf_index,
            vdu_id,
            vdu_count_index,
            vdu_name,
            primitive,
            mapped_primitive_params,
            operationState,
            detailed_status,
            operationType,
        )
        self.assertEqual(op_index_after, num_ops_before + 1)

        # Delete all suboperations and add the same operation again
        del db_nslcmop["_admin"]["operations"]
        op_index_zero = self.my_ns._add_suboperation(
            db_nslcmop,
            vnf_index,
            vdu_id,
            vdu_count_index,
            vdu_name,
            primitive,
            mapped_primitive_params,
            operationState,
            detailed_status,
            operationType,
        )
        self.assertEqual(op_index_zero, 0)

        # Add a 'RO' suboperation
        RO_nsr_id = "1234567890"
        RO_scaling_info = [
            {
                "type": "create",
                "count": 1,
                "member-vnf-index": "1",
                "osm_vdu_id": "dataVM",
            }
        ]
        op_index = self.my_ns._add_suboperation(
            db_nslcmop,
            vnf_index,
            vdu_id,
            vdu_count_index,
            vdu_name,
            primitive,
            mapped_primitive_params,
            operationState,
            detailed_status,
            operationType,
            RO_nsr_id,
            RO_scaling_info,
        )
        db_RO_nsr_id = db_nslcmop["_admin"]["operations"][op_index]["RO_nsr_id"]
        self.assertEqual(op_index, 1)
        self.assertEqual(RO_nsr_id, db_RO_nsr_id)

        # Try to add an invalid suboperation, should return SUBOPERATION_STATUS_NOT_FOUND
        op_index_invalid = self.my_ns._add_suboperation(
            None, None, None, None, None, None, None, None, None, None, None
        )
        self.assertEqual(op_index_invalid, self.my_ns.SUBOPERATION_STATUS_NOT_FOUND)

    # Test _check_or_add_scale_suboperation() and _check_or_add_scale_suboperation_RO()
    # check the possible return values:
    # - SUBOPERATION_STATUS_NEW: This is a new sub-operation
    # - op_index (non-negative number): This is an existing sub-operation, operationState != 'COMPLETED'
    # - SUBOPERATION_STATUS_SKIP: This is an existing sub-operation, operationState == 'COMPLETED'
    def test_scale_check_or_add_scale_suboperation(self):
        nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
        db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
        operationType = "PRE-SCALE"
        vnf_index = "1"
        primitive = "touch"
        primitive_params = {
            "parameter": [
                {
                    "data-type": "STRING",
                    "name": "filename",
                    "default-value": "<touch_filename2>",
                }
            ],
            "name": "touch",
        }

        # Delete all sub-operations to be sure this is a new sub-operation
        del db_nslcmop["_admin"]["operations"]

        # Add a new sub-operation
        # For new sub-operations, operationState is set to 'PROCESSING' by default
        op_index_new = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, primitive, primitive_params, operationType
        )
        self.assertEqual(op_index_new, self.my_ns.SUBOPERATION_STATUS_NEW)

        # Use the same parameters again to match the already added sub-operation
        # which has status 'PROCESSING' (!= 'COMPLETED') by default
        # The expected return value is a non-negative number
        op_index_existing = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, primitive, primitive_params, operationType
        )
        self.assertTrue(op_index_existing >= 0)

        # Change operationState 'manually' for this sub-operation
        db_nslcmop["_admin"]["operations"][op_index_existing][
            "operationState"
        ] = "COMPLETED"
        # Then use the same parameters again to match the already added sub-operation,
        # which now has status 'COMPLETED'
        # The expected return value is SUBOPERATION_STATUS_SKIP
        op_index_skip = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, primitive, primitive_params, operationType
        )
        self.assertEqual(op_index_skip, self.my_ns.SUBOPERATION_STATUS_SKIP)

        # RO sub-operation test:
        # Repeat tests for the very similar _check_or_add_scale_suboperation_RO(),
        RO_nsr_id = "1234567890"
        RO_scaling_info = [
            {
                "type": "create",
                "count": 1,
                "member-vnf-index": "1",
                "osm_vdu_id": "dataVM",
            }
        ]
        op_index_new_RO = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, None, None, "SCALE-RO", RO_nsr_id, RO_scaling_info
        )
        self.assertEqual(op_index_new_RO, self.my_ns.SUBOPERATION_STATUS_NEW)

        # Use the same parameters again to match the already added RO sub-operation
        op_index_existing_RO = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, None, None, "SCALE-RO", RO_nsr_id, RO_scaling_info
        )
        self.assertTrue(op_index_existing_RO >= 0)

        # Change operationState 'manually' for this RO sub-operation
        db_nslcmop["_admin"]["operations"][op_index_existing_RO][
            "operationState"
        ] = "COMPLETED"
        # Then use the same parameters again to match the already added sub-operation,
        # which now has status 'COMPLETED'
        # The expected return value is SUBOPERATION_STATUS_SKIP
        op_index_skip_RO = self.my_ns._check_or_add_scale_suboperation(
            db_nslcmop, vnf_index, None, None, "SCALE-RO", RO_nsr_id, RO_scaling_info
        )
        self.assertEqual(op_index_skip_RO, self.my_ns.SUBOPERATION_STATUS_SKIP)

    async def test_deploy_kdus(self):
        nsr_id = descriptors.test_ids["TEST-KDU"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-KDU"]["instantiate"]
        db_nsr = self.db.get_one("nsrs", {"_id": nsr_id})
        db_vnfr = self.db.get_one(
            "vnfrs", {"nsr-id-ref": nsr_id, "member-vnf-index-ref": "multikdu"}
        )
        db_vnfrs = {"multikdu": db_vnfr}
        db_vnfd = self.db.get_one("vnfds", {"_id": db_vnfr["vnfd-id"]})
        db_vnfds = [db_vnfd]
        task_register = {}
        logging_text = "KDU"
        self.my_ns.k8sclusterhelm3.generate_kdu_instance_name = asynctest.mock.Mock()
        self.my_ns.k8sclusterhelm3.generate_kdu_instance_name.return_value = "k8s_id"
        self.my_ns.k8sclusterhelm3.install = asynctest.CoroutineMock()
        self.my_ns.k8sclusterhelm3.synchronize_repos = asynctest.CoroutineMock(
            return_value=("", "")
        )
        self.my_ns.k8sclusterhelm3.get_services = asynctest.CoroutineMock(
            return_value=([])
        )
        await self.my_ns.deploy_kdus(
            logging_text, nsr_id, nslcmop_id, db_vnfrs, db_vnfds, task_register
        )
        await asyncio.wait(list(task_register.keys()), timeout=100)
        db_nsr = self.db.get_list("nsrs")[1]
        self.assertIn(
            "K8s",
            db_nsr["_admin"]["deployed"],
            "K8s entry not created at '_admin.deployed'",
        )
        self.assertIsInstance(
            db_nsr["_admin"]["deployed"]["K8s"], list, "K8s entry is not of type list"
        )
        self.assertEqual(
            len(db_nsr["_admin"]["deployed"]["K8s"]), 2, "K8s entry is not of type list"
        )
        k8s_instace_info = {
            "kdu-instance": "k8s_id",
            "k8scluster-uuid": "73d96432-d692-40d2-8440-e0c73aee209c",
            "k8scluster-type": "helm-chart-v3",
            "kdu-name": "ldap",
            "member-vnf-index": "multikdu",
            "namespace": None,
            "kdu-deployment-name": None,
        }

        nsr_result = copy.deepcopy(db_nsr["_admin"]["deployed"]["K8s"][0])
        nsr_kdu_model_result = nsr_result.pop("kdu-model")
        expected_kdu_model = "stable/openldap:1.2.1"
        self.assertEqual(nsr_result, k8s_instace_info)
        self.assertTrue(
            nsr_kdu_model_result in expected_kdu_model
            or expected_kdu_model in nsr_kdu_model_result
        )
        nsr_result = copy.deepcopy(db_nsr["_admin"]["deployed"]["K8s"][1])
        nsr_kdu_model_result = nsr_result.pop("kdu-model")
        k8s_instace_info["kdu-name"] = "mongo"
        expected_kdu_model = "stable/mongodb"
        self.assertEqual(nsr_result, k8s_instace_info)
        self.assertTrue(
            nsr_kdu_model_result in expected_kdu_model
            or expected_kdu_model in nsr_kdu_model_result
        )

    # Test remove_vnf() and related methods
    @asynctest.fail_on(active_handles=True)  # all async tasks must be completed
    async def test_remove_vnf(self):
        # Test REMOVE_VNF
        nsr_id = descriptors.test_ids["TEST-UPDATE"]["ns"]
        nslcmop_id = descriptors.test_ids["TEST-UPDATE"]["removeVnf"]
        vnf_instance_id = descriptors.test_ids["TEST-UPDATE"]["vnf"]
        mock_wait_ng_ro = asynctest.CoroutineMock()
        with patch("osm_lcm.ns.NsLcm._wait_ng_ro", mock_wait_ng_ro):
            await self.my_ns.update(nsr_id, nslcmop_id)
            expected_value = "COMPLETED"
            return_value = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
                "operationState"
            )
            self.assertEqual(return_value, expected_value)
            with self.assertRaises(Exception) as context:
                self.db.get_one("vnfrs", {"_id": vnf_instance_id})
            self.assertTrue(
                "database exception Not found entry with filter"
                in str(context.exception)
            )

    # async def test_instantiate_pdu(self):
    #     nsr_id = descriptors.test_ids["TEST-A"]["ns"]
    #     nslcmop_id = descriptors.test_ids["TEST-A"]["instantiate"]
    #     # Modify vnfd/vnfr to change KDU for PDU. Adding keys that NBI will already set
    #     self.db.set_one("vnfrs", {"nsr-id-ref": nsr_id, "member-vnf-index-ref": "1"},
    #                     update_dict={"ip-address": "10.205.1.46",
    #                                  "vdur.0.pdu-id": "53e1ec21-2464-451e-a8dc-6e311d45b2c8",
    #                                  "vdur.0.pdu-type": "PDU-TYPE-1",
    #                                  "vdur.0.ip-address": "10.205.1.46",
    #                                  },
    #                     unset={"vdur.status": None})
    #     self.db.set_one("vnfrs", {"nsr-id-ref": nsr_id, "member-vnf-index-ref": "2"},
    #                     update_dict={"ip-address": "10.205.1.47",
    #                                  "vdur.0.pdu-id": "53e1ec21-2464-451e-a8dc-6e311d45b2c8",
    #                                  "vdur.0.pdu-type": "PDU-TYPE-1",
    #                                  "vdur.0.ip-address": "10.205.1.47",
    #                                  },
    #                     unset={"vdur.status": None})

    #     await self.my_ns.instantiate(nsr_id, nslcmop_id)
    #     db_nsr = self.db.get_one("nsrs", {"_id": nsr_id})
    #     self.assertEqual(db_nsr.get("nsState"), "READY", str(db_nsr.get("errorDescription ")))
    #     self.assertEqual(db_nsr.get("currentOperation"), "IDLE", "currentOperation different than 'IDLE'")
    #     self.assertEqual(db_nsr.get("currentOperationID"), None, "currentOperationID different than None")
    #     self.assertEqual(db_nsr.get("errorDescription "), None, "errorDescription different than None")
    #     self.assertEqual(db_nsr.get("errorDetail"), None, "errorDetail different than None")

    # @asynctest.fail_on(active_handles=True)   # all async tasks must be completed
    # async def test_terminate_without_configuration(self):
    #     nsr_id = descriptors.test_ids["TEST-A"]["ns"]
    #     nslcmop_id = descriptors.test_ids["TEST-A"]["terminate"]
    #     # set instantiation task as completed
    #     self.db.set_list("nslcmops", {"nsInstanceId": nsr_id, "_id.ne": nslcmop_id},
    #                      update_dict={"operationState": "COMPLETED"})
    #     self.db.set_one("nsrs", {"_id": nsr_id},
    #                     update_dict={"_admin.deployed.VCA.0": None, "_admin.deployed.VCA.1": None})

    #     await self.my_ns.terminate(nsr_id, nslcmop_id)
    #     db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
    #     self.assertEqual(db_nslcmop.get("operationState"), 'COMPLETED', db_nslcmop.get("detailed-status"))
    #     db_nsr = self.db.get_one("nsrs", {"_id": nsr_id})
    #     self.assertEqual(db_nsr.get("nsState"), "NOT_INSTANTIATED", str(db_nsr.get("errorDescription ")))
    #     self.assertEqual(db_nsr["_admin"].get("nsState"), "NOT_INSTANTIATED", str(db_nsr.get("errorDescription ")))
    #     self.assertEqual(db_nsr.get("currentOperation"), "IDLE", "currentOperation different than 'IDLE'")
    #     self.assertEqual(db_nsr.get("currentOperationID"), None, "currentOperationID different than None")
    #     self.assertEqual(db_nsr.get("errorDescription "), None, "errorDescription different than None")
    #     self.assertEqual(db_nsr.get("errorDetail"), None, "errorDetail different than None")
    #     db_vnfrs_list = self.db.get_list("vnfrs", {"nsr-id-ref": nsr_id})
    #     for vnfr in db_vnfrs_list:
    #         self.assertEqual(vnfr["_admin"].get("nsState"), "NOT_INSTANTIATED", "Not instantiated")

    # @asynctest.fail_on(active_handles=True)   # all async tasks must be completed
    # async def test_terminate_primitive(self):
    #     nsr_id = descriptors.test_ids["TEST-A"]["ns"]
    #     nslcmop_id = descriptors.test_ids["TEST-A"]["terminate"]
    #     # set instantiation task as completed
    #     self.db.set_list("nslcmops", {"nsInstanceId": nsr_id, "_id.ne": nslcmop_id},
    #                      update_dict={"operationState": "COMPLETED"})

    #     # modify vnfd descriptor to include terminate_primitive
    #     terminate_primitive = [{
    #         "name": "touch",
    #         "parameter": [{"name": "filename", "value": "terminate_filename"}],
    #         "seq": '1'
    #     }]
    #     db_vnfr = self.db.get_one("vnfrs", {"nsr-id-ref": nsr_id, "member-vnf-index-ref": "1"})
    #     self.db.set_one("vnfds", {"_id": db_vnfr["vnfd-id"]},
    #                     {"vnf-configuration.0.terminate-config-primitive": terminate_primitive})

    #     await self.my_ns.terminate(nsr_id, nslcmop_id)
    #     db_nslcmop = self.db.get_one("nslcmops", {"_id": nslcmop_id})
    #     self.assertEqual(db_nslcmop.get("operationState"), 'COMPLETED', db_nslcmop.get("detailed-status"))
    #     db_nsr = self.db.get_one("nsrs", {"_id": nsr_id})
    #     self.assertEqual(db_nsr.get("nsState"), "NOT_INSTANTIATED", str(db_nsr.get("errorDescription ")))
    #     self.assertEqual(db_nsr["_admin"].get("nsState"), "NOT_INSTANTIATED", str(db_nsr.get("errorDescription ")))
    #     self.assertEqual(db_nsr.get("currentOperation"), "IDLE", "currentOperation different than 'IDLE'")
    #     self.assertEqual(db_nsr.get("currentOperationID"), None, "currentOperationID different than None")
    #     self.assertEqual(db_nsr.get("errorDescription "), None, "errorDescription different than None")
    #     self.assertEqual(db_nsr.get("errorDetail"), None, "errorDetail different than None")

    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    @patch("osm_lcm.data_utils.vnfd.find_software_version")
    @patch("osm_lcm.lcm_utils.check_juju_bundle_existence")
    async def test_update_change_vnfpkg_sw_version_not_changed(
        self,
        mock_juju_bundle,
        mock_software_version,
        mock_charm_upgrade,
        mock_charm_hash,
    ):
        """Update type: CHANGE_VNFPKG, latest_vnfd revision changed,
        Charm package changed, sw-version is not changed"""
        self.db.set_one(
            "vnfds",
            q_filter={"_id": vnfd_id},
            update_dict={"_admin.revision": 3, "kdu": []},
        )

        self.db.set_one(
            "vnfds_revisions",
            q_filter={"_id": vnfd_id + ":1"},
            update_dict={"_admin.revision": 1, "kdu": []},
        )

        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})

        mock_charm_hash.return_value = True
        mock_software_version.side_effect = ["1.0", "1.0"]

        task = asyncio.Future()
        task.set_result(("COMPLETED", "some_output"))
        mock_charm_upgrade.return_value = task

        instance = self.my_ns
        fs = deepcopy(update_fs)
        instance.fs = fs

        expected_operation_state = "COMPLETED"
        expected_operation_error = ""
        expected_vnfr_revision = 3
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_operation_state = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        return_operation_error = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "errorMessage"
        )
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        mock_charm_hash.assert_called_with(
            f"{vnfd_id}:1/hackfest_3charmed_vnfd/charms/simple",
            f"{vnfd_id}:3/hackfest_3charmed_vnfd/charms/simple",
        )
        self.assertEqual(fs.sync.call_count, 2)
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_operation_state, expected_operation_state)
        self.assertEqual(return_operation_error, expected_operation_error)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    @patch("osm_lcm.data_utils.vnfd.find_software_version")
    @patch("osm_lcm.lcm_utils.check_juju_bundle_existence")
    async def test_update_change_vnfpkg_vnfd_revision_not_changed(
        self,
        mock_juju_bundle,
        mock_software_version,
        mock_charm_upgrade,
        mock_charm_hash,
    ):
        """Update type: CHANGE_VNFPKG, latest_vnfd revision not changed"""
        self.db.set_one(
            "vnfds", q_filter={"_id": vnfd_id}, update_dict={"_admin.revision": 1}
        )
        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})

        mock_charm_hash.return_value = True

        task = asyncio.Future()
        task.set_result(("COMPLETED", "some_output"))
        mock_charm_upgrade.return_value = task

        instance = self.my_ns

        expected_operation_state = "COMPLETED"
        expected_operation_error = ""
        expected_vnfr_revision = 1
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_operation_state = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        return_operation_error = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "errorMessage"
        )
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        mock_charm_hash.assert_not_called()
        mock_software_version.assert_not_called()
        mock_juju_bundle.assert_not_called()
        mock_charm_upgrade.assert_not_called()
        update_fs.sync.assert_not_called()
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_operation_state, expected_operation_state)
        self.assertEqual(return_operation_error, expected_operation_error)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    @patch("osm_lcm.data_utils.vnfd.find_software_version")
    @patch("osm_lcm.lcm_utils.check_juju_bundle_existence")
    async def test_update_change_vnfpkg_charm_is_not_changed(
        self,
        mock_juju_bundle,
        mock_software_version,
        mock_charm_upgrade,
        mock_charm_hash,
    ):
        """Update type: CHANGE_VNFPKG, latest_vnfd revision changed
        Charm package is not changed, sw-version is not changed"""
        self.db.set_one(
            "vnfds",
            q_filter={"_id": vnfd_id},
            update_dict={"_admin.revision": 3, "kdu": []},
        )
        self.db.set_one(
            "vnfds_revisions",
            q_filter={"_id": vnfd_id + ":1"},
            update_dict={"_admin.revision": 1, "kdu": []},
        )
        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})

        mock_charm_hash.return_value = False
        mock_software_version.side_effect = ["1.0", "1.0"]

        instance = self.my_ns
        fs = deepcopy(update_fs)
        instance.fs = fs
        expected_operation_state = "COMPLETED"
        expected_operation_error = ""
        expected_vnfr_revision = 3
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_operation_state = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        return_operation_error = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "errorMessage"
        )
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        mock_charm_hash.assert_called_with(
            f"{vnfd_id}:1/hackfest_3charmed_vnfd/charms/simple",
            f"{vnfd_id}:3/hackfest_3charmed_vnfd/charms/simple",
        )
        self.assertEqual(fs.sync.call_count, 2)
        self.assertEqual(mock_charm_hash.call_count, 1)
        mock_juju_bundle.assert_not_called()
        mock_charm_upgrade.assert_not_called()
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_operation_state, expected_operation_state)
        self.assertEqual(return_operation_error, expected_operation_error)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    @patch("osm_lcm.lcm_utils.check_juju_bundle_existence")
    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    @patch("osm_lcm.lcm_utils.get_charm_artifact_path")
    async def test_update_change_vnfpkg_sw_version_changed(
        self, mock_charm_artifact, mock_charm_upgrade, mock_charm_hash, mock_juju_bundle
    ):
        """Update type: CHANGE_VNFPKG, latest_vnfd revision changed
        Charm package exists, sw-version changed."""
        self.db.set_one(
            "vnfds",
            q_filter={"_id": vnfd_id},
            update_dict={"_admin.revision": 3, "software-version": "3.0", "kdu": []},
        )
        self.db.set_one(
            "vnfds_revisions",
            q_filter={"_id": vnfd_id + ":1"},
            update_dict={"_admin.revision": 1, "kdu": []},
        )
        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})
        mock_charm_hash.return_value = False

        mock_charm_artifact.side_effect = [
            f"{vnfd_id}:1/hackfest_3charmed_vnfd/charms/simple",
            f"{vnfd_id}:3/hackfest_3charmed_vnfd/charms/simple",
        ]

        instance = self.my_ns
        fs = deepcopy(update_fs)
        instance.fs = fs
        expected_operation_state = "FAILED"
        expected_operation_error = "FAILED Checking if existing VNF has charm: Software version change is not supported as VNF instance 6421c7c9-d865-4fb4-9a13-d4275d243e01 has charm."
        expected_vnfr_revision = 1
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_operation_state = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        return_operation_error = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "errorMessage"
        )
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        self.assertEqual(fs.sync.call_count, 2)
        mock_charm_hash.assert_not_called()
        mock_juju_bundle.assert_not_called()
        mock_charm_upgrade.assert_not_called()
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_operation_state, expected_operation_state)
        self.assertEqual(return_operation_error, expected_operation_error)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    @patch("osm_lcm.lcm_utils.check_juju_bundle_existence")
    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    @patch("osm_lcm.data_utils.vnfd.find_software_version")
    async def test_update_change_vnfpkg_juju_bundle_exists(
        self,
        mock_software_version,
        mock_charm_upgrade,
        mock_charm_hash,
        mock_juju_bundle,
    ):
        """Update type: CHANGE_VNFPKG, latest_vnfd revision changed
        Charm package exists, sw-version not changed, juju-bundle exists"""
        # Upgrade is not allowed with juju bundles, this will cause TypeError
        self.db.set_one(
            "vnfds",
            q_filter={"_id": vnfd_id},
            update_dict={
                "_admin.revision": 5,
                "software-version": "1.0",
                "kdu": [{"kdu_name": "native-kdu", "juju-bundle": "stable/native-kdu"}],
            },
        )
        self.db.set_one(
            "vnfds_revisions",
            q_filter={"_id": vnfd_id + ":1"},
            update_dict={
                "_admin.revision": 1,
                "software-version": "1.0",
                "kdu": [{"kdu_name": "native-kdu", "juju-bundle": "stable/native-kdu"}],
            },
        )
        self.db.set_one(
            "nsrs",
            q_filter={"_id": nsr_id},
            update_dict={"_admin.deployed.VCA.0.kdu_name": "native-kdu"},
        )
        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})

        mock_charm_hash.side_effect = [True]
        mock_software_version.side_effect = ["1.0", "1.0"]
        mock_juju_bundle.return_value = True
        instance = self.my_ns
        fs = deepcopy(update_fs)
        instance.fs = fs

        expected_vnfr_revision = 1
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        self.assertEqual(fs.sync.call_count, 2)
        mock_charm_upgrade.assert_not_called()
        mock_charm_hash.assert_not_called()
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    @patch("osm_lcm.lcm_utils.LcmBase.check_charm_hash_changed")
    @patch(
        "osm_lcm.ns.NsLcm._ns_charm_upgrade", new_callable=asynctest.Mock(autospec=True)
    )
    async def test_update_change_vnfpkg_charm_upgrade_failed(
        self, mock_charm_upgrade, mock_charm_hash
    ):
        """ "Update type: CHANGE_VNFPKG, latest_vnfd revision changed"
        Charm package exists, sw-version not changed, charm-upgrade failed"""
        self.db.set_one(
            "vnfds",
            q_filter={"_id": vnfd_id},
            update_dict={"_admin.revision": 3, "software-version": "1.0", "kdu": []},
        )
        self.db.set_one(
            "vnfds_revisions",
            q_filter={"_id": vnfd_id + ":1"},
            update_dict={"_admin.revision": 1, "software-version": "1.0", "kdu": []},
        )
        self.db.set_one("vnfrs", q_filter={"_id": vnfr_id}, update_dict={"revision": 1})

        mock_charm_hash.return_value = True

        task = asyncio.Future()
        task.set_result(("FAILED", "some_error"))
        mock_charm_upgrade.return_value = task

        instance = self.my_ns
        fs = deepcopy(update_fs)
        instance.fs = fs
        expected_operation_state = "FAILED"
        expected_operation_error = "some_error"
        expected_vnfr_revision = 1
        expected_ns_state = "INSTANTIATED"
        expected_ns_operational_state = "running"

        await instance.update(nsr_id, nslcmop_id)
        return_operation_state = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "operationState"
        )
        return_operation_error = self.db.get_one("nslcmops", {"_id": nslcmop_id}).get(
            "errorMessage"
        )
        return_ns_operational_state = self.db.get_one("nsrs", {"_id": nsr_id}).get(
            "operational-status"
        )
        return_vnfr_revision = self.db.get_one("vnfrs", {"_id": vnfr_id}).get(
            "revision"
        )
        return_ns_state = self.db.get_one("nsrs", {"_id": nsr_id}).get("nsState")
        self.assertEqual(fs.sync.call_count, 2)
        self.assertEqual(mock_charm_hash.call_count, 1)
        self.assertEqual(mock_charm_upgrade.call_count, 1)
        self.assertEqual(return_ns_state, expected_ns_state)
        self.assertEqual(return_operation_state, expected_operation_state)
        self.assertEqual(return_operation_error, expected_operation_error)
        self.assertEqual(return_ns_operational_state, expected_ns_operational_state)
        self.assertEqual(return_vnfr_revision, expected_vnfr_revision)

    def test_ns_update_find_sw_version_vnfd_not_includes(self):
        """Find software version, VNFD does not have software version"""

        db_vnfd = self.db.get_one("vnfds", {"_id": vnfd_id})
        expected_result = "1.0"
        result = find_software_version(db_vnfd)
        self.assertEqual(result, expected_result, "Default sw version should be 1.0")

    def test_ns_update_find_sw_version_vnfd_includes(self):
        """Find software version, VNFD includes software version"""

        db_vnfd = self.db.get_one("vnfds", {"_id": vnfd_id})
        db_vnfd["software-version"] = "3.1"
        expected_result = "3.1"
        result = find_software_version(db_vnfd)
        self.assertEqual(result, expected_result, "VNFD software version is wrong")

    @patch("os.path.exists")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charmdir_hash")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charm_hash")
    def test_ns_update_check_charm_hash_not_changed(
        self, mock_compare_charm_hash, mock_compare_charmdir_hash, mock_path_exists
    ):
        """Check charm hash, Hash did not change"""

        current_path, target_path = "/tmp/charm1", "/tmp/charm1"

        fs = Mock()
        fs.path.__add__ = Mock()
        fs.path.side_effect = [current_path, target_path]
        fs.path.__add__.side_effect = [current_path, target_path]

        mock_path_exists.side_effect = [True, True]

        mock_compare_charmdir_hash.return_value = callable(False)
        mock_compare_charm_hash.return_value = callable(False)

        instance = self.my_ns
        instance.fs = fs
        expected_result = False

        result = instance.check_charm_hash_changed(current_path, target_path)
        self.assertEqual(result, expected_result, "Wrong charm hash control value")
        self.assertEqual(mock_path_exists.call_count, 2)
        self.assertEqual(mock_compare_charmdir_hash.call_count, 1)
        self.assertEqual(mock_compare_charm_hash.call_count, 0)

    @patch("os.path.exists")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charmdir_hash")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charm_hash")
    def test_ns_update_check_charm_hash_changed(
        self, mock_compare_charm_hash, mock_compare_charmdir_hash, mock_path_exists
    ):
        """Check charm hash, Hash has changed"""

        current_path, target_path = "/tmp/charm1", "/tmp/charm2"

        fs = Mock()
        fs.path.__add__ = Mock()
        fs.path.side_effect = [current_path, target_path, current_path, target_path]
        fs.path.__add__.side_effect = [
            current_path,
            target_path,
            current_path,
            target_path,
        ]

        mock_path_exists.side_effect = [True, True]
        mock_compare_charmdir_hash.return_value = callable(True)
        mock_compare_charm_hash.return_value = callable(True)

        instance = self.my_ns
        instance.fs = fs
        expected_result = True

        result = instance.check_charm_hash_changed(current_path, target_path)
        self.assertEqual(result, expected_result, "Wrong charm hash control value")
        self.assertEqual(mock_path_exists.call_count, 2)
        self.assertEqual(mock_compare_charmdir_hash.call_count, 1)
        self.assertEqual(mock_compare_charm_hash.call_count, 0)

    @patch("os.path.exists")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charmdir_hash")
    @patch("osm_lcm.lcm_utils.LcmBase.compare_charm_hash")
    def test_ns_update_check_no_charm_path(
        self, mock_compare_charm_hash, mock_compare_charmdir_hash, mock_path_exists
    ):
        """Check charm hash, Charm path does not exist"""

        current_path, target_path = "/tmp/charm1", "/tmp/charm2"

        fs = Mock()
        fs.path.__add__ = Mock()
        fs.path.side_effect = [current_path, target_path, current_path, target_path]
        fs.path.__add__.side_effect = [
            current_path,
            target_path,
            current_path,
            target_path,
        ]

        mock_path_exists.side_effect = [True, False]

        mock_compare_charmdir_hash.return_value = callable(False)
        mock_compare_charm_hash.return_value = callable(False)
        instance = self.my_ns
        instance.fs = fs

        with self.assertRaises(LcmException):
            instance.check_charm_hash_changed(current_path, target_path)
            self.assertEqual(mock_path_exists.call_count, 2)
            self.assertEqual(mock_compare_charmdir_hash.call_count, 0)
            self.assertEqual(mock_compare_charm_hash.call_count, 0)

    def test_ns_update_check_juju_bundle_existence_bundle_exists(self):
        """Check juju bundle existence"""
        test_vnfd2 = self.db.get_one(
            "vnfds", {"_id": "d96b1cdf-5ad6-49f7-bf65-907ada989293"}
        )
        expected_result = "stable/native-kdu"
        result = check_juju_bundle_existence(test_vnfd2)
        self.assertEqual(result, expected_result, "Wrong juju bundle name")

    def test_ns_update_check_juju_bundle_existence_bundle_does_not_exist(self):
        """Check juju bundle existence"""
        test_vnfd1 = self.db.get_one("vnfds", {"_id": vnfd_id})
        expected_result = None
        result = check_juju_bundle_existence(test_vnfd1)
        self.assertEqual(result, expected_result, "Wrong juju bundle name")

    def test_ns_update_check_juju_bundle_existence_empty_vnfd(self):
        """Check juju bundle existence"""
        test_vnfd1 = {}
        expected_result = None
        result = check_juju_bundle_existence(test_vnfd1)
        self.assertEqual(result, expected_result, "Wrong juju bundle name")

    def test_ns_update_check_juju_bundle_existence_invalid_vnfd(self):
        """Check juju bundle existence"""
        test_vnfd1 = [{"_id": vnfd_id}]
        with self.assertRaises(AttributeError):
            check_juju_bundle_existence(test_vnfd1)

    def test_ns_update_check_juju_charm_artifacts_base_folder_wth_pkgdir(self):
        """Check charm artifacts"""
        base_folder = {"folder": vnfd_id, "pkg-dir": "hackfest_3charmed_vnfd"}
        charm_name = "simple"
        charm_type = "lxc_proxy_charm"
        revision = 3
        expected_result = f"{vnfd_id}:3/hackfest_3charmed_vnfd/charms/simple"
        result = get_charm_artifact_path(base_folder, charm_name, charm_type, revision)
        self.assertEqual(result, expected_result, "Wrong charm artifact path")

    def test_ns_update_check_juju_charm_artifacts_base_folder_wthout_pkgdir(self):
        """Check charm artifacts, SOL004 packages"""
        base_folder = {"folder": vnfd_id}
        charm_name = "basic"
        charm_type, revision = "", ""
        expected_result = f"{vnfd_id}/Scripts/helm-charts/basic"
        result = get_charm_artifact_path(base_folder, charm_name, charm_type, revision)
        self.assertEqual(result, expected_result, "Wrong charm artifact path")


class TestInstantiateN2VC(TestBaseNS):
    async def setUp(self):
        await super().setUp()
        self.db_nsr = yaml.safe_load(descriptors.db_nsrs_text)[0]
        self.db_vnfr = yaml.safe_load(descriptors.db_vnfrs_text)[0]
        self.vca_index = 1
        self.my_ns._write_configuration_status = Mock()

    async def call_instantiate_N2VC(self):
        logging_text = "N2VC Instantiation"
        config_descriptor = {"config-access": {"ssh-access": {"default-user": "admin"}}}
        base_folder = {"pkg-dir": "", "folder": "~"}
        stage = ["Stage", "Message"]

        await self.my_ns.instantiate_N2VC(
            logging_text=logging_text,
            vca_index=self.vca_index,
            nsi_id="nsi_id",
            db_nsr=self.db_nsr,
            db_vnfr=self.db_vnfr,
            vdu_id=None,
            kdu_name=None,
            vdu_index=None,
            kdu_index=None,
            config_descriptor=config_descriptor,
            deploy_params={},
            base_folder=base_folder,
            nslcmop_id="nslcmop_id",
            stage=stage,
            vca_type="native_charm",
            vca_name="vca_name",
            ee_config_descriptor={},
        )

    def check_config_status(self, expected_status):
        self.my_ns._write_configuration_status.assert_called_with(
            nsr_id=self.db_nsr["_id"], vca_index=self.vca_index, status=expected_status
        )

    async def call_ns_add_relation(self):
        ee_relation = EERelation(
            {
                "nsr-id": self.db_nsr["_id"],
                "vdu-profile-id": None,
                "kdu-resource-profile-id": None,
                "vnf-profile-id": "hackfest_vnf1",
                "execution-environment-ref": "f48163a6-c807-47bc-9682-f72caef5af85.alf-c-ab",
                "endpoint": "127.0.0.1",
            }
        )

        relation = Relation("relation-name", ee_relation, ee_relation)
        cached_vnfrs = {"hackfest_vnf1": self.db_vnfr}

        return await self.my_ns._add_relation(
            relation=relation,
            vca_type="native_charm",
            db_nsr=self.db_nsr,
            cached_vnfds={},
            cached_vnfrs=cached_vnfrs,
        )

    async def test_add_relation_ok(self):
        await self.call_instantiate_N2VC()
        self.check_config_status(expected_status="READY")

    async def test_add_relation_returns_false_raises_exception(self):
        self.my_ns._add_vca_relations = asynctest.CoroutineMock(return_value=False)

        with self.assertRaises(LcmException) as exception:
            await self.call_instantiate_N2VC()

        exception_msg = "Relations could not be added to VCA."
        self.assertTrue(exception_msg in str(exception.exception))
        self.check_config_status(expected_status="BROKEN")

    async def test_add_relation_raises_lcm_exception(self):
        exception_msg = "Relations FAILED"
        self.my_ns._add_vca_relations = asynctest.CoroutineMock(
            side_effect=LcmException(exception_msg)
        )

        with self.assertRaises(LcmException) as exception:
            await self.call_instantiate_N2VC()

        self.assertTrue(exception_msg in str(exception.exception))
        self.check_config_status(expected_status="BROKEN")

    async def test_n2vc_add_relation_fails_raises_exception(self):
        exception_msg = "N2VC failed to add relations"
        self.my_ns.n2vc.add_relation = asynctest.CoroutineMock(
            side_effect=N2VCException(exception_msg)
        )
        with self.assertRaises(LcmException) as exception:
            await self.call_ns_add_relation()
        self.assertTrue(exception_msg in str(exception.exception))

    async def test_n2vc_add_relation_ok_returns_true(self):
        self.my_ns.n2vc.add_relation = asynctest.CoroutineMock(return_value=None)
        self.assertTrue(await self.call_ns_add_relation())


class TestGetVNFRelations(TestBaseNS):
    async def setUp(self):
        await super().setUp()
        self.db_nsd = yaml.safe_load(descriptors.db_nsds_text)[0]

    def test_ns_charm_vca_returns_empty_relations(self):
        ns_charm_vca = {"member-vnf-index": None, "target_element": "ns"}
        nsr_id = self.db_nsd["id"]
        deployed_vca = DeployedVCA(nsr_id, ns_charm_vca)

        expected_relations = []
        self.assertEqual(
            expected_relations,
            self.my_ns._get_vnf_relations(
                nsr_id=nsr_id, nsd=self.db_nsd, vca=deployed_vca, cached_vnfds={}
            ),
        )

    def test_vnf_returns_relation(self):
        vnf_vca = {
            "member-vnf-index": "1",
            "target_element": "vnf/0",
            "ee_descriptor_id": "simple-ee",
            "vdu_id": "mgmtVM",
        }
        nsr_id = self.db_nsd["id"]
        deployed_vca = DeployedVCA(nsr_id, vnf_vca)

        provider_dict = {
            "nsr-id": nsr_id,
            "vnf-profile-id": "1",
            "vdu-profile-id": "mgmtVM",
            "kdu-resource-profile-id": None,
            "execution-environment-ref": "simple-ee",
            "endpoint": "interface",
        }

        requirer_dict = {
            "nsr-id": nsr_id,
            "vnf-profile-id": "1",
            "vdu-profile-id": "dataVM",
            "kdu-resource-profile-id": None,
            "execution-environment-ref": "simple-ee",
            "endpoint": "interface",
        }

        provider = EERelation(provider_dict)
        requirer = EERelation(requirer_dict)
        relation = Relation("relation", provider, requirer)

        relations_found = self.my_ns._get_vnf_relations(
            nsr_id=nsr_id, nsd=self.db_nsd, vca=deployed_vca, cached_vnfds={}
        )

        self.assertEqual(1, len(relations_found))
        self.assertEqual(relation, relations_found[0])


if __name__ == "__main__":
    asynctest.main()
