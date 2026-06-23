# Copyright 2021 Canonical Ltd.
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
from unittest.mock import Mock, patch, MagicMock


from osm_common import msgbase
from osm_common.dbbase import DbException
from osm_lcm.vim_sdn import K8sClusterLcm, VcaLcm


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class TestVcaLcm(TestCase):
    @patch("osm_lcm.lcm_utils.Database")
    @patch("osm_lcm.lcm_utils.Filesystem")
    def setUp(self, mock_filesystem, mock_database):
        self.loop = asyncio.get_event_loop()
        self.msg = Mock(msgbase.MsgBase())
        self.lcm_tasks = Mock()
        self.config = {"database": {"driver": "mongo"}}
        self.vca_lcm = VcaLcm(self.msg, self.lcm_tasks, self.config)
        self.vca_lcm.db = Mock()
        self.vca_lcm.fs = Mock()

    def test_vca_lcm_create(self):
        vca_content = {"op_id": "order-id", "_id": "id"}
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        self.vca_lcm.update_db_2 = Mock()

        self.loop.run_until_complete(self.vca_lcm.create(vca_content, order_id))

        self.lcm_tasks.lock_HA.assert_called_with("vca", "create", "order-id")
        self.vca_lcm.db.encrypt_decrypt_fields.assert_called_with(
            db_vca,
            "decrypt",
            ["secret", "cacert"],
            schema_version="1.11",
            salt="vca-id",
        )
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {
                "_admin.operationalState": "ENABLED",
                "_admin.detailed-status": "Connectivity: ok",
            },
        )
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "create",
            "order-id",
            operationState="COMPLETED",
            detailed_status="VCA validated",
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_create_exception(self):
        vca_content = {"op_id": "order-id", "_id": "id"}
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        self.vca_lcm.n2vc.validate_vca.side_effect = Exception("failed")
        self.vca_lcm.update_db_2 = Mock()
        self.vca_lcm.update_db_2.side_effect = DbException("failed")
        self.loop.run_until_complete(self.vca_lcm.create(vca_content, order_id))

        self.lcm_tasks.lock_HA.assert_called_with("vca", "create", "order-id")
        self.vca_lcm.db.encrypt_decrypt_fields.assert_called_with(
            db_vca,
            "decrypt",
            ["secret", "cacert"],
            schema_version="1.11",
            salt="vca-id",
        )
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {
                "_admin.operationalState": "ERROR",
                "_admin.detailed-status": "Failed with exception: failed",
            },
        )
        self.lcm_tasks.unlock_HA.assert_not_called()
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_edit_success_no_config(self):
        vca_content = {
            "op_id": "order-id",
            "_id": "id",
            "description": "test-description",
        }
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        self.vca_lcm.update_db_2 = Mock()
        self.loop.run_until_complete(self.vca_lcm.edit(vca_content, order_id))
        self.vca_lcm.n2vc.validate_vca.assert_not_called()
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "edit",
            "order-id",
            operationState="COMPLETED",
            detailed_status="Edited",
        )
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {},
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_edit_success_config(self):
        vca_content = {"op_id": "order-id", "_id": "id", "cacert": "editcacert"}
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        self.vca_lcm.update_db_2 = Mock()
        self.loop.run_until_complete(self.vca_lcm.edit(vca_content, order_id))
        self.vca_lcm.n2vc.validate_vca.assert_called()
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "edit",
            "order-id",
            operationState="COMPLETED",
            detailed_status="Edited",
        )
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {
                "_admin.operationalState": "ENABLED",
                "_admin.detailed-status": "Connectivity: ok",
            },
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_edit_exception_no_config(self):
        vca_content = {
            "op_id": "order-id",
            "_id": "id",
            "description": "new-description",
        }
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        # validate_vca should not be called in this case
        self.vca_lcm.n2vc.validate_vca.side_effect = Exception("failed")
        self.vca_lcm.update_db_2 = Mock()
        self.loop.run_until_complete(self.vca_lcm.edit(vca_content, order_id))
        self.lcm_tasks.lock_HA.assert_called_with("vca", "edit", "order-id")
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "edit",
            "order-id",
            operationState="COMPLETED",
            detailed_status="Edited",
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_edit_exception_config(self):
        vca_content = {"op_id": "order-id", "_id": "id", "user": "new-user"}
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        # validate_vca should be called in this case
        self.vca_lcm.n2vc.validate_vca.side_effect = Exception("failed")
        self.vca_lcm.update_db_2 = Mock()
        self.loop.run_until_complete(self.vca_lcm.edit(vca_content, order_id))
        self.lcm_tasks.lock_HA.assert_called_with("vca", "edit", "order-id")
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "edit",
            "order-id",
            operationState="FAILED",
            detailed_status="Failed with exception: failed",
        )
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {
                "_admin.operationalState": "ERROR",
                "_admin.detailed-status": "Failed with exception: failed",
            },
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_edit_db_exception(self):
        vca_content = {
            "op_id": "order-id",
            "_id": "id",
            "description": "new-description",
        }
        db_vca = {
            "_id": "vca-id",
            "secret": "secret",
            "cacert": "cacert",
            "schema_version": "1.11",
        }
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.db.get_one.return_value = db_vca
        self.vca_lcm.n2vc.validate_vca = AsyncMock()
        self.vca_lcm.update_db_2 = Mock()
        self.vca_lcm.update_db_2.side_effect = DbException("failed")
        self.loop.run_until_complete(self.vca_lcm.edit(vca_content, order_id))
        self.vca_lcm.n2vc.validate_vca.assert_not_called()
        self.lcm_tasks.lock_HA.assert_called_with("vca", "edit", "order-id")
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {},
        )
        self.lcm_tasks.unlock_HA.assert_not_called()
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_delete(self):
        vca_content = {"op_id": "order-id", "_id": "id"}
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.update_db_2 = Mock()

        self.loop.run_until_complete(self.vca_lcm.delete(vca_content, order_id))

        self.lcm_tasks.lock_HA.assert_called_with("vca", "delete", "order-id")
        self.vca_lcm.db.del_one.assert_called_with("vca", {"_id": "id"})
        self.vca_lcm.update_db_2.assert_called_with("vca", "id", None)
        self.lcm_tasks.unlock_HA.assert_called_with(
            "vca",
            "delete",
            "order-id",
            operationState="COMPLETED",
            detailed_status="deleted",
        )
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")

    def test_vca_lcm_delete_exception(self):
        vca_content = {"op_id": "order-id", "_id": "id"}
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.vca_lcm.update_db_2 = Mock()
        self.vca_lcm.db.del_one.side_effect = Exception("failed deleting")
        self.vca_lcm.update_db_2.side_effect = DbException("failed")

        self.loop.run_until_complete(self.vca_lcm.delete(vca_content, order_id))

        self.lcm_tasks.lock_HA.assert_called_with("vca", "delete", "order-id")
        self.vca_lcm.db.del_one.assert_called_with("vca", {"_id": "id"})
        self.vca_lcm.update_db_2.assert_called_with(
            "vca",
            "id",
            {
                "_admin.operationalState": "ERROR",
                "_admin.detailed-status": "Failed with exception: failed deleting",
            },
        )
        self.lcm_tasks.unlock_HA.not_called()
        self.lcm_tasks.remove.assert_called_with("vca", "id", "order-id")


class TestK8SClusterLcm(TestCase):
    @patch("osm_lcm.vim_sdn.K8sHelm3Connector")
    @patch("osm_lcm.vim_sdn.K8sJujuConnector")
    @patch("osm_lcm.lcm_utils.Database")
    @patch("osm_lcm.lcm_utils.Filesystem")
    def setUp(
        self,
        mock_filesystem,
        mock_database,
        juju_connector,
        helm3_connector,
    ):
        self.loop = asyncio.get_event_loop()
        self.msg = Mock(msgbase.MsgBase())
        self.lcm_tasks = Mock()
        self.config = {"database": {"driver": "mongo"}}
        self.vca_config = {
            "VCA": {
                "helm3path": "/usr/local/bin/helm3",
                "kubectlpath": "/usr/bin/kubectl",
            }
        }
        self.k8scluster_lcm = K8sClusterLcm(self.msg, self.lcm_tasks, self.vca_config)
        self.k8scluster_lcm.db = Mock()
        self.k8scluster_lcm.fs = Mock()

    def test_k8scluster_edit(self):
        k8scluster_content = {"op_id": "op-id", "_id": "id"}
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.loop.run_until_complete(
            self.k8scluster_lcm.edit(k8scluster_content, order_id)
        )
        self.lcm_tasks.unlock_HA.assert_called_with(
            "k8scluster",
            "edit",
            "op-id",
            operationState="COMPLETED",
            detailed_status="Not implemented",
        )
        self.lcm_tasks.remove.assert_called_with("k8scluster", "id", order_id)

    def test_k8scluster_edit_lock_false(self):
        k8scluster_content = {"op_id": "op-id", "_id": "id"}
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = False
        self.loop.run_until_complete(
            self.k8scluster_lcm.edit(k8scluster_content, order_id)
        )
        self.lcm_tasks.unlock_HA.assert_not_called()
        self.lcm_tasks.remove.assert_not_called()

    def test_k8scluster_edit_no_opid(self):
        k8scluster_content = {"_id": "id"}
        order_id = "order-id"
        self.lcm_tasks.lock_HA.return_value = True
        self.loop.run_until_complete(
            self.k8scluster_lcm.edit(k8scluster_content, order_id)
        )
        self.lcm_tasks.unlock_HA.assert_called_with(
            "k8scluster",
            "edit",
            None,
            operationState="COMPLETED",
            detailed_status="Not implemented",
        )
        self.lcm_tasks.remove.assert_called_with("k8scluster", "id", order_id)

    def test_k8scluster_edit_no_orderid(self):
        k8scluster_content = {"op_id": "op-id", "_id": "id"}
        order_id = None
        self.lcm_tasks.lock_HA.return_value = True
        self.loop.run_until_complete(
            self.k8scluster_lcm.edit(k8scluster_content, order_id)
        )
        self.lcm_tasks.unlock_HA.assert_called_with(
            "k8scluster",
            "edit",
            "op-id",
            operationState="COMPLETED",
            detailed_status="Not implemented",
        )
        self.lcm_tasks.remove.assert_called_with("k8scluster", "id", order_id)
