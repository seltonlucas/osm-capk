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
from base64 import b64decode
from unittest import TestCase
from unittest.mock import Mock, patch


from osm_lcm.n2vc.store import DbMongoStore, MotorStore
from osm_lcm.n2vc.vca.connection_data import ConnectionData
from osm_lcm.n2vc.tests.unit.utils import AsyncMock
from osm_common.dbmongo import DbException


class TestDbMongoStore(TestCase):
    def setUp(self):
        self.store = DbMongoStore(Mock())
        self.loop = asyncio.get_event_loop()

    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_get_vca_connection_data(self, mock_base64_to_cacert):
        mock_base64_to_cacert.return_value = "cacert"
        conn_data = {
            "endpoints": ["1.2.3.4:17070"],
            "user": "admin",
            "secret": "1234",
            "cacert": "cacert",
            "pubkey": "pubkey",
            "lxd-cloud": "lxd-cloud",
            "lxd-credentials": "lxd-credentials",
            "k8s-cloud": "k8s-cloud",
            "k8s-credentials": "k8s-credentials",
            "model-config": {},
            "api-proxy": None,
        }
        db_get_one = conn_data.copy()
        db_get_one.update({"schema_version": "1.1", "_id": "id"})
        self.store.db.get_one.return_value = db_get_one
        connection_data = self.loop.run_until_complete(
            self.store.get_vca_connection_data("vca_id")
        )
        self.assertTrue(
            all(
                connection_data.__dict__[k.replace("-", "_")] == v
                for k, v in conn_data.items()
            )
        )

    def test_update_vca_endpoints(self):
        endpoints = ["1.2.3.4:17070"]
        self.store.db.get_one.side_effect = [None, {"api_endpoints": []}]
        self.store.db.create.side_effect = DbException("already exists")
        self.loop.run_until_complete(self.store.update_vca_endpoints(endpoints))
        self.assertEqual(self.store.db.get_one.call_count, 2)
        Mock()
        self.store.db.set_one.assert_called_once_with(
            "vca", {"_id": "juju"}, {"api_endpoints": endpoints}
        )

    def test_update_vca_endpoints_exception(self):
        endpoints = ["1.2.3.4:17070"]
        self.store.db.get_one.side_effect = [None, None]
        self.store.db.create.side_effect = DbException("already exists")
        with self.assertRaises(DbException):
            self.loop.run_until_complete(self.store.update_vca_endpoints(endpoints))
        self.assertEqual(self.store.db.get_one.call_count, 2)
        self.store.db.set_one.assert_not_called()

    def test_update_vca_endpoints_with_vca_id(self):
        endpoints = ["1.2.3.4:17070"]
        self.store.db.get_one.return_value = {}
        self.loop.run_until_complete(
            self.store.update_vca_endpoints(endpoints, "vca_id")
        )
        self.store.db.get_one.assert_called_once_with("vca", q_filter={"_id": "vca_id"})
        self.store.db.replace.assert_called_once_with(
            "vca", "vca_id", {"endpoints": endpoints}
        )

    def test_get_vca_endpoints(self):
        endpoints = ["1.2.3.4:17070"]
        db_data = {"api_endpoints": endpoints}
        db_returns = [db_data, None]
        expected_returns = [endpoints, []]
        returns = []
        self.store._get_juju_info = Mock()
        self.store._get_juju_info.side_effect = db_returns
        for _ in range(len(db_returns)):
            e = self.loop.run_until_complete(self.store.get_vca_endpoints())
            returns.append(e)
        self.assertEqual(expected_returns, returns)

    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_get_vca_endpoints_with_vca_id(self, mock_base64_to_cacert):
        expected_endpoints = ["1.2.3.4:17070"]
        mock_base64_to_cacert.return_value = "cacert"
        self.store.get_vca_connection_data = Mock()
        self.store.get_vca_connection_data.return_value = ConnectionData(
            **{
                "endpoints": expected_endpoints,
                "user": "admin",
                "secret": "1234",
                "cacert": "cacert",
            }
        )
        endpoints = self.loop.run_until_complete(self.store.get_vca_endpoints("vca_id"))
        self.store.get_vca_connection_data.assert_called_with("vca_id")
        self.assertEqual(expected_endpoints, endpoints)

    def test_get_vca_id(self):
        self.assertIsNone(self.loop.run_until_complete(self.store.get_vca_id()))

    def test_get_vca_id_with_vim_id(self):
        self.store.db.get_one.return_value = {"vca": "vca_id"}
        vca_id = self.loop.run_until_complete(self.store.get_vca_id("vim_id"))
        self.store.db.get_one.assert_called_once_with(
            "vim_accounts", q_filter={"_id": "vim_id"}, fail_on_empty=False
        )
        self.assertEqual(vca_id, "vca_id")


class TestMotorStore(TestCase):
    def setUp(self):
        self.store = MotorStore("uri")
        self.vca_collection = Mock()
        self.vca_collection.find_one = AsyncMock()
        self.vca_collection.insert_one = AsyncMock()
        self.vca_collection.replace_one = AsyncMock()
        self.encryption = Mock()
        self.encryption.admin_collection = Mock()
        self.encryption.admin_collection.find_one = AsyncMock()
        self.admin_collection = Mock()
        self.admin_collection.find_one = AsyncMock()
        self.admin_collection.insert_one = AsyncMock()
        self.admin_collection.replace_one = AsyncMock()
        self.vim_accounts_collection = Mock()
        self.vim_accounts_collection.find_one = AsyncMock()
        self.store.encryption._client = {
            "osm": {
                "admin": self.encryption.admin_collection,
            }
        }
        self.store._client = {
            "osm": {
                "vca": self.vca_collection,
                "admin": self.admin_collection,
                "vim_accounts": self.vim_accounts_collection,
            }
        }
        self.store._config = {"database_commonkey": "osm"}
        self.store.encryption._config = {"database_commonkey": "osm"}
        self.loop = asyncio.get_event_loop()

    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_get_vca_connection_data(self, mock_base64_to_cacert):
        mock_base64_to_cacert.return_value = "cacert"
        conn_data = {
            "endpoints": ["1.2.3.4:17070"],
            "user": "admin",
            "secret": "1234",
            "cacert": "cacert",
            "pubkey": "pubkey",
            "lxd-cloud": "lxd-cloud",
            "lxd-credentials": "lxd-credentials",
            "k8s-cloud": "k8s-cloud",
            "k8s-credentials": "k8s-credentials",
            "model-config": {},
            "api-proxy": None,
        }
        db_find_one = conn_data.copy()
        db_find_one.update({"schema_version": "1.1", "_id": "id"})
        self.vca_collection.find_one.return_value = db_find_one
        self.store.encryption.decrypt_fields = AsyncMock()
        connection_data = self.loop.run_until_complete(
            self.store.get_vca_connection_data("vca_id")
        )
        self.assertTrue(
            all(
                connection_data.__dict__[k.replace("-", "_")] == v
                for k, v in conn_data.items()
            )
        )

    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_get_vca_connection_data_exception(self, mock_base64_to_cacert):
        mock_base64_to_cacert.return_value = "cacert"
        self.vca_collection.find_one.return_value = None
        with self.assertRaises(Exception):
            self.loop.run_until_complete(self.store.get_vca_connection_data("vca_id"))

    def test_update_vca_endpoints(self):
        endpoints = ["1.2.3.4:17070"]
        self.admin_collection.find_one.side_effect = [None, {"api_endpoints": []}]
        self.admin_collection.insert_one.side_effect = DbException("already exists")
        self.loop.run_until_complete(self.store.update_vca_endpoints(endpoints))
        self.assertEqual(self.admin_collection.find_one.call_count, 2)
        self.admin_collection.replace_one.assert_called_once_with(
            {"_id": "juju"}, {"api_endpoints": ["1.2.3.4:17070"]}
        )

    def test_get_vca_connection_data_with_id(self):
        secret = "e7b253af37785045d1ca08b8d929e556"
        encrypted_secret = "kI46kRJh828ExSNpr16OG/q5a5/qTsE0bsHrv/W/2/g="
        cacert = "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUQ4ekNDQWx1Z0F3SUJBZ0lVRWlzTTBoQWxiYzQ0Z1ZhZWh6bS80ZUsyNnRZd0RRWUpLb1pJaHZjTkFRRUwKQlFBd0lURU5NQXNHQTFVRUNoTUVTblZxZFRFUU1BNEdBMVVFQXhNSGFuVnFkUzFqWVRBZUZ3MHlNVEEwTWpNeApNRFV3TXpSYUZ3MHpNVEEwTWpNeE1EVTFNelJhTUNFeERUQUxCZ05WQkFvVEJFcDFhblV4RURBT0JnTlZCQU1UCkIycDFhblV0WTJFd2dnR2lNQTBHQ1NxR1NJYjNEUUVCQVFVQUE0SUJqd0F3Z2dHS0FvSUJnUUNhTmFvNGZab2gKTDJWYThtdy9LdCs3RG9tMHBYTlIvbEUxSHJyVmZvbmZqZFVQV01zSHpTSjJZZXlXcUNSd3BiaHlLaE82N1c1dgpUY2RsV3Y3WGFLTGtsdVkraDBZY3BQT3BFTmZZYmxrNGk0QkV1L0wzYVY5MFFkUFFrMG94S01CS2R5QlBNZVNNCkJmS2pPWXdyOGgzM0ZWUWhmVkJnMXVGZ2tGaDdTamNuNHczUFdvc1BCMjNiVHBCbGR3VE9zemN4Qm9TaDNSVTkKTzZjb3lQdDdEN0drOCtHRlA3RGRUQTdoV1RkaUM4cDBkeHp2RUNmY0psMXNFeFEyZVprS1QvVzZyelNtVDhUTApCM0ErM1FDRDhEOEVsQU1IVy9zS25SeHphYU8welpNVmVlQnRnNlFGZ1F3M0dJMGo2ZTY0K2w3VExoOW8wSkZVCjdpUitPY01xUzVDY0NROGpWV3JPSk9Xc2dEbDZ4T2FFREczYnR5SVJHY29jbVcvcEZFQjNZd1A2S1BRTUIrNXkKWDdnZExEWmFGRFBVakZmblhkMnhHdUZlMnpRTDNVbXZEUkZuUlBBaW02QlpQbWo1OFh2emFhZXROa3lyaUZLZwp4Z0Z1dVpTcDUwV2JWdjF0MkdzOTMrRE53NlhFZHRFYnlWWUNBa28xTTY0MkozczFnN3NoQnRFQ0F3RUFBYU1qCk1DRXdEZ1lEVlIwUEFRSC9CQVFEQWdLa01BOEdBMVVkRXdFQi93UUZNQU1CQWY4d0RRWUpLb1pJaHZjTkFRRUwKQlFBRGdnR0JBRXYxM2o2ZGFVbDBqeERPSnNTV1ZJZS9JdXNXVTRpN2ZXSWlqMHAwRU1GNS9LTE8yemRndTR5SQoreVd2T3N5aVFPanEzMlRYVlo2bTRDSnBkR1dGVE5HK2lLdXVOU3M0N3g3Q3dmVUNBWm5VVzhyamd3ZWJyS3BmCkJMNEVQcTZTcW0rSmltN0VPankyMWJkY2cyUXdZb3A3eUhvaHcveWEvL0l6RTMzVzZxNHlJeEFvNDBVYUhPTEMKTGtGbnNVYitjcFZBeFlPZGp6bjFzNWhnclpuWXlETEl3WmtIdFdEWm94alUzeC9jdnZzZ1FzLytzTWYrRFU4RgpZMkJKRHJjQ1VQM2xzclc0QVpFMFplZkEwOTlncFEvb3dSN0REYnMwSjZUeFM4NGt6Tldjc1FuWnRraXZheHJNClkyVHNnaWVndFExVFdGRWpxLy9sUFV4emJCdmpnd1FBZm5CQXZGeVNKejdTa0VuVm5rUXJGaUlUQVArTHljQVIKMlg4UFI2ZGI1bEt0SitBSENDM3kvZmNQS2k0ZzNTL3djeXRRdmdvOXJ6ODRFalp5YUNTaGJXNG9jNzNrMS9RcAowQWtHRDU0ZGVDWWVPYVJNbW96c0w3ZzdxWkpFekhtODdOcVBYSy9EZFoweWNxaVFhMXY2T3QxNjdXNUlzMUkzCjBWb0IzUzloSlE9PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCgo="  # noqa: E501
        encrypted_cacert = "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"  # noqa: E501
        self.vca_collection.find_one.return_value = {
            "_id": "2ade7f0e-9b58-4dbd-93a3-4ec076185d39",
            "schema_version": "1.11",
            "endpoints": [],
            "user": "admin",
            "secret": encrypted_secret,
            "cacert": encrypted_cacert,
        }
        self.encryption.admin_collection.find_one.return_value = {
            "serial": b"l+U3HDp9td+UjQ+AN+Ypj/Uh7n3C+rMJueQNNxkIpWI="
        }
        connection_data = self.loop.run_until_complete(
            self.store.get_vca_connection_data("vca_id")
        )
        self.assertEqual(connection_data.endpoints, [])
        self.assertEqual(connection_data.user, "admin")
        self.assertEqual(connection_data.secret, secret)
        self.assertEqual(
            connection_data.cacert, b64decode(cacert.encode("utf-8")).decode("utf-8")
        )

    def test_update_vca_endpoints_exception(self):
        endpoints = ["1.2.3.4:17070"]
        self.admin_collection.find_one.side_effect = [None, None]
        self.admin_collection.insert_one.side_effect = DbException("already exists")
        with self.assertRaises(DbException):
            self.loop.run_until_complete(self.store.update_vca_endpoints(endpoints))
        self.assertEqual(self.admin_collection.find_one.call_count, 2)
        self.admin_collection.replace_one.assert_not_called()

    def test_update_vca_endpoints_with_vca_id(self):
        endpoints = ["1.2.3.4:17070"]
        self.vca_collection.find_one.return_value = {}
        self.loop.run_until_complete(
            self.store.update_vca_endpoints(endpoints, "vca_id")
        )
        self.vca_collection.find_one.assert_called_once_with({"_id": "vca_id"})
        self.vca_collection.replace_one.assert_called_once_with(
            {"_id": "vca_id"}, {"endpoints": endpoints}
        )

    def test_get_vca_endpoints(self):
        endpoints = ["1.2.3.4:17070"]
        db_data = {"api_endpoints": endpoints}
        db_returns = [db_data, None]
        expected_returns = [endpoints, []]
        returns = []
        self.admin_collection.find_one.side_effect = db_returns
        for _ in range(len(db_returns)):
            e = self.loop.run_until_complete(self.store.get_vca_endpoints())
            returns.append(e)
        self.assertEqual(expected_returns, returns)

    @patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def test_get_vca_endpoints_with_vca_id(self, mock_base64_to_cacert):
        expected_endpoints = ["1.2.3.4:17070"]
        mock_base64_to_cacert.return_value = "cacert"
        self.store.get_vca_connection_data = AsyncMock()
        self.store.get_vca_connection_data.return_value = ConnectionData(
            **{
                "endpoints": expected_endpoints,
                "user": "admin",
                "secret": "1234",
                "cacert": "cacert",
            }
        )
        endpoints = self.loop.run_until_complete(self.store.get_vca_endpoints("vca_id"))
        self.store.get_vca_connection_data.assert_called_with("vca_id")
        self.assertEqual(expected_endpoints, endpoints)

    def test_get_vca_id(self):
        self.assertIsNone(self.loop.run_until_complete((self.store.get_vca_id())))

    def test_get_vca_id_with_vim_id(self):
        self.vim_accounts_collection.find_one.return_value = {"vca": "vca_id"}
        vca_id = self.loop.run_until_complete(self.store.get_vca_id("vim_id"))
        self.vim_accounts_collection.find_one.assert_called_once_with({"_id": "vim_id"})
        self.assertEqual(vca_id, "vca_id")
