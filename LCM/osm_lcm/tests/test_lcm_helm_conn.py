##
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

import asynctest
import logging

from osm_lcm import lcm_helm_conn
from osm_lcm.lcm_helm_conn import LCMHelmConn
from asynctest.mock import Mock
from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem
from osm_lcm.data_utils.lcm_config import VcaConfig

__author__ = "Isabel Lloret <illoret@indra.es>"


class TestLcmHelmConn(asynctest.TestCase):
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    async def setUp(self):
        Database.instance = None
        self.db = Mock(Database({"database": {"driver": "memory"}}).instance.db)
        Database().instance.db = self.db

        Filesystem.instance = None
        self.fs = asynctest.Mock(
            Filesystem({"storage": {"driver": "local", "path": "/"}}).instance.fs
        )

        Filesystem.instance.fs = self.fs
        self.fs.path = "/"

        vca_config = {
            "helmpath": "/usr/local/bin/helm",
            "helm3path": "/usr/local/bin/helm3",
            "kubectlpath": "/usr/bin/kubectl",
        }
        lcm_helm_conn.K8sHelm3Connector = asynctest.Mock(
            lcm_helm_conn.K8sHelm3Connector
        )
        vca_config = VcaConfig(vca_config)
        self.helm_conn = LCMHelmConn(vca_config=vca_config, log=self.logger)

    @asynctest.fail_on(active_handles=True)
    async def test_create_execution_environment(self):
        namespace = "testnamespace"
        db_dict = {}
        artifact_path = "helm_sample_charm"
        chart_model = "helm_sample_charm"
        helm_chart_id = "helm_sample_charm_0001"
        self.helm_conn._k8sclusterhelm3.install = asynctest.CoroutineMock(
            return_value=None
        )
        self.helm_conn._k8sclusterhelm3.generate_kdu_instance_name = Mock()
        self.helm_conn._k8sclusterhelm3.generate_kdu_instance_name.return_value = (
            helm_chart_id
        )

        self.db.get_one.return_value = {"_admin": {"helm-chart-v3": {"id": "myk8s_id"}}}
        ee_id, _ = await self.helm_conn.create_execution_environment(
            namespace,
            db_dict,
            artifact_path=artifact_path,
            chart_model=chart_model,
            vca_type="helm-v3",
        )
        self.assertEqual(
            ee_id,
            "{}:{}.{}".format("helm-v3", namespace, helm_chart_id),
            "Check ee_id format: <helm-version>:<NS ID>.<helm_chart-id>",
        )
        self.helm_conn._k8sclusterhelm3.install.assert_called_once_with(
            "myk8s_id",
            kdu_model="/helm_sample_charm",
            kdu_instance=helm_chart_id,
            namespace=namespace,
            db_dict=db_dict,
            params=None,
            timeout=None,
        )

    @asynctest.fail_on(active_handles=True)
    async def test_get_ee_ssh_public__key(self):
        ee_id = "osm.helm_sample_charm_0001"
        db_dict = {}
        mock_pub_key = "ssh-rsapubkey"
        self.db.get_one.return_value = {"_admin": {"helm-chart": {"id": "myk8s_id"}}}
        self.helm_conn._get_ssh_key = asynctest.CoroutineMock(return_value=mock_pub_key)
        pub_key = await self.helm_conn.get_ee_ssh_public__key(
            ee_id=ee_id, db_dict=db_dict
        )
        self.assertEqual(pub_key, mock_pub_key)

    @asynctest.fail_on(active_handles=True)
    async def test_execute_primitive(self):
        ee_id = "osm.helm_sample_charm_0001"
        primitive_name = "sleep"
        params = {}
        self.db.get_one.return_value = {"_admin": {"helm-chart": {"id": "myk8s_id"}}}
        self.helm_conn._execute_primitive_internal = asynctest.CoroutineMock(
            return_value=("OK", "test-ok")
        )
        message = await self.helm_conn.exec_primitive(ee_id, primitive_name, params)
        self.assertEqual(message, "test-ok")

    @asynctest.fail_on(active_handles=True)
    async def test_execute_config_primitive(self):
        self.logger.debug("Execute config primitive")
        ee_id = "osm.helm_sample_charm_0001"
        primitive_name = "config"
        params = {"ssh-host-name": "host1"}
        self.db.get_one.return_value = {"_admin": {"helm-chart": {"id": "myk8s_id"}}}
        self.helm_conn._execute_primitive_internal = asynctest.CoroutineMock(
            return_value=("OK", "CONFIG OK")
        )
        message = await self.helm_conn.exec_primitive(ee_id, primitive_name, params)
        self.assertEqual(message, "CONFIG OK")

    @asynctest.fail_on(active_handles=True)
    async def test_delete_execution_environment(self):
        ee_id = "helm-v3:osm.helm_sample_charm_0001"
        self.db.get_one.return_value = {"_admin": {"helm-chart-v3": {"id": "myk8s_id"}}}
        self.helm_conn._k8sclusterhelm3.uninstall = asynctest.CoroutineMock(
            return_value=""
        )
        await self.helm_conn.delete_execution_environment(ee_id)
        self.helm_conn._k8sclusterhelm3.uninstall.assert_called_once_with(
            "myk8s_id", "helm_sample_charm_0001"
        )


if __name__ == "__main__":
    asynctest.main()
