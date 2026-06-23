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

__author__ = "Alfonso Tierno, alfonso.tiernosepulveda@telefonica.com"
__date__ = "2020-06-17"

from copy import deepcopy
import unittest
from unittest import TestCase
from unittest.mock import patch, Mock
from osm_nbi.base_topic import (
    BaseTopic,
    EngineException,
    NBIBadArgumentsException,
    detect_descriptor_usage,
    update_descriptor_usage_state,
)
from osm_common import dbbase
from osm_nbi.tests.test_pkg_descriptors import db_vnfds_text, db_nsds_text
import yaml

db_vnfd_content = yaml.safe_load(db_vnfds_text)[0]
db_nsd_content = yaml.safe_load(db_nsds_text)[0]


class Test_BaseTopic(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_name = "test-base-topic"

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.db = Mock(dbbase.DbBase())

    def test_update_input_with_kwargs(self):
        test_set = (
            # (descriptor content, kwargs, expected descriptor (None=fails), message)
            (
                {"a": {"none": None}},
                {"a.b.num": "v"},
                {"a": {"none": None, "b": {"num": "v"}}},
                "create dict",
            ),
            (
                {"a": {"none": None}},
                {"a.none.num": "v"},
                {"a": {"none": {"num": "v"}}},
                "create dict over none",
            ),
            (
                {"a": {"b": {"num": 4}}},
                {"a.b.num": "v"},
                {"a": {"b": {"num": "v"}}},
                "replace_number",
            ),
            (
                {"a": {"b": {"num": 4}}},
                {"a.b.num.c.d": "v"},
                {"a": {"b": {"num": {"c": {"d": "v"}}}}},
                "create dict over number",
            ),
            (
                {"a": {"b": {"num": 4}}},
                {"a.b": "v"},
                {"a": {"b": "v"}},
                "replace dict with a string",
            ),
            (
                {"a": {"b": {"num": 4}}},
                {"a.b": None},
                {"a": {}},
                "replace dict with None",
            ),
            (
                {"a": [{"b": {"num": 4}}]},
                {"a.b.num": "v"},
                None,
                "create dict over list should fail",
            ),
            (
                {"a": [{"b": {"num": 4}}]},
                {"a.0.b.num": "v"},
                {"a": [{"b": {"num": "v"}}]},
                "set list",
            ),
            (
                {"a": [{"b": {"num": 4}}]},
                {"a.3.b.num": "v"},
                {"a": [{"b": {"num": 4}}, None, None, {"b": {"num": "v"}}]},
                "expand list",
            ),
            ({"a": [[4]]}, {"a.0.0": "v"}, {"a": [["v"]]}, "set nested list"),
            (
                {"a": [[4]]},
                {"a.0.2": "v"},
                {"a": [[4, None, "v"]]},
                "expand nested list",
            ),
            (
                {"a": [[4]]},
                {"a.2.2": "v"},
                {"a": [[4], None, {"2": "v"}]},
                "expand list and add number key",
            ),
            ({"a": None}, {"b.c": "v"}, {"a": None, "b": {"c": "v"}}, "expand at root"),
        )
        for desc, kwargs, expected, message in test_set:
            if expected is None:
                self.assertRaises(
                    EngineException, BaseTopic._update_input_with_kwargs, desc, kwargs
                )
            else:
                BaseTopic._update_input_with_kwargs(desc, kwargs)
                self.assertEqual(desc, expected, message)

    def test_detect_descriptor_usage_empty_descriptor(self):
        descriptor = {}
        db_collection = "vnfds"
        with self.assertRaises(EngineException) as error:
            detect_descriptor_usage(descriptor, db_collection, self.db)
            self.assertIn(
                "Argument is mandatory and can not be empty, Bad arguments: descriptor",
                error,
                "Error message is wrong.",
            )
        self.db.get_list.assert_not_called()

    def test_detect_descriptor_usage_empty_db_argument(self):
        descriptor = deepcopy(db_vnfd_content)
        db_collection = "vnfds"
        db = None
        with self.assertRaises(EngineException) as error:
            detect_descriptor_usage(descriptor, db_collection, db)
            self.assertIn(
                "A valid DB object should be provided, Bad arguments: db",
                error,
                "Error message is wrong.",
            )
        self.db.get_list.assert_not_called()

    def test_detect_descriptor_usage_which_is_in_use(self):
        descriptor = deepcopy(db_vnfd_content)
        db_collection = "vnfds"
        self.db.get_list.side_effect = [deepcopy(db_vnfd_content)]
        expected = True
        result = detect_descriptor_usage(descriptor, db_collection, self.db)
        self.assertEqual(result, expected, "wrong result")
        self.db.get_list.assert_called_once_with(
            "vnfrs", {"vnfd-id": descriptor["_id"]}
        )

    def test_detect_descriptor_usage_which_is_not_in_use(self):
        descriptor = deepcopy(db_nsd_content)
        self.db.get_list.return_value = []
        db_collection = "nsds"
        expected = None
        result = detect_descriptor_usage(descriptor, db_collection, self.db)
        self.assertEqual(result, expected, "wrong result")
        self.db.get_list.assert_called_once_with("nsrs", {"nsd-id": descriptor["_id"]})

    def test_detect_descriptor_usage_wrong_desc_format(self):
        descriptor = deepcopy(db_nsd_content)
        descriptor.pop("_id")
        db_collection = "nsds"
        with self.assertRaises(EngineException) as error:
            detect_descriptor_usage(descriptor, db_collection, self.db)
            self.assertIn("KeyError", error, "wrong error type")
        self.db.get_list.assert_not_called()

    def test_detect_descriptor_usage_wrong_db_collection(self):
        descriptor = deepcopy(db_vnfd_content)
        descriptor.pop("_id")
        db_collection = "vnf"
        with self.assertRaises(EngineException) as error:
            detect_descriptor_usage(descriptor, db_collection, self.db)
            self.assertIn(
                "db_collection should be equal to vnfds or nsds, db_collection",
                error,
                "wrong error type",
            )

        self.db.get_list.assert_not_called()

    @patch("osm_nbi.base_topic.detect_descriptor_usage")
    def test_update_descriptor_usage_state_to_in_use(self, mock_descriptor_usage):
        db_collection = "vnfds"
        descriptor = deepcopy(db_vnfd_content)
        mock_descriptor_usage.return_value = True
        descriptor_update = {"_admin.usageState": "IN_USE"}
        update_descriptor_usage_state(descriptor, db_collection, self.db)
        self.db.set_one.assert_called_once_with(
            db_collection, {"_id": descriptor["_id"]}, update_dict=descriptor_update
        )

    @patch("osm_nbi.base_topic.detect_descriptor_usage")
    def test_update_descriptor_usage_state_to_not_in_use(self, mock_descriptor_usage):
        db_collection = "nsds"
        descriptor = deepcopy(db_nsd_content)
        mock_descriptor_usage.return_value = False
        descriptor_update = {"_admin.usageState": "NOT_IN_USE"}
        update_descriptor_usage_state(descriptor, db_collection, self.db)
        self.db.set_one.assert_called_once_with(
            db_collection, {"_id": descriptor["_id"]}, update_dict=descriptor_update
        )

    @patch("osm_nbi.base_topic.detect_descriptor_usage")
    def test_update_descriptor_usage_state_db_exception(self, mock_descriptor_usage):
        db_collection = "nsd"
        descriptor = deepcopy(db_nsd_content)
        mock_descriptor_usage.side_effect = NBIBadArgumentsException
        with self.assertRaises(EngineException) as error:
            update_descriptor_usage_state(descriptor, db_collection, self.db)
            self.assertIn(
                "db_collection should be equal to vnfds or nsds, db_collection",
                error,
                "wrong error type",
            )
        self.db.set_one.assert_not_called()


if __name__ == "__main__":
    unittest.main()
