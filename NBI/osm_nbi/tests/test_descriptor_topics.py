#! /usr/bin/python3
# -*- coding: utf-8 -*-

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

__author__ = "Pedro de la Cruz Ramos, pedro.delacruzramos@altran.com"
__date__ = "2019-11-20"

from contextlib import contextmanager
import unittest
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4
from http import HTTPStatus
from copy import deepcopy
from time import time
from osm_common import dbbase, fsbase, msgbase
from osm_nbi import authconn
from osm_nbi.tests.test_pkg_descriptors import (
    db_vnfds_text,
    db_nsds_text,
    vnfd_exploit_text,
    vnfd_exploit_fixed_text,
    db_sfc_nsds_text,
)
from osm_nbi.descriptor_topics import VnfdTopic, NsdTopic
from osm_nbi.engine import EngineException
from osm_common.dbbase import DbException
import yaml
import tempfile
import collections
import collections.abc

collections.MutableSequence = collections.abc.MutableSequence

test_name = "test-user"
db_vnfd_content = yaml.safe_load(db_vnfds_text)[0]
db_nsd_content = yaml.safe_load(db_nsds_text)[0]
test_pid = db_vnfd_content["_admin"]["projects_read"][0]
fake_session = {
    "username": test_name,
    "project_id": (test_pid,),
    "method": None,
    "admin": True,
    "force": False,
    "public": False,
    "allow_show_user_project_role": True,
}
UUID = "00000000-0000-0000-0000-000000000000"


def admin_value():
    return {"projects_read": []}


def setup_mock_fs(fs):
    fs.path = ""
    fs.get_params.return_value = {}
    fs.file_exists.return_value = False
    fs.file_open.side_effect = lambda path, mode: tempfile.TemporaryFile(mode="a+b")


def norm(s: str):
    """Normalize string for checking"""
    return " ".join(s.strip().split()).lower()


def compare_desc(tc, d1, d2, k):
    """
    Compare two descriptors
    We need this function because some methods are adding/removing items to/from the descriptors
    before they are stored in the database, so the original and stored versions will differ
    What we check is that COMMON LEAF ITEMS are equal
    Lists of different length are not compared
    :param tc: Test Case wich provides context (in particular the assert* methods)
    :param d1,d2: Descriptors to be compared
    :param k: key/item being compared
    :return: Nothing
    """
    if isinstance(d1, dict) and isinstance(d2, dict):
        for key in d1.keys():
            if key in d2:
                compare_desc(tc, d1[key], d2[key], k + "[{}]".format(key))
    elif isinstance(d1, list) and isinstance(d2, list) and len(d1) == len(d2):
        for i in range(len(d1)):
            compare_desc(tc, d1[i], d2[i], k + "[{}]".format(i))
    else:
        tc.assertEqual(d1, d2, "Wrong descriptor content: {}".format(k))


class Test_VnfdTopic(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_name = "test-vnfd-topic"

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.db = Mock(dbbase.DbBase())
        self.fs = Mock(fsbase.FsBase())
        self.msg = Mock(msgbase.MsgBase())
        self.auth = Mock(authconn.Authconn(None, None, None))
        self.topic = VnfdTopic(self.db, self.fs, self.msg, self.auth)
        self.topic.check_quota = Mock(return_value=None)  # skip quota

    @contextmanager
    def assertNotRaises(self, exception_type=Exception):
        try:
            yield None
        except exception_type:
            raise self.failureException("{} raised".format(exception_type.__name__))

    def create_desc_temp(self, template):
        old_desc = deepcopy(template)
        new_desc = deepcopy(template)
        return old_desc, new_desc

    def prepare_vnfd_creation(self):
        setup_mock_fs(self.fs)
        test_vnfd = deepcopy(db_vnfd_content)
        did = db_vnfd_content["_id"]
        self.db.create.return_value = did
        self.db.get_one.side_effect = [
            {"_id": did, "_admin": deepcopy(db_vnfd_content["_admin"])},
            None,
        ]
        return did, test_vnfd

    def prepare_vnfd(self, vnfd_text):
        setup_mock_fs(self.fs)
        test_vnfd = yaml.safe_load(vnfd_text)
        self.db.create.return_value = UUID
        self.db.get_one.side_effect = [
            {"_id": UUID, "_admin": admin_value()},
            None,
        ]
        return UUID, test_vnfd

    def prepare_test_vnfd(self, test_vnfd):
        del test_vnfd["_id"]
        del test_vnfd["_admin"]
        del test_vnfd["vdu"][0]["cloud-init-file"]
        del test_vnfd["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ][0]["execution-environment-list"][0]["juju"]
        return test_vnfd

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_normal_creation(self, mock_rename, mock_shutil):
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        rollback = []
        did2, oid = self.topic.new(rollback, fake_session, {})
        db_args = self.db.create.call_args[0]
        msg_args = self.msg.write.call_args[0]

        self.assertEqual(len(rollback), 1, "Wrong rollback length")
        self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
        self.assertEqual(msg_args[1], "created", "Wrong message action")
        self.assertEqual(msg_args[2], {"_id": did}, "Wrong message content")
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(did2, did, "Wrong DB VNFD id")
        self.assertIsNotNone(db_args[1]["_admin"]["created"], "Wrong creation time")
        self.assertEqual(
            db_args[1]["_admin"]["modified"],
            db_args[1]["_admin"]["created"],
            "Wrong modification time",
        )
        self.assertEqual(
            db_args[1]["_admin"]["projects_read"],
            [test_pid],
            "Wrong read-only project list",
        )
        self.assertEqual(
            db_args[1]["_admin"]["projects_write"],
            [test_pid],
            "Wrong read-write project list",
        )

        self.db.get_one.side_effect = [
            {"_id": did, "_admin": deepcopy(db_vnfd_content["_admin"])},
            None,
        ]

        self.topic.upload_content(
            fake_session, did, test_vnfd, {}, {"Content-Type": []}
        )
        msg_args = self.msg.write.call_args[0]
        test_vnfd["_id"] = did
        self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
        self.assertEqual(msg_args[1], "edited", "Wrong message action")
        self.assertEqual(msg_args[2], test_vnfd, "Wrong message content")

        db_args = self.db.get_one.mock_calls[0][1]
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(db_args[1]["_id"], did, "Wrong DB VNFD id")

        db_args = self.db.replace.call_args[0]
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(db_args[1], did, "Wrong DB VNFD id")

        admin = db_args[2]["_admin"]
        db_admin = deepcopy(db_vnfd_content["_admin"])
        self.assertEqual(admin["type"], "vnfd", "Wrong descriptor type")
        self.assertEqual(admin["created"], db_admin["created"], "Wrong creation time")
        self.assertGreater(
            admin["modified"], db_admin["created"], "Wrong modification time"
        )
        self.assertEqual(
            admin["projects_read"],
            db_admin["projects_read"],
            "Wrong read-only project list",
        )
        self.assertEqual(
            admin["projects_write"],
            db_admin["projects_write"],
            "Wrong read-write project list",
        )
        self.assertEqual(
            admin["onboardingState"], "ONBOARDED", "Wrong onboarding state"
        )
        self.assertEqual(
            admin["operationalState"], "ENABLED", "Wrong operational state"
        )
        self.assertEqual(admin["usageState"], "NOT_IN_USE", "Wrong usage state")

        storage = admin["storage"]
        self.assertEqual(storage["folder"], did + ":1", "Wrong storage folder")
        self.assertEqual(storage["descriptor"], "package", "Wrong storage descriptor")
        self.assertEqual(admin["revision"], 1, "Wrong revision number")
        compare_desc(self, test_vnfd, db_args[2], "VNFD")

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_exploit(self, mock_rename, mock_shutil):
        id, test_vnfd = self.prepare_vnfd(vnfd_exploit_text)

        with self.assertRaises(EngineException):
            self.topic.upload_content(
                fake_session, id, test_vnfd, {}, {"Content-Type": []}
            )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_valid_helm_chart(self, mock_rename, mock_shutil):
        id, test_vnfd = self.prepare_vnfd(vnfd_exploit_fixed_text)

        with self.assertNotRaises():
            self.topic.upload_content(
                fake_session, id, test_vnfd, {}, {"Content-Type": []}
            )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_pyangbind_validation_additional_properties(
        self, mock_rename, mock_shutil
    ):
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        self.topic.upload_content(
            fake_session, did, test_vnfd, {}, {"Content-Type": []}
        )
        test_vnfd["_id"] = did
        test_vnfd["extra-property"] = 0
        self.db.get_one.side_effect = (
            lambda table, filter, fail_on_empty=None, fail_on_more=None: {
                "_id": did,
                "_admin": deepcopy(db_vnfd_content["_admin"]),
            }
        )

        with self.assertRaises(
            EngineException, msg="Accepted VNFD with an additional property"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error in pyangbind validation: {} ({})".format(
                    "json object contained a key that did not exist", "extra-property"
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )
        db_args = self.db.replace.call_args[0]
        admin = db_args[2]["_admin"]
        self.assertEqual(admin["revision"], 1, "Wrong revision number")

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_pyangbind_validation_property_types(
        self, mock_rename, mock_shutil
    ):
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["_id"] = did
        test_vnfd["product-name"] = {"key": 0}

        with self.assertRaises(
            EngineException, msg="Accepted VNFD with a wrongly typed property"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error in pyangbind validation: {} ({})".format(
                    "json object contained a key that did not exist", "key"
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_cloud_init(self, mock_rename, mock_shutil):
        did, test_vnfd = self.prepare_vnfd_creation()
        del test_vnfd["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ][0]["execution-environment-list"][0]["juju"]

        with self.assertRaises(
            EngineException, msg="Accepted non-existent cloud_init file"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code, HTTPStatus.BAD_REQUEST, "Wrong HTTP status code"
        )
        self.assertIn(
            norm(
                "{} defined in vnf[id={}]:vdu[id={}] but not present in package".format(
                    "cloud-init", test_vnfd["id"], test_vnfd["vdu"][0]["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_day12_configuration(
        self, mock_rename, mock_shutil
    ):
        did, test_vnfd = self.prepare_vnfd_creation()
        del test_vnfd["vdu"][0]["cloud-init-file"]

        with self.assertRaises(
            EngineException, msg="Accepted non-existent charm in VNF configuration"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code, HTTPStatus.BAD_REQUEST, "Wrong HTTP status code"
        )
        self.assertIn(
            norm(
                "{} defined in vnf[id={}] but not present in package".format(
                    "charm", test_vnfd["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_mgmt_cp(self, mock_rename, mock_shutil):
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        del test_vnfd["mgmt-cp"]

        with self.assertRaises(
            EngineException, msg="Accepted VNFD without management interface"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm("'{}' is a mandatory field and it is not defined".format("mgmt-cp")),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_mgmt_cp_connection_point(
        self, mock_rename, mock_shutil
    ):
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["mgmt-cp"] = "wrong-cp"

        with self.assertRaises(
            EngineException, msg="Accepted wrong mgmt-cp connection point"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "mgmt-cp='{}' must match an existing ext-cpd".format(
                    test_vnfd["mgmt-cp"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_vdu_int_cpd(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for vdu internal connection point"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        ext_cpd = test_vnfd["ext-cpd"][1]
        ext_cpd["int-cpd"]["cpd"] = "wrong-cpd"

        with self.assertRaises(
            EngineException, msg="Accepted wrong ext-cpd internal connection point"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "ext-cpd[id='{}']:int-cpd must match an existing vdu int-cpd".format(
                    ext_cpd["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_duplicated_vld(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for dublicated virtual link description"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["int-virtual-link-desc"].insert(0, {"id": "internal"})

        with self.assertRaises(
            EngineException, msg="Accepted duplicated VLD name"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "identifier id '{}' is not unique".format(
                    test_vnfd["int-virtual-link-desc"][0]["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_vdu_int_virtual_link_desc(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for vdu internal virtual link description"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        vdu = test_vnfd["vdu"][0]
        int_cpd = vdu["int-cpd"][1]
        int_cpd["int-virtual-link-desc"] = "non-existing-int-virtual-link-desc"

        with self.assertRaises(
            EngineException, msg="Accepted int-virtual-link-desc"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[id='{}']:int-cpd[id='{}']:int-virtual-link-desc='{}' must match an existing "
                "int-virtual-link-desc".format(
                    vdu["id"], int_cpd["id"], int_cpd["int-virtual-link-desc"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_virtual_link_profile(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for virtual link profile"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        fake_ivld_profile = {"id": "fake-profile-ref", "flavour": "fake-flavour"}
        df = test_vnfd["df"][0]
        df["virtual-link-profile"] = [fake_ivld_profile]

        with self.assertRaises(
            EngineException, msg="Accepted non-existent Profile Ref"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:virtual-link-profile='{}' must match an existing "
                "int-virtual-link-desc".format(df["id"], fake_ivld_profile["id"])
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_scaling_criteria_vdu_id(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for scaling criteria with invalid vdu-id"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["df"][0]["scaling-aspect"][0]["aspect-delta-details"]["deltas"][0][
            "vdu-delta"
        ][0]["id"] = "vdudelta1"
        affected_df = test_vnfd["df"][0]
        sa = affected_df["scaling-aspect"][0]
        delta = sa["aspect-delta-details"]["deltas"][0]
        vdu_delta = delta["vdu-delta"][0]

        with self.assertRaises(
            EngineException, msg="Accepted invalid Scaling Group Policy Criteria"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:scaling-aspect[id='{}']:aspect-delta-details"
                "[delta='{}']: "
                "vdu-id='{}' not defined in vdu".format(
                    affected_df["id"],
                    sa["id"],
                    delta["id"],
                    vdu_delta["id"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_scaling_criteria_monitoring_param_ref(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for scaling criteria without monitoring parameter"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        vdu = test_vnfd["vdu"][1]
        affected_df = test_vnfd["df"][0]
        sa = affected_df["scaling-aspect"][0]
        sp = sa["scaling-policy"][0]
        sc = sp["scaling-criteria"][0]
        vdu.pop("monitoring-parameter")

        with self.assertRaises(
            EngineException, msg="Accepted non-existent Scaling Group Policy Criteria"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:scaling-aspect[id='{}']:scaling-policy"
                "[name='{}']:scaling-criteria[name='{}']: "
                "vnf-monitoring-param-ref='{}' not defined in any monitoring-param".format(
                    affected_df["id"],
                    sa["id"],
                    sp["name"],
                    sc["name"],
                    sc["vnf-monitoring-param-ref"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_scaling_aspect_vnf_configuration(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for scaling criteria without day12 configuration"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ].pop()
        df = test_vnfd["df"][0]

        with self.assertRaises(
            EngineException, msg="Accepted non-existent Scaling Group VDU ID Reference"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "'day1-2 configuration' not defined in the descriptor but it is referenced "
                "by df[id='{}']:scaling-aspect[id='{}']:scaling-config-action".format(
                    df["id"], df["scaling-aspect"][0]["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_scaling_config_action(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for scaling criteria wrong config primitive"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        df = test_vnfd["df"][0]
        affected_df = test_vnfd["df"][0]
        sa = affected_df["scaling-aspect"][0]
        test_vnfd["df"][0].get("lcm-operations-configuration").get(
            "operate-vnf-op-config"
        )["day1-2"][0]["config-primitive"] = [{"name": "wrong-primitive"}]

        with self.assertRaises(
            EngineException, msg="Accepted non-existent Scaling Group VDU ID Reference"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:scaling-aspect[id='{}']:scaling-config-action:vnf-"
                "config-primitive-name-ref='{}' does not match any "
                "day1-2 configuration:config-primitive:name".format(
                    df["id"],
                    df["scaling-aspect"][0]["id"],
                    sa["scaling-config-action"][0]["vnf-config-primitive-name-ref"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_healing_criteria_vdu_id(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for healing criteria with invalid vdu-id"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["df"][0]["healing-aspect"][0]["healing-policy"][0][
            "vdu-id"
        ] = "vduid1"
        affected_df = test_vnfd["df"][0]
        ha = affected_df["healing-aspect"][0]
        hp = ha["healing-policy"][0]
        hp_vdu_id = hp["vdu-id"]

        with self.assertRaises(
            EngineException, msg="Accepted invalid Healing Group Policy Criteria"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:healing-aspect[id='{}']:healing-policy"
                "[name='{}']: "
                "vdu-id='{}' not defined in vdu".format(
                    affected_df["id"],
                    ha["id"],
                    hp["event-name"],
                    hp_vdu_id,
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_alarm_criteria_monitoring_param_ref(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for alarm with invalid monitoring parameter reference"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["vdu"][1]["alarm"][0]["vnf-monitoring-param-ref"] = "unit_test_alarm"
        vdu = test_vnfd["vdu"][1]
        alarm = vdu["alarm"][0]
        alarm_monitoring_param = alarm["vnf-monitoring-param-ref"]

        with self.assertRaises(
            EngineException, msg="Accepted invalid Alarm Criteria"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[id='{}']:alarm[id='{}']:"
                "vnf-monitoring-param-ref='{}' not defined in any monitoring-param".format(
                    vdu["id"],
                    alarm["alarm-id"],
                    alarm_monitoring_param,
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_storage_reference_criteria(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for invalid virtual-storge-desc reference"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["vdu"][1]["virtual-storage-desc"] = "unit_test_storage"
        vdu = test_vnfd["vdu"][1]
        vsd_ref = vdu["virtual-storage-desc"]

        with self.assertRaises(
            EngineException, msg="Accepted invalid virtual-storage-desc"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[virtual-storage-desc='{}']"
                "not defined in vnfd".format(
                    vsd_ref,
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_compute_reference_criteria(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        for invalid virtual-compute-desc reference"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["vdu"][1]["virtual-compute-desc"] = "unit_test_compute"
        vdu = test_vnfd["vdu"][1]
        vcd_ref = vdu["virtual-compute-desc"]

        with self.assertRaises(
            EngineException, msg="Accepted invalid virtual-compute-desc"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_vnfd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[virtual-compute-desc='{}']"
                "not defined in vnfd".format(
                    vcd_ref,
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_vnfd_check_input_validation_everything_right(
        self, mock_rename, mock_shutil
    ):
        """Testing input validation during new vnfd creation
        everything correct"""
        did, test_vnfd = self.prepare_vnfd_creation()
        test_vnfd = self.prepare_test_vnfd(test_vnfd)
        test_vnfd["id"] = "fake-vnfd-id"
        test_vnfd["df"][0].get("lcm-operations-configuration").get(
            "operate-vnf-op-config"
        )["day1-2"][0]["id"] = "fake-vnfd-id"
        self.db.get_one.side_effect = [
            {"_id": did, "_admin": deepcopy(db_vnfd_content["_admin"])},
            None,
        ]
        rc = self.topic.upload_content(
            fake_session, did, test_vnfd, {}, {"Content-Type": []}
        )
        self.assertTrue(rc, "Input Validation: Unexpected failure")

    def test_edit_vnfd(self):
        vnfd_content = deepcopy(db_vnfd_content)
        did = vnfd_content["_id"]
        self.fs.file_exists.return_value = True
        self.fs.dir_ls.return_value = True
        with self.subTest(i=1, t="Normal Edition"):
            now = time()
            self.db.get_one.side_effect = [deepcopy(vnfd_content), None]
            data = {"product-name": "new-vnfd-name"}
            self.topic.edit(fake_session, did, data)
            db_args = self.db.replace.call_args[0]
            msg_args = self.msg.write.call_args[0]
            data["_id"] = did
            self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
            self.assertEqual(msg_args[1], "edited", "Wrong message action")
            self.assertEqual(msg_args[2], data, "Wrong message content")
            self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_args[1], did, "Wrong DB ID")
            self.assertEqual(
                db_args[2]["_admin"]["created"],
                vnfd_content["_admin"]["created"],
                "Wrong creation time",
            )
            self.assertGreater(
                db_args[2]["_admin"]["modified"], now, "Wrong modification time"
            )
            self.assertEqual(
                db_args[2]["_admin"]["projects_read"],
                vnfd_content["_admin"]["projects_read"],
                "Wrong read-only project list",
            )
            self.assertEqual(
                db_args[2]["_admin"]["projects_write"],
                vnfd_content["_admin"]["projects_write"],
                "Wrong read-write project list",
            )
            self.assertEqual(
                db_args[2]["product-name"], data["product-name"], "Wrong VNFD Name"
            )
        with self.subTest(i=2, t="Conflict on Edit"):
            data = {"id": "hackfest3charmed-vnf", "product-name": "new-vnfd-name"}
            self.db.get_one.side_effect = [
                deepcopy(vnfd_content),
                {"_id": str(uuid4()), "id": data["id"]},
            ]
            with self.assertRaises(
                EngineException, msg="Accepted existing VNFD ID"
            ) as e:
                self.topic.edit(fake_session, did, data)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                norm(
                    "{} with id '{}' already exists for this project".format(
                        "vnfd", data["id"]
                    )
                ),
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=3, t="Check Envelope"):
            data = {"vnfd": [{"id": "new-vnfd-id-1", "product-name": "new-vnfd-name"}]}
            with self.assertRaises(
                EngineException, msg="Accepted VNFD with wrong envelope"
            ) as e:
                self.topic.edit(fake_session, did, data, content=vnfd_content)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.BAD_REQUEST, "Wrong HTTP status code"
            )
            self.assertIn(
                "'vnfd' must be dict", norm(str(e.exception)), "Wrong exception text"
            )
        return

    def test_delete_vnfd(self):
        did = db_vnfd_content["_id"]
        self.db.get_one.return_value = db_vnfd_content
        p_id = db_vnfd_content["_admin"]["projects_read"][0]
        with self.subTest(i=1, t="Normal Deletion"):
            self.db.get_list.return_value = []
            self.db.del_one.return_value = {"deleted": 1}
            self.topic.delete(fake_session, did)
            db_args = self.db.del_one.call_args[0]
            msg_args = self.msg.write.call_args[0]
            self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
            self.assertEqual(msg_args[1], "deleted", "Wrong message action")
            self.assertEqual(msg_args[2], {"_id": did}, "Wrong message content")
            self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_args[1]["_id"], did, "Wrong DB ID")
            self.assertEqual(
                db_args[1]["_admin.projects_write.cont"],
                [p_id, "ANY"],
                "Wrong DB filter",
            )
            db_g1_args = self.db.get_one.call_args[0]
            self.assertEqual(db_g1_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_g1_args[1]["_id"], did, "Wrong DB VNFD ID")
            db_gl_calls = self.db.get_list.call_args_list
            self.assertEqual(db_gl_calls[0][0][0], "vnfrs", "Wrong DB topic")
            # self.assertEqual(db_gl_calls[0][0][1]["vnfd-id"], did, "Wrong DB VNFD ID")   # Filter changed after call
            self.assertEqual(db_gl_calls[1][0][0], "nsds", "Wrong DB topic")
            self.assertEqual(
                db_gl_calls[1][0][1]["vnfd-id"],
                db_vnfd_content["id"],
                "Wrong DB NSD vnfd-id",
            )

            self.assertEqual(
                self.db.del_list.call_args[0][0],
                self.topic.topic + "_revisions",
                "Wrong DB topic",
            )

            self.assertEqual(
                self.db.del_list.call_args[0][1]["_id"]["$regex"],
                did,
                "Wrong ID for rexep delete",
            )

            self.db.set_one.assert_not_called()
            fs_del_calls = self.fs.file_delete.call_args_list
            self.assertEqual(fs_del_calls[0][0][0], did, "Wrong FS file id")
            self.assertEqual(fs_del_calls[1][0][0], did + "_", "Wrong FS folder id")
        with self.subTest(i=2, t="Conflict on Delete - VNFD in use by VNFR"):
            self.db.get_list.return_value = [{"_id": str(uuid4()), "name": "fake-vnfr"}]
            with self.assertRaises(
                EngineException, msg="Accepted VNFD in use by VNFR"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                "there is at least one vnf instance using this descriptor",
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=3, t="Conflict on Delete - VNFD in use by NSD"):
            self.db.get_list.side_effect = [
                [],
                [{"_id": str(uuid4()), "name": "fake-nsd"}],
            ]
            with self.assertRaises(
                EngineException, msg="Accepted VNFD in use by NSD"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                "there is at least one ns package referencing this descriptor",
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=4, t="Non-existent VNFD"):
            excp_msg = "Not found any {} with filter='{}'".format("VNFD", {"_id": did})
            self.db.get_one.side_effect = DbException(excp_msg, HTTPStatus.NOT_FOUND)
            with self.assertRaises(
                DbException, msg="Accepted non-existent VNFD ID"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.NOT_FOUND, "Wrong HTTP status code"
            )
            self.assertIn(
                norm(excp_msg), norm(str(e.exception)), "Wrong exception text"
            )
        with self.subTest(i=5, t="No delete because referenced by other project"):
            db_vnfd_content["_admin"]["projects_read"].append("other_project")
            self.db.get_one = Mock(return_value=db_vnfd_content)
            self.db.get_list = Mock(return_value=[])
            self.msg.write.reset_mock()
            self.db.del_one.reset_mock()
            self.fs.file_delete.reset_mock()

            self.topic.delete(fake_session, did)
            self.db.del_one.assert_not_called()
            self.msg.write.assert_not_called()
            db_g1_args = self.db.get_one.call_args[0]
            self.assertEqual(db_g1_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_g1_args[1]["_id"], did, "Wrong DB VNFD ID")
            db_s1_args = self.db.set_one.call_args
            self.assertEqual(db_s1_args[0][0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_s1_args[0][1]["_id"], did, "Wrong DB ID")
            self.assertIn(
                p_id, db_s1_args[0][1]["_admin.projects_write.cont"], "Wrong DB filter"
            )
            self.assertIsNone(
                db_s1_args[1]["update_dict"], "Wrong DB update dictionary"
            )
            self.assertEqual(
                db_s1_args[1]["pull_list"],
                {"_admin.projects_read": (p_id,), "_admin.projects_write": (p_id,)},
                "Wrong DB pull_list dictionary",
            )
            self.fs.file_delete.assert_not_called()
        return

    def prepare_vnfd_validation(self):
        descriptor_name = "test_descriptor"
        self.fs.file_open.side_effect = lambda path, mode: open(
            "/tmp/" + str(uuid4()), "a+b"
        )
        old_vnfd, new_vnfd = self.create_desc_temp(db_vnfd_content)
        return descriptor_name, old_vnfd, new_vnfd

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_vnfd_changes_day12_config_primitive_changed(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating VNFD for VNFD updates, day1-2 config primitive has changed"""
        descriptor_name, old_vnfd, new_vnfd = self.prepare_vnfd_validation()
        did = old_vnfd["_id"]
        new_vnfd["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ][0]["config-primitive"][0]["name"] = "new_action"
        mock_safe_load.side_effect = [old_vnfd, new_vnfd]
        mock_detect_usage.return_value = True
        self.db.get_one.return_value = old_vnfd

        with self.assertNotRaises(EngineException):
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp/", "/tmp:1/"
            )
        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        self.assertEqual(mock_safe_load.call_count, 2)

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_vnfd_changes_sw_version_changed(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating VNFD for updates, software version has changed"""
        # old vnfd uses the default software version: 1.0
        descriptor_name, old_vnfd, new_vnfd = self.prepare_vnfd_validation()
        did = old_vnfd["_id"]
        new_vnfd["software-version"] = "1.3"
        new_vnfd["sw-image-desc"][0]["name"] = "new-image"
        mock_safe_load.side_effect = [old_vnfd, new_vnfd]
        mock_detect_usage.return_value = True
        self.db.get_one.return_value = old_vnfd

        with self.assertNotRaises(EngineException):
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp/", "/tmp:1/"
            )
        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        self.assertEqual(mock_safe_load.call_count, 2)

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_vnfd_changes_sw_version_not_changed_mgm_cp_changed(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating VNFD for updates, software version has not
        changed, mgmt-cp has changed."""
        descriptor_name, old_vnfd, new_vnfd = self.prepare_vnfd_validation()
        new_vnfd["mgmt-cp"] = "new-mgmt-cp"
        mock_safe_load.side_effect = [old_vnfd, new_vnfd]
        did = old_vnfd["_id"]
        mock_detect_usage.return_value = True
        self.db.get_one.return_value = old_vnfd

        with self.assertRaises(
            EngineException, msg="there are disallowed changes in the vnf descriptor"
        ) as e:
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp/", "/tmp:1/"
            )

        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm("there are disallowed changes in the vnf descriptor"),
            norm(str(e.exception)),
            "Wrong exception text",
        )
        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        self.assertEqual(mock_safe_load.call_count, 2)

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_vnfd_changes_sw_version_not_changed_mgm_cp_changed_vnfd_not_in_use(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating VNFD for updates, software version has not
        changed, mgmt-cp has changed, vnfd is not in use."""
        descriptor_name, old_vnfd, new_vnfd = self.prepare_vnfd_validation()
        new_vnfd["mgmt-cp"] = "new-mgmt-cp"
        mock_safe_load.side_effect = [old_vnfd, new_vnfd]
        did = old_vnfd["_id"]
        mock_detect_usage.return_value = None
        self.db.get_one.return_value = old_vnfd

        with self.assertNotRaises(EngineException):
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp/", "/tmp:1/"
            )

        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        mock_safe_load.assert_not_called()

    def test_validate_mgmt_interface_connection_point_on_valid_descriptor(self):
        indata = deepcopy(db_vnfd_content)
        self.topic.validate_mgmt_interface_connection_point(indata)

    def test_validate_mgmt_interface_connection_point_when_missing_connection_point(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        indata["ext-cpd"] = []
        with self.assertRaises(EngineException) as e:
            self.topic.validate_mgmt_interface_connection_point(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "mgmt-cp='{}' must match an existing ext-cpd".format(indata["mgmt-cp"])
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_mgmt_interface_connection_point_when_missing_mgmt_cp(self):
        indata = deepcopy(db_vnfd_content)
        indata.pop("mgmt-cp")
        with self.assertRaises(EngineException) as e:
            self.topic.validate_mgmt_interface_connection_point(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm("'mgmt-cp' is a mandatory field and it is not defined"),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_vdu_internal_connection_points_on_valid_descriptor(self):
        indata = db_vnfd_content
        vdu = indata["vdu"][0]
        self.topic.validate_vdu_internal_connection_points(vdu)

    def test_validate_external_connection_points_on_valid_descriptor(self):
        indata = db_vnfd_content
        self.topic.validate_external_connection_points(indata)

    def test_validate_external_connection_points_when_missing_internal_connection_point(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        vdu = indata["vdu"][0]
        vdu.pop("int-cpd")
        affected_ext_cpd = indata["ext-cpd"][0]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_external_connection_points(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "ext-cpd[id='{}']:int-cpd must match an existing vdu int-cpd".format(
                    affected_ext_cpd["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_vdu_internal_connection_points_on_duplicated_internal_connection_point(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        vdu = indata["vdu"][0]
        duplicated_cpd = {
            "id": "vnf-mgmt",
            "order": 3,
            "virtual-network-interface-requirement": [{"name": "duplicated"}],
        }
        vdu["int-cpd"].insert(0, duplicated_cpd)
        with self.assertRaises(EngineException) as e:
            self.topic.validate_vdu_internal_connection_points(vdu)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[id='{}']:int-cpd[id='{}'] is already used by other int-cpd".format(
                    vdu["id"], duplicated_cpd["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_external_connection_points_on_duplicated_external_connection_point(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        duplicated_cpd = {
            "id": "vnf-mgmt-ext",
            "int-cpd": {"vdu-id": "dataVM", "cpd": "vnf-data"},
        }
        indata["ext-cpd"].insert(0, duplicated_cpd)
        with self.assertRaises(EngineException) as e:
            self.topic.validate_external_connection_points(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "ext-cpd[id='{}'] is already used by other ext-cpd".format(
                    duplicated_cpd["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_internal_virtual_links_on_valid_descriptor(self):
        indata = db_vnfd_content
        self.topic.validate_internal_virtual_links(indata)

    def test_validate_internal_virtual_links_on_duplicated_ivld(self):
        indata = deepcopy(db_vnfd_content)
        duplicated_vld = {"id": "internal"}
        indata["int-virtual-link-desc"].insert(0, duplicated_vld)
        with self.assertRaises(EngineException) as e:
            self.topic.validate_internal_virtual_links(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Duplicated VLD id in int-virtual-link-desc[id={}]".format(
                    duplicated_vld["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_internal_virtual_links_when_missing_ivld_on_connection_point(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        vdu = indata["vdu"][0]
        affected_int_cpd = vdu["int-cpd"][0]
        affected_int_cpd["int-virtual-link-desc"] = "non-existing-int-virtual-link-desc"
        with self.assertRaises(EngineException) as e:
            self.topic.validate_internal_virtual_links(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "vdu[id='{}']:int-cpd[id='{}']:int-virtual-link-desc='{}' must match an existing "
                "int-virtual-link-desc".format(
                    vdu["id"],
                    affected_int_cpd["id"],
                    affected_int_cpd["int-virtual-link-desc"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_internal_virtual_links_when_missing_ivld_on_profile(self):
        indata = deepcopy(db_vnfd_content)
        affected_ivld_profile = {"id": "non-existing-int-virtual-link-desc"}
        df = indata["df"][0]
        df["virtual-link-profile"] = [affected_ivld_profile]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_internal_virtual_links(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:virtual-link-profile='{}' must match an existing "
                "int-virtual-link-desc".format(df["id"], affected_ivld_profile["id"])
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_monitoring_params_on_valid_descriptor(self):
        indata = db_vnfd_content
        self.topic.validate_monitoring_params(indata)

    def test_validate_monitoring_params_on_duplicated_ivld_monitoring_param(self):
        indata = deepcopy(db_vnfd_content)
        duplicated_mp = {"id": "cpu", "name": "cpu", "performance_metric": "cpu"}
        affected_ivld = indata["int-virtual-link-desc"][0]
        affected_ivld["monitoring-parameters"] = [duplicated_mp, duplicated_mp]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_monitoring_params(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Duplicated monitoring-parameter id in "
                "int-virtual-link-desc[id='{}']:monitoring-parameters[id='{}']".format(
                    affected_ivld["id"], duplicated_mp["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_monitoring_params_on_duplicated_vdu_monitoring_param(self):
        indata = deepcopy(db_vnfd_content)
        duplicated_mp = {
            "id": "dataVM_cpu_util",
            "name": "dataVM_cpu_util",
            "performance_metric": "cpu",
        }
        affected_vdu = indata["vdu"][1]
        affected_vdu["monitoring-parameter"].insert(0, duplicated_mp)
        with self.assertRaises(EngineException) as e:
            self.topic.validate_monitoring_params(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Duplicated monitoring-parameter id in "
                "vdu[id='{}']:monitoring-parameter[id='{}']".format(
                    affected_vdu["id"], duplicated_mp["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_monitoring_params_on_duplicated_df_monitoring_param(self):
        indata = deepcopy(db_vnfd_content)
        duplicated_mp = {
            "id": "memory",
            "name": "memory",
            "performance_metric": "memory",
        }
        affected_df = indata["df"][0]
        affected_df["monitoring-parameter"] = [duplicated_mp, duplicated_mp]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_monitoring_params(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Duplicated monitoring-parameter id in "
                "df[id='{}']:monitoring-parameter[id='{}']".format(
                    affected_df["id"], duplicated_mp["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_scaling_group_descriptor_on_valid_descriptor(self):
        indata = db_vnfd_content
        self.topic.validate_scaling_group_descriptor(indata)

    def test_validate_scaling_group_descriptor_when_missing_monitoring_param(self):
        indata = deepcopy(db_vnfd_content)
        vdu = indata["vdu"][1]
        affected_df = indata["df"][0]
        affected_sa = affected_df["scaling-aspect"][0]
        affected_sp = affected_sa["scaling-policy"][0]
        affected_sc = affected_sp["scaling-criteria"][0]
        vdu.pop("monitoring-parameter")
        with self.assertRaises(EngineException) as e:
            self.topic.validate_scaling_group_descriptor(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:scaling-aspect[id='{}']:scaling-policy"
                "[name='{}']:scaling-criteria[name='{}']: "
                "vnf-monitoring-param-ref='{}' not defined in any monitoring-param".format(
                    affected_df["id"],
                    affected_sa["id"],
                    affected_sp["name"],
                    affected_sc["name"],
                    affected_sc["vnf-monitoring-param-ref"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_scaling_group_descriptor_when_missing_vnf_configuration(self):
        indata = deepcopy(db_vnfd_content)
        df = indata["df"][0]
        affected_sa = df["scaling-aspect"][0]
        indata["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ].pop()
        with self.assertRaises(EngineException) as e:
            self.topic.validate_scaling_group_descriptor(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "'day1-2 configuration' not defined in the descriptor but it is referenced "
                "by df[id='{}']:scaling-aspect[id='{}']:scaling-config-action".format(
                    df["id"], affected_sa["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_scaling_group_descriptor_when_missing_scaling_config_action_primitive(
        self,
    ):
        indata = deepcopy(db_vnfd_content)
        df = indata["df"][0]
        affected_sa = df["scaling-aspect"][0]
        affected_sca_primitive = affected_sa["scaling-config-action"][0][
            "vnf-config-primitive-name-ref"
        ]
        df["lcm-operations-configuration"]["operate-vnf-op-config"]["day1-2"][0][
            "config-primitive"
        ] = []
        with self.assertRaises(EngineException) as e:
            self.topic.validate_scaling_group_descriptor(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "df[id='{}']:scaling-aspect[id='{}']:scaling-config-action:vnf-"
                "config-primitive-name-ref='{}' does not match any "
                "day1-2 configuration:config-primitive:name".format(
                    df["id"], affected_sa["id"], affected_sca_primitive
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_new_vnfd_revision(self):
        did = db_vnfd_content["_id"]
        self.fs.get_params.return_value = {}
        self.fs.file_exists.return_value = False
        self.fs.file_open.side_effect = lambda path, mode: open(
            "/tmp/" + str(uuid4()), "a+b"
        )
        test_vnfd = deepcopy(db_vnfd_content)
        del test_vnfd["_id"]
        del test_vnfd["_admin"]
        self.db.create.return_value = did
        rollback = []
        did2, oid = self.topic.new(rollback, fake_session, {})
        db_args = self.db.create.call_args[0]
        self.assertEqual(
            db_args[1]["_admin"]["revision"], 0, "New package should be at revision 0"
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_update_vnfd(self, mock_rename, mock_shutil):
        old_revision = 5
        did = db_vnfd_content["_id"]
        self.fs.path = ""
        self.fs.get_params.return_value = {}
        self.fs.file_exists.return_value = False
        self.fs.file_open.side_effect = lambda path, mode: open(
            "/tmp/" + str(uuid4()), "a+b"
        )
        new_vnfd = deepcopy(db_vnfd_content)
        del new_vnfd["_id"]
        self.db.create.return_value = did
        rollback = []
        did2, oid = self.topic.new(rollback, fake_session, {})
        del new_vnfd["vdu"][0]["cloud-init-file"]
        del new_vnfd["df"][0]["lcm-operations-configuration"]["operate-vnf-op-config"][
            "day1-2"
        ][0]["execution-environment-list"][0]["juju"]

        old_vnfd = {"_id": did, "_admin": deepcopy(db_vnfd_content["_admin"])}
        old_vnfd["_admin"]["revision"] = old_revision

        self.db.get_one.side_effect = [old_vnfd, old_vnfd, None]
        self.topic.upload_content(fake_session, did, new_vnfd, {}, {"Content-Type": []})

        db_args = self.db.replace.call_args[0]
        self.assertEqual(
            db_args[2]["_admin"]["revision"],
            old_revision + 1,
            "Revision should increment",
        )


class Test_NsdTopic(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_name = "test-nsd-topic"

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.db = Mock(dbbase.DbBase())
        self.fs = Mock(fsbase.FsBase())
        self.msg = Mock(msgbase.MsgBase())
        self.auth = Mock(authconn.Authconn(None, None, None))
        self.topic = NsdTopic(self.db, self.fs, self.msg, self.auth)
        self.topic.check_quota = Mock(return_value=None)  # skip quota

    @contextmanager
    def assertNotRaises(self, exception_type):
        try:
            yield None
        except exception_type:
            raise self.failureException("{} raised".format(exception_type.__name__))

    def create_desc_temp(self, template):
        old_desc = deepcopy(template)
        new_desc = deepcopy(template)
        return old_desc, new_desc

    def prepare_nsd_creation(self):
        self.fs.path = ""
        did = db_nsd_content["_id"]
        self.fs.get_params.return_value = {}
        self.fs.file_exists.return_value = False
        self.fs.file_open.side_effect = lambda path, mode: tempfile.TemporaryFile(
            mode="a+b"
        )
        self.db.get_one.side_effect = [
            {"_id": did, "_admin": deepcopy(db_nsd_content["_admin"])},
            None,
        ]
        test_nsd = deepcopy(db_nsd_content)
        del test_nsd["_id"]
        del test_nsd["_admin"]
        return did, test_nsd

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_normal_creation(self, mock_rename, mock_shutil):
        did, test_nsd = self.prepare_nsd_creation()
        self.db.create.return_value = did
        rollback = []

        did2, oid = self.topic.new(rollback, fake_session, {})
        db_args = self.db.create.call_args[0]
        msg_args = self.msg.write.call_args[0]
        self.assertEqual(len(rollback), 1, "Wrong rollback length")
        self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
        self.assertEqual(msg_args[1], "created", "Wrong message action")
        self.assertEqual(msg_args[2], {"_id": did}, "Wrong message content")
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(did2, did, "Wrong DB NSD id")
        self.assertIsNotNone(db_args[1]["_admin"]["created"], "Wrong creation time")
        self.assertEqual(
            db_args[1]["_admin"]["modified"],
            db_args[1]["_admin"]["created"],
            "Wrong modification time",
        )
        self.assertEqual(
            db_args[1]["_admin"]["projects_read"],
            [test_pid],
            "Wrong read-only project list",
        )
        self.assertEqual(
            db_args[1]["_admin"]["projects_write"],
            [test_pid],
            "Wrong read-write project list",
        )

        self.db.get_list.return_value = [db_vnfd_content]

        self.topic.upload_content(fake_session, did, test_nsd, {}, {"Content-Type": []})
        msg_args = self.msg.write.call_args[0]
        test_nsd["_id"] = did
        self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
        self.assertEqual(msg_args[1], "edited", "Wrong message action")
        self.assertEqual(msg_args[2], test_nsd, "Wrong message content")

        db_args = self.db.get_one.mock_calls[0][1]
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(db_args[1]["_id"], did, "Wrong DB NSD id")

        db_args = self.db.replace.call_args[0]
        self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
        self.assertEqual(db_args[1], did, "Wrong DB NSD id")

        admin = db_args[2]["_admin"]
        db_admin = db_nsd_content["_admin"]
        self.assertEqual(admin["created"], db_admin["created"], "Wrong creation time")
        self.assertGreater(
            admin["modified"], db_admin["created"], "Wrong modification time"
        )
        self.assertEqual(
            admin["projects_read"],
            db_admin["projects_read"],
            "Wrong read-only project list",
        )
        self.assertEqual(
            admin["projects_write"],
            db_admin["projects_write"],
            "Wrong read-write project list",
        )
        self.assertEqual(
            admin["onboardingState"], "ONBOARDED", "Wrong onboarding state"
        )
        self.assertEqual(
            admin["operationalState"], "ENABLED", "Wrong operational state"
        )
        self.assertEqual(admin["usageState"], "NOT_IN_USE", "Wrong usage state")

        storage = admin["storage"]
        self.assertEqual(storage["folder"], did + ":1", "Wrong storage folder")
        self.assertEqual(storage["descriptor"], "package", "Wrong storage descriptor")

        compare_desc(self, test_nsd, db_args[2], "NSD")
        revision_args = self.db.create.call_args[0]
        self.assertEqual(
            revision_args[0], self.topic.topic + "_revisions", "Wrong topic"
        )
        self.assertEqual(revision_args[1]["id"], db_args[2]["id"], "Wrong revision id")
        self.assertEqual(
            revision_args[1]["_id"], db_args[2]["_id"] + ":1", "Wrong revision _id"
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_pyangbind_validation_required_properties(
        self, mock_rename, mock_shutil
    ):
        did, test_nsd = self.prepare_nsd_creation()
        del test_nsd["id"]

        with self.assertRaises(
            EngineException, msg="Accepted NSD with a missing required property"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm("Error in pyangbind validation: '{}'".format("id")),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_pyangbind_validation_additional_properties(
        self, mock_rename, mock_shutil
    ):
        did, test_nsd = self.prepare_nsd_creation()
        test_nsd["extra-property"] = 0

        with self.assertRaises(
            EngineException, msg="Accepted NSD with an additional property"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error in pyangbind validation: {} ({})".format(
                    "json object contained a key that did not exist", "extra-property"
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_pyangbind_validation_property_types(
        self, mock_rename, mock_shutil
    ):
        did, test_nsd = self.prepare_nsd_creation()
        test_nsd["designer"] = {"key": 0}

        with self.assertRaises(
            EngineException, msg="Accepted NSD with a wrongly typed property"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error in pyangbind validation: {} ({})".format(
                    "json object contained a key that did not exist", "key"
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_input_validation_mgmt_network_virtual_link_protocol_data(
        self, mock_rename, mock_shutil
    ):
        did, test_nsd = self.prepare_nsd_creation()
        df = test_nsd["df"][0]
        mgmt_profile = {
            "id": "id",
            "virtual-link-desc-id": "mgmt",
            "virtual-link-protocol-data": {"associated-layer-protocol": "ipv4"},
        }
        df["virtual-link-profile"] = [mgmt_profile]

        with self.assertRaises(
            EngineException, msg="Accepted VLD with mgmt-network+ip-profile"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at df[id='{}']:virtual-link-profile[id='{}']:virtual-link-protocol-data"
                " You cannot set a virtual-link-protocol-data when mgmt-network is True".format(
                    df["id"], mgmt_profile["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_descriptor_dependencies_vnfd_id(
        self, mock_rename, mock_shutil
    ):
        did, test_nsd = self.prepare_nsd_creation()
        self.db.get_list.return_value = []

        with self.assertRaises(
            EngineException, msg="Accepted wrong VNFD ID reference"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
        )
        self.assertIn(
            norm(
                "'vnfd-id'='{}' references a non existing vnfd".format(
                    test_nsd["vnfd-id"][0]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_new_nsd_check_descriptor_dependencies_vld_vnfd_connection_point_ref(
        self, mock_rename, mock_shutil
    ):
        # Check Descriptor Dependencies: "vld[vnfd-connection-point-ref][vnfd-connection-point-ref]
        did, test_nsd = self.prepare_nsd_creation()
        vnfd_descriptor = deepcopy(db_vnfd_content)
        df = test_nsd["df"][0]
        affected_vnf_profile = df["vnf-profile"][0]
        affected_virtual_link = affected_vnf_profile["virtual-link-connectivity"][1]
        affected_cpd = vnfd_descriptor["ext-cpd"].pop()
        self.db.get_list.return_value = [vnfd_descriptor]

        with self.assertRaises(
            EngineException, msg="Accepted wrong VLD CP reference"
        ) as e:
            self.topic.upload_content(
                fake_session, did, test_nsd, {}, {"Content-Type": []}
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at df[id='{}']:vnf-profile[id='{}']:virtual-link-connectivity"
                "[virtual-link-profile-id='{}']:constituent-cpd-id='{}' references a "
                "non existing ext-cpd:id inside vnfd '{}'".format(
                    df["id"],
                    affected_vnf_profile["id"],
                    affected_virtual_link["virtual-link-profile-id"],
                    affected_cpd["id"],
                    vnfd_descriptor["id"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_edit_nsd(self):
        nsd_content = deepcopy(db_nsd_content)
        did = nsd_content["_id"]
        self.fs.file_exists.return_value = True
        self.fs.dir_ls.return_value = True
        with self.subTest(i=1, t="Normal Edition"):
            now = time()
            self.db.get_one.side_effect = [deepcopy(nsd_content), None]
            self.db.get_list.return_value = [db_vnfd_content]
            data = {"id": "new-nsd-id", "name": "new-nsd-name"}
            self.topic.edit(fake_session, did, data)
            db_args = self.db.replace.call_args[0]
            msg_args = self.msg.write.call_args[0]
            data["_id"] = did
            self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
            self.assertEqual(msg_args[1], "edited", "Wrong message action")
            self.assertEqual(msg_args[2], data, "Wrong message content")
            self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_args[1], did, "Wrong DB ID")
            self.assertEqual(
                db_args[2]["_admin"]["created"],
                nsd_content["_admin"]["created"],
                "Wrong creation time",
            )
            self.assertGreater(
                db_args[2]["_admin"]["modified"], now, "Wrong modification time"
            )
            self.assertEqual(
                db_args[2]["_admin"]["projects_read"],
                nsd_content["_admin"]["projects_read"],
                "Wrong read-only project list",
            )
            self.assertEqual(
                db_args[2]["_admin"]["projects_write"],
                nsd_content["_admin"]["projects_write"],
                "Wrong read-write project list",
            )
            self.assertEqual(db_args[2]["id"], data["id"], "Wrong NSD ID")
            self.assertEqual(db_args[2]["name"], data["name"], "Wrong NSD Name")
        with self.subTest(i=2, t="Conflict on Edit"):
            data = {"id": "fake-nsd-id", "name": "new-nsd-name"}
            self.db.get_one.side_effect = [
                nsd_content,
                {"_id": str(uuid4()), "id": data["id"]},
            ]
            with self.assertRaises(
                EngineException, msg="Accepted existing NSD ID"
            ) as e:
                self.topic.edit(fake_session, did, data)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                norm(
                    "{} with id '{}' already exists for this project".format(
                        "nsd", data["id"]
                    )
                ),
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=3, t="Check Envelope"):
            data = {"nsd": {"nsd": {"id": "new-nsd-id", "name": "new-nsd-name"}}}
            self.db.get_one.side_effect = [nsd_content, None]
            with self.assertRaises(
                EngineException, msg="Accepted NSD with wrong envelope"
            ) as e:
                self.topic.edit(fake_session, did, data, content=nsd_content)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.BAD_REQUEST, "Wrong HTTP status code"
            )
            self.assertIn(
                "'nsd' must be a list of only one element",
                norm(str(e.exception)),
                "Wrong exception text",
            )
        self.db.reset_mock()
        return

    def test_delete_nsd(self):
        did = db_nsd_content["_id"]
        self.db.get_one.return_value = db_nsd_content
        p_id = db_nsd_content["_admin"]["projects_read"][0]
        with self.subTest(i=1, t="Normal Deletion"):
            self.db.get_list.return_value = []
            self.db.del_one.return_value = {"deleted": 1}
            self.topic.delete(fake_session, did)
            db_args = self.db.del_one.call_args[0]
            msg_args = self.msg.write.call_args[0]
            self.assertEqual(msg_args[0], self.topic.topic_msg, "Wrong message topic")
            self.assertEqual(msg_args[1], "deleted", "Wrong message action")
            self.assertEqual(msg_args[2], {"_id": did}, "Wrong message content")
            self.assertEqual(db_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_args[1]["_id"], did, "Wrong DB ID")
            self.assertEqual(
                db_args[1]["_admin.projects_write.cont"],
                [p_id, "ANY"],
                "Wrong DB filter",
            )
            db_g1_args = self.db.get_one.call_args[0]
            self.assertEqual(db_g1_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_g1_args[1]["_id"], did, "Wrong DB NSD ID")
            db_gl_calls = self.db.get_list.call_args_list
            self.assertEqual(db_gl_calls[0][0][0], "nsrs", "Wrong DB topic")
            # self.assertEqual(db_gl_calls[0][0][1]["nsd-id"], did, "Wrong DB NSD ID")   # Filter changed after call
            self.assertEqual(db_gl_calls[1][0][0], "nsts", "Wrong DB topic")
            self.assertEqual(
                db_gl_calls[1][0][1]["netslice-subnet.ANYINDEX.nsd-ref"],
                db_nsd_content["id"],
                "Wrong DB NSD netslice-subnet nsd-ref",
            )
            self.db.set_one.assert_not_called()
            fs_del_calls = self.fs.file_delete.call_args_list
            self.assertEqual(fs_del_calls[0][0][0], did, "Wrong FS file id")
            self.assertEqual(fs_del_calls[1][0][0], did + "_", "Wrong FS folder id")
        with self.subTest(i=2, t="Conflict on Delete - NSD in use by nsr"):
            self.db.get_list.return_value = [{"_id": str(uuid4()), "name": "fake-nsr"}]
            with self.assertRaises(
                EngineException, msg="Accepted NSD in use by NSR"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                "there is at least one ns instance using this descriptor",
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=3, t="Conflict on Delete - NSD in use by NST"):
            self.db.get_list.side_effect = [
                [],
                [{"_id": str(uuid4()), "name": "fake-nst"}],
            ]
            with self.assertRaises(
                EngineException, msg="Accepted NSD in use by NST"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
            )
            self.assertIn(
                "there is at least one netslice template referencing this descriptor",
                norm(str(e.exception)),
                "Wrong exception text",
            )
        with self.subTest(i=4, t="Non-existent NSD"):
            excp_msg = "Not found any {} with filter='{}'".format("NSD", {"_id": did})
            self.db.get_one.side_effect = DbException(excp_msg, HTTPStatus.NOT_FOUND)
            with self.assertRaises(
                DbException, msg="Accepted non-existent NSD ID"
            ) as e:
                self.topic.delete(fake_session, did)
            self.assertEqual(
                e.exception.http_code, HTTPStatus.NOT_FOUND, "Wrong HTTP status code"
            )
            self.assertIn(
                norm(excp_msg), norm(str(e.exception)), "Wrong exception text"
            )
        with self.subTest(i=5, t="No delete because referenced by other project"):
            db_nsd_content["_admin"]["projects_read"].append("other_project")
            self.db.get_one = Mock(return_value=db_nsd_content)
            self.db.get_list = Mock(return_value=[])
            self.msg.write.reset_mock()
            self.db.del_one.reset_mock()
            self.fs.file_delete.reset_mock()

            self.topic.delete(fake_session, did)
            self.db.del_one.assert_not_called()
            self.msg.write.assert_not_called()
            db_g1_args = self.db.get_one.call_args[0]
            self.assertEqual(db_g1_args[0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_g1_args[1]["_id"], did, "Wrong DB VNFD ID")
            db_s1_args = self.db.set_one.call_args
            self.assertEqual(db_s1_args[0][0], self.topic.topic, "Wrong DB topic")
            self.assertEqual(db_s1_args[0][1]["_id"], did, "Wrong DB ID")
            self.assertIn(
                p_id, db_s1_args[0][1]["_admin.projects_write.cont"], "Wrong DB filter"
            )
            self.assertIsNone(
                db_s1_args[1]["update_dict"], "Wrong DB update dictionary"
            )
            self.assertEqual(
                db_s1_args[1]["pull_list"],
                {"_admin.projects_read": (p_id,), "_admin.projects_write": (p_id,)},
                "Wrong DB pull_list dictionary",
            )
            self.fs.file_delete.assert_not_called()
        self.db.reset_mock()
        return

    def prepare_nsd_validation(self):
        descriptor_name = "test_ns_descriptor"
        self.fs.file_open.side_effect = lambda path, mode: open(
            "/tmp/" + str(uuid4()), "a+b"
        )
        old_nsd, new_nsd = self.create_desc_temp(db_nsd_content)
        return descriptor_name, old_nsd, new_nsd

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_descriptor_ns_configuration_changed(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating NSD and NSD has changes in ns-configuration:config-primitive"""
        descriptor_name, old_nsd, new_nsd = self.prepare_nsd_validation()
        mock_safe_load.side_effect = [old_nsd, new_nsd]
        mock_detect_usage.return_value = True
        self.db.get_one.return_value = old_nsd
        old_nsd.update(
            {"ns-configuration": {"config-primitive": [{"name": "add-user"}]}}
        )
        new_nsd.update(
            {"ns-configuration": {"config-primitive": [{"name": "del-user"}]}}
        )

        with self.assertNotRaises(EngineException):
            self.topic._validate_descriptor_changes(
                old_nsd["_id"], descriptor_name, "/tmp", "/tmp:1"
            )
        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        self.assertEqual(mock_safe_load.call_count, 2)

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_descriptor_nsd_name_changed(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating NSD, NSD name has changed."""
        descriptor_name, old_nsd, new_nsd = self.prepare_nsd_validation()
        did = old_nsd["_id"]
        new_nsd["name"] = "nscharm-ns2"
        mock_safe_load.side_effect = [old_nsd, new_nsd]
        mock_detect_usage.return_value = True
        self.db.get_one.return_value = old_nsd

        with self.assertRaises(
            EngineException, msg="there are disallowed changes in the ns descriptor"
        ) as e:
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp", "/tmp:1"
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm("there are disallowed changes in the ns descriptor"),
            norm(str(e.exception)),
            "Wrong exception text",
        )

        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        self.assertEqual(mock_safe_load.call_count, 2)

    @patch("osm_nbi.descriptor_topics.detect_descriptor_usage")
    @patch("osm_nbi.descriptor_topics.yaml.safe_load")
    def test_validate_descriptor_nsd_name_changed_nsd_not_in_use(
        self, mock_safe_load, mock_detect_usage
    ):
        """Validating NSD, NSD name has changed, NSD is not in use."""
        descriptor_name, old_nsd, new_nsd = self.prepare_nsd_validation()
        did = old_nsd["_id"]
        new_nsd["name"] = "nscharm-ns2"
        mock_safe_load.side_effect = [old_nsd, new_nsd]
        mock_detect_usage.return_value = None
        self.db.get_one.return_value = old_nsd

        with self.assertNotRaises(Exception):
            self.topic._validate_descriptor_changes(
                did, descriptor_name, "/tmp", "/tmp:1"
            )

        self.db.get_one.assert_called_once()
        mock_detect_usage.assert_called_once()
        mock_safe_load.assert_not_called()

    def test_validate_vld_mgmt_network_with_virtual_link_protocol_data_on_valid_descriptor(
        self,
    ):
        indata = deepcopy(db_nsd_content)
        vld = indata["virtual-link-desc"][0]
        self.topic.validate_vld_mgmt_network_with_virtual_link_protocol_data(
            vld, indata
        )

    def test_validate_vld_mgmt_network_with_virtual_link_protocol_data_when_both_defined(
        self,
    ):
        indata = deepcopy(db_nsd_content)
        vld = indata["virtual-link-desc"][0]
        df = indata["df"][0]
        affected_vlp = {
            "id": "id",
            "virtual-link-desc-id": "mgmt",
            "virtual-link-protocol-data": {"associated-layer-protocol": "ipv4"},
        }
        df["virtual-link-profile"] = [affected_vlp]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_vld_mgmt_network_with_virtual_link_protocol_data(
                vld, indata
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at df[id='{}']:virtual-link-profile[id='{}']:virtual-link-protocol-data"
                " You cannot set a virtual-link-protocol-data when mgmt-network is True".format(
                    df["id"], affected_vlp["id"]
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_vnf_profiles_vnfd_id_on_valid_descriptor(self):
        indata = deepcopy(db_nsd_content)
        self.topic.validate_vnf_profiles_vnfd_id(indata)

    def test_validate_vnf_profiles_vnfd_id_when_missing_vnfd(self):
        indata = deepcopy(db_nsd_content)
        df = indata["df"][0]
        affected_vnf_profile = df["vnf-profile"][0]
        indata["vnfd-id"] = ["non-existing-vnfd"]
        with self.assertRaises(EngineException) as e:
            self.topic.validate_vnf_profiles_vnfd_id(indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at df[id='{}']:vnf_profile[id='{}']:vnfd-id='{}' "
                "does not match any vnfd-id".format(
                    df["id"],
                    affected_vnf_profile["id"],
                    affected_vnf_profile["vnfd-id"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_df_vnf_profiles_constituent_connection_points_on_valid_descriptor(
        self,
    ):
        nsd_descriptor = deepcopy(db_nsd_content)
        vnfd_descriptor = deepcopy(db_vnfd_content)
        df = nsd_descriptor["df"][0]
        vnfds_index = {vnfd_descriptor["id"]: vnfd_descriptor}
        self.topic.validate_df_vnf_profiles_constituent_connection_points(
            df, vnfds_index
        )

    def test_validate_df_vnf_profiles_constituent_connection_points_when_missing_connection_point(
        self,
    ):
        nsd_descriptor = deepcopy(db_nsd_content)
        vnfd_descriptor = deepcopy(db_vnfd_content)
        df = nsd_descriptor["df"][0]
        affected_vnf_profile = df["vnf-profile"][0]
        affected_virtual_link = affected_vnf_profile["virtual-link-connectivity"][1]
        vnfds_index = {vnfd_descriptor["id"]: vnfd_descriptor}
        affected_cpd = vnfd_descriptor["ext-cpd"].pop()
        with self.assertRaises(EngineException) as e:
            self.topic.validate_df_vnf_profiles_constituent_connection_points(
                df, vnfds_index
            )
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at df[id='{}']:vnf-profile[id='{}']:virtual-link-connectivity"
                "[virtual-link-profile-id='{}']:constituent-cpd-id='{}' references a "
                "non existing ext-cpd:id inside vnfd '{}'".format(
                    df["id"],
                    affected_vnf_profile["id"],
                    affected_virtual_link["virtual-link-profile-id"],
                    affected_cpd["id"],
                    vnfd_descriptor["id"],
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_check_conflict_on_edit_when_missing_constituent_vnfd_id(self):
        nsd_descriptor = deepcopy(db_nsd_content)
        invalid_vnfd_id = "invalid-vnfd-id"
        nsd_descriptor["id"] = "invalid-vnfd-id-ns"
        nsd_descriptor["vnfd-id"][0] = invalid_vnfd_id
        nsd_descriptor["df"][0]["vnf-profile"][0]["vnfd-id"] = invalid_vnfd_id
        nsd_descriptor["df"][0]["vnf-profile"][1]["vnfd-id"] = invalid_vnfd_id
        with self.assertRaises(EngineException) as e:
            self.db.get_list.return_value = []
            nsd_descriptor = self.topic.check_conflict_on_edit(
                fake_session, nsd_descriptor, [], "id"
            )
        self.assertEqual(
            e.exception.http_code, HTTPStatus.CONFLICT, "Wrong HTTP status code"
        )
        self.assertIn(
            norm(
                "Descriptor error at 'vnfd-id'='{}' references a non "
                "existing vnfd".format(invalid_vnfd_id)
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_vnffgd_descriptor_on_valid_descriptor(self):
        indata = yaml.safe_load(db_sfc_nsds_text)[0]
        vnffgd = indata.get("vnffgd")
        fg = vnffgd[0]
        self.topic.validate_vnffgd_data(fg, indata)

    def test_validate_vnffgd_descriptor_not_matching_nfp_position_element(self):
        indata = yaml.safe_load(db_sfc_nsds_text)[0]
        vnffgd = indata.get("vnffgd")
        fg = vnffgd[0]
        nfpd = fg.get("nfpd")[0]
        with self.assertRaises(EngineException) as e:
            fg.update({"nfp-position-element": [{"id": "test1"}]})
            self.topic.validate_vnffgd_data(fg, indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at vnffgd nfpd[id='{}']:nfp-position-element-id='{}' "
                "does not match any nfp-position-element".format(nfpd["id"], "test")
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )

    def test_validate_vnffgd_descriptor_not_matching_constituent_base_element_id(
        self,
    ):
        indata = yaml.safe_load(db_sfc_nsds_text)[0]
        vnffgd = indata.get("vnffgd")
        fg = vnffgd[0]
        fg["nfpd"][0]["position-desc-id"][0]["cp-profile-id"][0][
            "constituent-profile-elements"
        ][0]["constituent-base-element-id"] = "error_vnf"
        with self.assertRaises(EngineException) as e:
            self.topic.validate_vnffgd_data(fg, indata)
        self.assertEqual(
            e.exception.http_code,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Wrong HTTP status code",
        )
        self.assertIn(
            norm(
                "Error at vnffgd constituent_profile[id='{}']:vnfd-id='{}' "
                "does not match any constituent-base-element-id".format(
                    "vnf1", "error_vnf"
                )
            ),
            norm(str(e.exception)),
            "Wrong exception text",
        )


if __name__ == "__main__":
    unittest.main()
