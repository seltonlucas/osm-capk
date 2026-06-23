# Copyright 2022 Canonical Ltd.
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

from unittest import TestCase
import os
import tempfile

from osm_lcm.lcm_hc import get_health_check_file
from osm_lcm.lcm_utils import LcmException
from test_lcm import create_lcm_config


class TestLcmHealthCheck(TestCase):
    def setUp(self):
        self.config_temp = os.getcwd() + "/osm_lcm/tests/test_lcm_config_file.yaml"

    def test_get_health_check_path(self):
        with self.subTest(i=1, t="Empty Config Input"):
            hc_path = get_health_check_file()
            expected_hc_path = "/app/storage/time_last_ping"
            self.assertEqual(hc_path, expected_hc_path)

        with self.subTest(i=2, t="Config Input as Dictionary"):
            config_dict = {"storage": {"path": "/tmp/sample_hc"}}
            hc_path = get_health_check_file(config_dict)
            expected_hc_path = "/tmp/sample_hc/time_last_ping"
            self.assertEqual(hc_path, expected_hc_path)

        with self.subTest(i=3, t="Config Input as Dictionary with wrong format"):
            config_dict = {"folder": {"path": "/tmp/sample_hc"}}
            # it will return default health check path
            hc_path = get_health_check_file(config_dict)
            expected_hc_path = "/app/storage/time_last_ping"
            self.assertEqual(hc_path, expected_hc_path)

    def test_get_health_check_path_config_file_not_found(self):
        # open raises the FileNotFoundError
        with self.assertRaises(LcmException):
            get_health_check_file("/tmp2/config_yaml")

    def test_get_health_check_path_config_file(self):
        config_file = tempfile.mkstemp()[1]
        create_lcm_config(self.config_temp, config_file)
        hc_path = get_health_check_file(config_file)
        expected_hc_path = "/tmp/storage/time_last_ping"
        self.assertEqual(hc_path, expected_hc_path)

    def test_get_health_check_path_config_file_empty(self):
        new_config = tempfile.mkstemp()[1]
        # Empty file will cause AttributeError
        # and it will raise LCMException
        with self.assertRaises(LcmException):
            get_health_check_file(new_config)

    def test_get_health_check_path_config_file_not_include_storage_path(self):
        config_file = tempfile.mkstemp()[1]
        create_lcm_config(self.config_temp, config_file, 36)
        # It will return default health check path
        hc_path = get_health_check_file(config_file)
        expected_hc_path = "/app/storage/time_last_ping"
        self.assertEqual(hc_path, expected_hc_path)
