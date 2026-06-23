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

import os
import re
import tempfile
from unittest import TestCase
from unittest.mock import Mock

from osm_lcm.lcm import Lcm
from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem

from osm_lcm.lcm_utils import LcmException


def create_lcm_config(
    source_path: str, destination_path: str, line_number=None
) -> None:
    """This function creates new lcm_config files by
    using the config file template. If line number is provided,
    it removes the line from file.
    Args:
        source_path: (str)  source file path
        destination_path: (str) destination file path
        line_number:    (int)   line to be deleted
    """
    with open(source_path, "r+") as fs:
        # read and store all lines into list
        contents = fs.readlines()

    with open(destination_path, "w") as fd:
        if line_number:
            if line_number < 0:
                raise LcmException("Line number can not be smaller than zero")
            contents.pop(line_number)
        contents = "".join(contents)
        fd.write(contents)


def check_file_content(health_check_file: str) -> str:
    """Get the health check file contents
    Args:
        health_check_file: (str) file path

    Returns:
        contents:   (str) health check file content
    """
    with open(health_check_file, "r") as hc:
        contents = hc.read()
        return contents


class TestLcm(TestCase):
    def setUp(self):
        self.config_file = os.getcwd() + "/osm_lcm/tests/test_lcm_config_file.yaml"
        self.config_file_without_storage_path = tempfile.mkstemp()[1]
        Database.instance = None
        self.db = Mock(Database({"database": {"driver": "memory"}}).instance.db)
        Database().instance.db = self.db
        Filesystem.instance = None
        self.fs = Mock(
            Filesystem({"storage": {"driver": "local", "path": "/"}}).instance.fs
        )
        Filesystem.instance.fs = self.fs
        self.fs.path = "/"
        self.my_lcm = Lcm(config_file=self.config_file)

    def test_get_health_check_file_from_config_file(self):
        self.assertEqual(self.my_lcm.health_check_file, "/tmp/storage/time_last_ping")

    # def test_health_check_file_not_in_config_file(self):
    #     create_lcm_config(self.config_file, self.config_file_without_storage_path, 38)
    #     with self.assertRaises(LcmException):
    #         Lcm(config_file=self.config_file_without_storage_path)

    async def test_kafka_admin_topic_ping_command(self):
        params = {
            "to": "lcm",
            "from": "lcm",
            "worker_id": self.my_lcm.worker_id,
        }
        self.my_lcm.health_check_file = tempfile.mkstemp()[1]
        await self.my_lcm.kafka_read_callback("admin", "ping", params)
        pattern = "[0-9]{10}.[0-9]{5,8}"
        # Epoch time is written in health check file.
        result = re.findall(pattern, check_file_content(self.my_lcm.health_check_file))
        self.assertTrue(result)

    async def test_kafka_wrong_topic_ping_command(self):
        params = {
            "to": "lcm",
            "from": "lcm",
            "worker_id": self.my_lcm.worker_id,
        }
        self.my_lcm.health_check_file = tempfile.mkstemp()[1]
        await self.my_lcm.kafka_read_callback("kafka", "ping", params)
        pattern = "[0-9]{10}.[0-9]{5,8}"
        # Health check file is empty.
        result = re.findall(pattern, check_file_content(self.my_lcm.health_check_file))
        self.assertFalse(result)

    async def test_kafka_admin_topic_ping_command_wrong_worker_id(self):
        params = {
            "to": "lcm",
            "from": "lcm",
            "worker_id": 5,
        }
        self.my_lcm.health_check_file = tempfile.mkstemp()[1]
        await self.my_lcm.kafka_read_callback("admin", "ping", params)
        pattern = "[0-9]{10}.[0-9]{5,8}"
        # Health check file is empty.
        result = re.findall(pattern, check_file_content(self.my_lcm.health_check_file))
        self.assertFalse(result)
