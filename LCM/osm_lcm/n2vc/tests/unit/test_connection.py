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
from unittest import TestCase
from unittest.mock import Mock, patch


from osm_lcm.n2vc.tests.unit.utils import AsyncMock
from osm_lcm.n2vc.vca import connection


class TestConnection(TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.store = AsyncMock()

    def test_load_from_store(self):
        self.loop.run_until_complete(connection.get_connection(self.store, "vim_id"))

        self.store.get_vca_connection_data.assert_called_once()

    def test_cloud_properties(self):
        conn = self.loop.run_until_complete(
            connection.get_connection(self.store, "vim_id")
        )
        conn._data = Mock()
        conn._data.lxd_cloud = "name"
        conn._data.k8s_cloud = "name"
        conn._data.lxd_credentials = "credential"
        conn._data.k8s_credentials = "credential"

        self.assertEqual(conn.lxd_cloud.name, "name")
        self.assertEqual(conn.lxd_cloud.credential_name, "credential")
        self.assertEqual(conn.k8s_cloud.name, "name")
        self.assertEqual(conn.k8s_cloud.credential_name, "credential")

    @patch("osm_lcm.n2vc.vca.connection.EnvironConfig")
    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_load_from_env(self, mock_base64_to_cacert, mock_env):
        mock_base64_to_cacert.return_value = "cacert"
        mock_env.return_value = {
            "endpoints": "1.2.3.4:17070",
            "user": "user",
            "secret": "secret",
            "cacert": "cacert",
            "pubkey": "pubkey",
            "cloud": "cloud",
            "credentials": "credentials",
            "k8s_cloud": "k8s_cloud",
            "k8s_credentials": "k8s_credentials",
            "model_config": {},
            "api-proxy": "api_proxy",
        }
        self.store.get_vca_endpoints.return_value = ["1.2.3.5:17070"]
        self.loop.run_until_complete(connection.get_connection(self.store))
        self.store.get_vca_connection_data.assert_not_called()
