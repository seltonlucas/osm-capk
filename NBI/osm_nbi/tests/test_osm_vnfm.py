# Copyright 2021 Selvi Jayaraman (Tata Elxsi)
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

__author__ = "Selvi Jayaraman <selvi.j@tataelxsi.co.in>"

import unittest
from uuid import uuid4
from unittest.mock import Mock, patch, mock_open
from osm_common.dbmemory import DbMemory
from osm_common.fsbase import FsBase
from osm_common.msgbase import MsgBase
from osm_nbi.vnf_instance_topics import VnfInstances, VnfLcmOpTopic
from osm_nbi.instance_topics import NsrTopic
from osm_nbi.tests.test_db_descriptors import (
    db_vim_accounts_text,
    db_vnfm_vnfd_text,
    db_nsds_text,
    db_nsrs_text,
    db_vnfrs_text,
    db_nslcmops_text,
)
import yaml


class TestVnfInstances(unittest.TestCase):
    def setUp(self):
        self.db = DbMemory()
        self.fs = Mock(FsBase())
        self.msg = Mock(MsgBase())
        self.vnfinstances = VnfInstances(self.db, self.fs, self.msg, None)
        self.nsrtopic = NsrTopic(self.db, self.fs, self.msg, None)
        self.db.create_list("vim_accounts", yaml.safe_load(db_vim_accounts_text))
        self.db.create_list("vnfds", yaml.safe_load(db_vnfm_vnfd_text))
        self.vnfd = self.db.get_list("vnfds")[0]
        self.vnfd_id = self.vnfd["id"]
        self.vnfd_project = self.vnfd["_admin"]["projects_read"][0]

        self.vim = self.db.get_list("vim_accounts")[0]
        self.vim_id = self.vim["_id"]

    @patch("osm_nbi.descriptor_topics.shutil")
    @patch("osm_nbi.descriptor_topics.os.rename")
    def test_create_identifier(self, mock_rename, mock_shutil):
        session = {
            "force": True,
            "admin": False,
            "public": False,
            "project_id": [self.vnfd_project],
            "method": "write",
        }
        indata = {
            "vnfdId": self.vnfd_id,
            "vnfInstanceName": "vnf_instance_name",
            "vnfInstanceDescription": "vnf instance description",
            "vimAccountId": self.vim_id,
            "additionalParams": {
                "virtual-link-desc": [{"id": "mgmt-net", "mgmt-network": True}],
                "constituent-cpd-id": "vnf-cp0-ext",
                "virtual-link-profile-id": "mgmt-net",
            },
        }
        rollback = []
        self.fs.path = ""
        self.fs.get_params.return_value = {}
        self.fs.file_exists.return_value = False
        self.fs.file_open.side_effect = lambda path, mode: open(
            "/tmp/" + str(uuid4()), "a+b"
        )

        vnfr_id, _ = self.vnfinstances.new(
            rollback, session, indata, {}, headers={"Content-Type": []}
        )
        vnfr = self.db.get_one("vnfrs")
        self.assertEqual(
            vnfr_id, vnfr["id"], "Mismatch between return id and database id"
        )
        self.assertEqual(
            "NOT_INSTANTIATED",
            vnfr["_admin"]["nsState"],
            "Database record must contain 'nsState' NOT_INSTANTIATED",
        )
        self.assertEqual(
            self.vnfd_id,
            vnfr["vnfd-ref"],
            "vnfr record is not properly created for the given vnfd",
        )

    def test_show_vnfinstance(self):
        session = {
            "force": False,
            "admin": False,
            "public": False,
            "project_id": [self.vnfd_project],
            "method": "write",
        }
        filter_q = {}
        self.db.create_list("vnfrs", yaml.safe_load(db_vnfrs_text))
        actual_vnfr = self.db.get_list("vnfrs")[0]
        id = actual_vnfr["_id"]
        expected_vnfr = self.vnfinstances.show(session, id, filter_q)
        self.assertEqual(
            actual_vnfr["_id"],
            expected_vnfr["_id"],
            "Mismatch between return vnfr Id and database vnfr Id",
        )

    def test_delete_vnfinstance(self):
        session = {
            "force": False,
            "admin": False,
            "public": False,
            "project_id": [self.vnfd_project],
            "method": "delete",
        }
        self.db.create_list("vnfrs", yaml.safe_load(db_vnfrs_text))
        self.db.create_list("nsrs", yaml.safe_load(db_nsrs_text))
        self.db.create_list("nsds", yaml.safe_load(db_nsds_text))

        self.vnfr = self.db.get_list("vnfrs")[0]
        self.vnfr_id = self.vnfr["_id"]
        self.db.set_one = self.db.set_one
        self.db.set_one = Mock()

        self.vnfinstances.delete(session, self.vnfr_id)
        msg_args = self.msg.write.call_args[0]
        self.assertEqual(msg_args[1], "deleted", "Wrong message action")


class TestVnfLcmOpTopic(unittest.TestCase):
    def setUp(self):
        self.db = DbMemory()
        self.fs = Mock(FsBase())
        self.fs.get_params.return_value = {"./fake/folder"}
        self.fs.file_open = mock_open()
        self.msg = Mock(MsgBase())

        self.vnflcmop_topic = VnfLcmOpTopic(self.db, self.fs, self.msg, None)
        self.vnflcmop_topic.check_quota = Mock(return_value=None)  # skip quota

        self.db.create_list("vim_accounts", yaml.safe_load(db_vim_accounts_text))
        self.db.create_list("nsds", yaml.safe_load(db_nsds_text))
        self.db.create_list("vnfds", yaml.safe_load(db_vnfm_vnfd_text))
        self.db.create_list("vnfrs", yaml.safe_load(db_vnfrs_text))
        self.db.create_list("nsrs", yaml.safe_load(db_nsrs_text))

        self.vnfd = self.db.get_list("vnfds")[0]
        self.vnfd_id = self.vnfd["_id"]
        self.vnfr = self.db.get_list("vnfrs")[0]
        self.vnfr_id = self.vnfr["_id"]

        self.vnfd_project = self.vnfd["_admin"]["projects_read"][0]

        self.vim = self.db.get_list("vim_accounts")[0]
        self.vim_id = self.vim["_id"]

    def test_create_vnf_instantiate(self):
        session = {
            "force": False,
            "admin": False,
            "public": False,
            "project_id": [self.vnfd_project],
            "method": "write",
        }
        indata = {
            "vnfInstanceId": self.vnfr_id,
            "lcmOperationType": "instantiate",
            "vnfName": "vnf_instance_name",
            "vnfDescription": "vnf instance description",
            "vnfId": self.vnfd_id,
            "vimAccountId": self.vim_id,
        }
        rollback = []
        headers = {}
        vnflcmop_id, nsName, _ = self.vnflcmop_topic.new(
            rollback, session, indata, kwargs=None, headers=headers
        )
        vnflcmop_info = self.db.get_one("nslcmops")
        self.assertEqual(
            vnflcmop_id,
            vnflcmop_info["_id"],
            "Mismatch between return id and database '_id'",
        )
        self.assertTrue(
            vnflcmop_info["lcmOperationType"] == "instantiate",
            "Database record must contain 'lcmOperationType=instantiate'",
        )

    def test_show_vnflmcop(self):
        session = {
            "force": False,
            "admin": False,
            "public": False,
            "project_id": [self.vnfd_project],
            "method": "write",
        }
        self.db.create_list("nslcmops", yaml.safe_load(db_nslcmops_text))
        filter_q = {}
        actual_lcmop = self.db.get_list("nslcmops")[0]
        id = actual_lcmop["_id"]
        vnfr = self.db.get_list("vnfrs")[0]
        vnfr_id = vnfr["_id"]
        vnflcmop = self.vnflcmop_topic.show(session, id, filter_q)
        _id = vnflcmop["vnfInstanceId"]
        self.assertEqual(
            _id,
            vnfr_id,
            "Mismatch between vnflcmop's vnfInstanceId and database vnfr's id",
        )
