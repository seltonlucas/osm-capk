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
import logging
import asynctest
from unittest.mock import Mock
from osm_lcm.n2vc.definitions import Offer, RelationEndpoint
from osm_lcm.n2vc.k8s_juju_conn import K8sJujuConnector, RBAC_LABEL_KEY_NAME
from osm_common import fslocal
from .utils import kubeconfig, FakeModel, FakeFileWrapper, AsyncMock, FakeApplication
from osm_lcm.n2vc.exceptions import MethodNotImplemented, K8sException
from osm_lcm.n2vc.vca.connection_data import ConnectionData


class K8sJujuConnTestCase(asynctest.TestCase):
    @asynctest.mock.patch("osm_lcm.n2vc.k8s_juju_conn.Libjuju")
    @asynctest.mock.patch("osm_lcm.n2vc.k8s_juju_conn.MotorStore")
    @asynctest.mock.patch("osm_lcm.n2vc.k8s_juju_conn.get_connection")
    @asynctest.mock.patch("osm_lcm.n2vc.vca.connection_data.base64_to_cacert")
    def setUp(
        self,
        mock_base64_to_cacert=None,
        mock_get_connection=None,
        mock_store=None,
        mock_libjuju=None,
    ):
        self.loop = asyncio.get_event_loop()
        self.db = Mock()
        mock_base64_to_cacert.return_value = """
    -----BEGIN CERTIFICATE-----
    SOMECERT
    -----END CERTIFICATE-----"""
        mock_libjuju.return_value = Mock()
        mock_store.return_value = AsyncMock()
        mock_vca_connection = Mock()
        mock_get_connection.return_value = mock_vca_connection
        mock_vca_connection.data.return_value = ConnectionData(
            **{
                "endpoints": ["1.2.3.4:17070"],
                "user": "user",
                "secret": "secret",
                "cacert": "cacert",
                "pubkey": "pubkey",
                "lxd-cloud": "cloud",
                "lxd-credentials": "credentials",
                "k8s-cloud": "k8s_cloud",
                "k8s-credentials": "k8s_credentials",
                "model-config": {},
                "api-proxy": "api_proxy",
            }
        )
        logging.disable(logging.CRITICAL)

        self.kdu_name = "kdu_name"
        self.kdu_instance = "{}-{}".format(self.kdu_name, "id")
        self.default_namespace = self.kdu_instance

        self.k8s_juju_conn = K8sJujuConnector(
            fs=fslocal.FsLocal(),
            db=self.db,
            log=None,
            on_update_db=None,
        )
        self.k8s_juju_conn._store.get_vca_id.return_value = None
        self.k8s_juju_conn.libjuju = Mock()
        # Mock Kubectl
        self.kubectl = Mock()
        self.kubectl.get_secret_data = AsyncMock()
        self.kubectl.get_secret_data.return_value = ("token", "cacert")
        self.kubectl.get_services.return_value = [{}]
        self.k8s_juju_conn._get_kubectl = Mock()
        self.k8s_juju_conn._get_kubectl.return_value = self.kubectl
        self.k8s_juju_conn._obtain_namespace_from_db = Mock(
            return_value=self.default_namespace
        )


class InitEnvTest(K8sJujuConnTestCase):
    def setUp(self):
        super(InitEnvTest, self).setUp()
        self.k8s_juju_conn.libjuju.add_k8s = AsyncMock()

    def test_with_cluster_uuid(
        self,
    ):
        reuse_cluster_uuid = "uuid"
        uuid, created = self.loop.run_until_complete(
            self.k8s_juju_conn.init_env(
                k8s_creds=kubeconfig, reuse_cluster_uuid=reuse_cluster_uuid
            )
        )

        self.assertTrue(created)
        self.assertEqual(uuid, reuse_cluster_uuid)
        self.kubectl.get_default_storage_class.assert_called_once()
        self.k8s_juju_conn.libjuju.add_k8s.assert_called_once()

    def test_with_no_cluster_uuid(
        self,
    ):
        uuid, created = self.loop.run_until_complete(
            self.k8s_juju_conn.init_env(k8s_creds=kubeconfig)
        )

        self.assertTrue(created)
        self.assertTrue(isinstance(uuid, str))
        self.kubectl.get_default_storage_class.assert_called_once()
        self.k8s_juju_conn.libjuju.add_k8s.assert_called_once()

    def test_init_env_exception(
        self,
    ):
        self.k8s_juju_conn.libjuju.add_k8s.side_effect = Exception()
        created = None
        uuid = None
        with self.assertRaises(Exception):
            uuid, created = self.loop.run_until_complete(
                self.k8s_juju_conn.init_env(k8s_creds=kubeconfig)
            )
        self.assertIsNone(created)
        self.assertIsNone(uuid)
        self.kubectl.create_cluster_role.assert_called_once()
        self.kubectl.create_service_account.assert_called_once()
        self.kubectl.create_cluster_role_binding.assert_called_once()
        self.kubectl.get_default_storage_class.assert_called_once()
        self.kubectl.delete_cluster_role.assert_called_once()
        self.kubectl.delete_service_account.assert_called_once()
        self.kubectl.delete_cluster_role_binding.assert_called_once()
        self.k8s_juju_conn.libjuju.add_k8s.assert_called_once()


class NotImplementedTest(K8sJujuConnTestCase):
    def setUp(self):
        super(NotImplementedTest, self).setUp()

    def test_repo_add(self):
        with self.assertRaises(MethodNotImplemented):
            self.loop.run_until_complete(self.k8s_juju_conn.repo_add("", ""))

    def test_repo_list(self):
        with self.assertRaises(MethodNotImplemented):
            self.loop.run_until_complete(self.k8s_juju_conn.repo_list())

    def test_repo_remove(self):
        with self.assertRaises(MethodNotImplemented):
            self.loop.run_until_complete(self.k8s_juju_conn.repo_remove(""))

    def test_synchronize_repos(self):
        self.assertIsNone(
            self.loop.run_until_complete(self.k8s_juju_conn.synchronize_repos("", ""))
        )

    def test_upgrade(self):
        with self.assertRaises(MethodNotImplemented):
            self.loop.run_until_complete(self.k8s_juju_conn.upgrade("", ""))

    def test_rollback(self):
        with self.assertRaises(MethodNotImplemented):
            self.loop.run_until_complete(self.k8s_juju_conn.rollback("", ""))

    def test_get_namespace(self):
        self.assertIsNone(self.k8s_juju_conn.get_namespace(""))

    def test_instances_list(self):
        res = self.loop.run_until_complete(self.k8s_juju_conn.instances_list(""))
        self.assertEqual(res, [])


class ResetTest(K8sJujuConnTestCase):
    def setUp(self):
        super(ResetTest, self).setUp()
        self.k8s_juju_conn.libjuju.remove_cloud = AsyncMock()
        self.k8s_juju_conn.libjuju.get_cloud_credentials = AsyncMock()
        cloud_creds = Mock()
        cloud_creds.result = {"attrs": {RBAC_LABEL_KEY_NAME: "asd"}}
        self.k8s_juju_conn.libjuju.get_cloud_credentials.return_value = [cloud_creds]
        self.k8s_juju_conn.get_credentials = Mock()
        self.k8s_juju_conn.get_credentials.return_value = kubeconfig

    def test_success(self):
        removed = self.loop.run_until_complete(self.k8s_juju_conn.reset("uuid"))
        self.assertTrue(removed)
        self.k8s_juju_conn.libjuju.remove_cloud.assert_called_once()

    def test_exception(self):
        removed = None
        self.k8s_juju_conn.libjuju.remove_cloud.side_effect = Exception()
        with self.assertRaises(Exception):
            removed = self.loop.run_until_complete(self.k8s_juju_conn.reset("uuid"))
        self.assertIsNone(removed)
        self.k8s_juju_conn.libjuju.remove_cloud.assert_called_once()


@asynctest.mock.patch("os.chdir")
class InstallTest(K8sJujuConnTestCase):
    def setUp(self):
        super(InstallTest, self).setUp()
        self.db_dict = {"filter": {"_id": "id"}}
        self.local_bundle = "bundle"
        self.cs_bundle = "cs:bundle"
        self.http_bundle = "https://example.com/bundle.yaml"
        self.cluster_uuid = "cluster"
        self.k8s_juju_conn.libjuju.add_model = AsyncMock()
        self.k8s_juju_conn.libjuju.deploy = AsyncMock()

    def test_success_local(self, mock_chdir):
        self.loop.run_until_complete(
            self.k8s_juju_conn.install(
                self.cluster_uuid,
                self.local_bundle,
                self.kdu_instance,
                atomic=True,
                kdu_name=self.kdu_name,
                db_dict=self.db_dict,
                timeout=1800,
                params=None,
            )
        )
        self.assertEqual(mock_chdir.call_count, 2)
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            "local:{}".format(self.local_bundle),
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=None,
        )

    def test_success_cs(self, mock_chdir):
        self.loop.run_until_complete(
            self.k8s_juju_conn.install(
                self.cluster_uuid,
                self.cs_bundle,
                self.kdu_instance,
                atomic=True,
                kdu_name=self.kdu_name,
                db_dict=self.db_dict,
                timeout=1800,
                params={},
            )
        )
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            self.cs_bundle,
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=None,
        )

    def test_success_http(self, mock_chdir):
        params = {"overlay": {"applications": {"squid": {"scale": 2}}}}
        self.loop.run_until_complete(
            self.k8s_juju_conn.install(
                self.cluster_uuid,
                self.http_bundle,
                self.kdu_instance,
                atomic=True,
                kdu_name=self.kdu_name,
                db_dict=self.db_dict,
                timeout=1800,
                params=params,
            )
        )
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            self.http_bundle,
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=params.get("overlay"),
        )

    def test_success_not_kdu_name(self, mock_chdir):
        params = {"some_key": {"applications": {"squid": {"scale": 2}}}}
        self.loop.run_until_complete(
            self.k8s_juju_conn.install(
                self.cluster_uuid,
                self.cs_bundle,
                self.kdu_instance,
                atomic=True,
                db_dict=self.db_dict,
                timeout=1800,
                params=params,
            )
        )
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            self.cs_bundle,
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=None,
        )

    def test_missing_db_dict(self, mock_chdir):
        kdu_instance = None
        with self.assertRaises(K8sException):
            self.loop.run_until_complete(
                self.k8s_juju_conn.install(
                    self.cluster_uuid,
                    self.cs_bundle,
                    self.kdu_instance,
                    atomic=True,
                    kdu_name=self.kdu_name,
                    timeout=1800,
                )
            )
        self.assertIsNone(kdu_instance)
        self.k8s_juju_conn.libjuju.add_model.assert_not_called()
        self.k8s_juju_conn.libjuju.deploy.assert_not_called()

    @asynctest.mock.patch("os.getcwd")
    def test_getcwd_exception(self, mock_getcwd, mock_chdir):
        mock_getcwd.side_effect = FileNotFoundError()
        self.loop.run_until_complete(
            self.k8s_juju_conn.install(
                self.cluster_uuid,
                self.cs_bundle,
                self.kdu_instance,
                atomic=True,
                kdu_name=self.kdu_name,
                db_dict=self.db_dict,
                timeout=1800,
            )
        )
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            self.cs_bundle,
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=None,
        )

    def test_missing_bundle(self, mock_chdir):
        with self.assertRaises(K8sException):
            self.loop.run_until_complete(
                self.k8s_juju_conn.install(
                    self.cluster_uuid,
                    "",
                    self.kdu_instance,
                    atomic=True,
                    kdu_name=self.kdu_name,
                    timeout=1800,
                    db_dict=self.db_dict,
                )
            )
        self.k8s_juju_conn.libjuju.add_model.assert_not_called()
        self.k8s_juju_conn.libjuju.deploy.assert_not_called()

    def test_missing_exception(self, mock_chdir):
        self.k8s_juju_conn.libjuju.deploy.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.k8s_juju_conn.install(
                    self.cluster_uuid,
                    self.local_bundle,
                    self.kdu_instance,
                    atomic=True,
                    kdu_name=self.kdu_name,
                    db_dict=self.db_dict,
                    timeout=1800,
                )
            )
        self.k8s_juju_conn.libjuju.add_model.assert_called_once()
        self.k8s_juju_conn.libjuju.deploy.assert_called_once_with(
            "local:{}".format(self.local_bundle),
            model_name=self.default_namespace,
            wait=True,
            timeout=1800,
            instantiation_params=None,
        )


class UninstallTest(K8sJujuConnTestCase):
    def setUp(self):
        super(UninstallTest, self).setUp()
        self.k8s_juju_conn.libjuju.destroy_model = AsyncMock()

    def test_success(self):
        destroyed = self.loop.run_until_complete(
            self.k8s_juju_conn.uninstall("cluster_uuid", "model_name")
        )
        self.assertTrue(destroyed)
        self.k8s_juju_conn.libjuju.destroy_model.assert_called_once()

    def test_exception(self):
        destroyed = None
        self.k8s_juju_conn.libjuju.destroy_model.side_effect = Exception()
        with self.assertRaises(Exception):
            destroyed = self.loop.run_until_complete(
                self.k8s_juju_conn.uninstall("cluster_uuid", "model_name")
            )
        self.assertIsNone(destroyed)
        self.k8s_juju_conn.libjuju.destroy_model.assert_called_once()


class ExecPrimitivesTest(K8sJujuConnTestCase):
    def setUp(self):
        super(ExecPrimitivesTest, self).setUp()
        self.action_name = "touch"
        self.application_name = "myapp"
        self.k8s_juju_conn.libjuju.get_actions = AsyncMock()
        self.k8s_juju_conn.libjuju.execute_action = AsyncMock()

    def test_success(self):
        params = {"application-name": self.application_name}
        self.k8s_juju_conn.libjuju.get_actions.return_value = [self.action_name]
        self.k8s_juju_conn.libjuju.execute_action.return_value = (
            "success",
            "completed",
        )

        output = self.loop.run_until_complete(
            self.k8s_juju_conn.exec_primitive(
                "cluster", self.kdu_instance, self.action_name, params=params
            )
        )

        self.assertEqual(output, "success")
        self.k8s_juju_conn._obtain_namespace_from_db.assert_called_once_with(
            kdu_instance=self.kdu_instance
        )
        self.k8s_juju_conn.libjuju.get_actions.assert_called_once_with(
            application_name=self.application_name, model_name=self.default_namespace
        )
        self.k8s_juju_conn.libjuju.execute_action.assert_called_once_with(
            application_name=self.application_name,
            model_name=self.default_namespace,
            action_name=self.action_name,
            **params
        )

    def test_exception(self):
        params = {"application-name": self.application_name}
        self.k8s_juju_conn.libjuju.get_actions.return_value = [self.action_name]
        self.k8s_juju_conn.libjuju.execute_action.side_effect = Exception()
        output = None

        with self.assertRaises(Exception):
            output = self.loop.run_until_complete(
                self.k8s_juju_conn.exec_primitive(
                    "cluster", self.kdu_instance, self.action_name, params=params
                )
            )

        self.assertIsNone(output)
        self.k8s_juju_conn._obtain_namespace_from_db.assert_called_once_with(
            kdu_instance=self.kdu_instance
        )
        self.k8s_juju_conn.libjuju.get_actions.assert_called_once_with(
            application_name=self.application_name, model_name=self.default_namespace
        )
        self.k8s_juju_conn.libjuju.execute_action.assert_called_once_with(
            application_name=self.application_name,
            model_name=self.default_namespace,
            action_name=self.action_name,
            **params
        )

    def test_missing_application_name_in_params(self):
        params = {}
        output = None

        with self.assertRaises(K8sException):
            output = self.loop.run_until_complete(
                self.k8s_juju_conn.exec_primitive(
                    "cluster", self.kdu_instance, self.action_name, params=params
                )
            )

        self.assertIsNone(output)
        self.k8s_juju_conn.libjuju.get_actions.assert_not_called()
        self.k8s_juju_conn.libjuju.execute_action.assert_not_called()

    def test_missing_params(self):
        output = None
        with self.assertRaises(K8sException):
            output = self.loop.run_until_complete(
                self.k8s_juju_conn.exec_primitive(
                    "cluster", self.kdu_instance, self.action_name
                )
            )

        self.assertIsNone(output)
        self.k8s_juju_conn.libjuju.get_actions.assert_not_called()
        self.k8s_juju_conn.libjuju.execute_action.assert_not_called()

    def test_missing_action(self):
        output = None
        params = {"application-name": self.application_name}
        self.k8s_juju_conn.libjuju.get_actions.return_value = [self.action_name]
        self.k8s_juju_conn.libjuju.execute_action.return_value = (
            "success",
            "completed",
        )
        with self.assertRaises(K8sException):
            output = self.loop.run_until_complete(
                self.k8s_juju_conn.exec_primitive(
                    "cluster", self.kdu_instance, "non-existing-action", params=params
                )
            )

        self.assertIsNone(output)
        self.k8s_juju_conn._obtain_namespace_from_db.assert_called_once_with(
            kdu_instance=self.kdu_instance
        )
        self.k8s_juju_conn.libjuju.get_actions.assert_called_once_with(
            application_name=self.application_name, model_name=self.default_namespace
        )
        self.k8s_juju_conn.libjuju.execute_action.assert_not_called()

    def test_missing_not_completed(self):
        output = None
        params = {"application-name": self.application_name}
        self.k8s_juju_conn.libjuju.get_actions.return_value = [self.action_name]
        self.k8s_juju_conn.libjuju.execute_action.return_value = (None, "failed")
        with self.assertRaises(K8sException):
            output = self.loop.run_until_complete(
                self.k8s_juju_conn.exec_primitive(
                    "cluster", self.kdu_instance, self.action_name, params=params
                )
            )

        self.assertIsNone(output)
        self.k8s_juju_conn._obtain_namespace_from_db.assert_called_once_with(
            kdu_instance=self.kdu_instance
        )
        self.k8s_juju_conn.libjuju.get_actions.assert_called_once_with(
            application_name=self.application_name, model_name=self.default_namespace
        )
        self.k8s_juju_conn.libjuju.execute_action.assert_called_once_with(
            application_name=self.application_name,
            model_name=self.default_namespace,
            action_name=self.action_name,
            **params
        )


class InspectKduTest(K8sJujuConnTestCase):
    def setUp(self):
        super(InspectKduTest, self).setUp()

    @asynctest.mock.patch("builtins.open")
    @asynctest.mock.patch("os.path.exists")
    def test_existing_file(self, mock_exists, mock_open):
        mock_exists.return_value = True
        content = """{
            'description': 'test bundle',
            'bundle': 'kubernetes',
            'applications': {'app':{ }, 'app2': { }}
        }"""
        mock_open.return_value = FakeFileWrapper(content=content)
        kdu = self.loop.run_until_complete(self.k8s_juju_conn.inspect_kdu("model"))
        self.assertEqual(kdu, {"app": {}, "app2": {}})
        mock_exists.assert_called_once()
        mock_open.assert_called_once()

    @asynctest.mock.patch("builtins.open")
    @asynctest.mock.patch("os.path.exists")
    def test_not_existing_file(self, mock_exists, mock_open):
        kdu = None
        mock_exists.return_value = False
        with self.assertRaises(K8sException):
            kdu = self.loop.run_until_complete(self.k8s_juju_conn.inspect_kdu("model"))
        self.assertEqual(kdu, None)
        mock_exists.assert_called_once_with("model")
        mock_open.assert_not_called()


class HelpKduTest(K8sJujuConnTestCase):
    def setUp(self):
        super(HelpKduTest, self).setUp()

    @asynctest.mock.patch("builtins.open")
    @asynctest.mock.patch("os.listdir")
    def test_existing_file(self, mock_listdir, mock_open):
        content = "Readme file content"
        mock_open.return_value = FakeFileWrapper(content=content)
        for file in ["README.md", "README.txt", "README"]:
            mock_listdir.return_value = [file]
            help = self.loop.run_until_complete(
                self.k8s_juju_conn.help_kdu("kdu_instance")
            )
            self.assertEqual(help, content)

        self.assertEqual(mock_listdir.call_count, 3)
        self.assertEqual(mock_open.call_count, 3)

    @asynctest.mock.patch("builtins.open")
    @asynctest.mock.patch("os.listdir")
    def test_not_existing_file(self, mock_listdir, mock_open):
        for file in ["src/charm.py", "tox.ini", "requirements.txt"]:
            mock_listdir.return_value = [file]
            help = self.loop.run_until_complete(
                self.k8s_juju_conn.help_kdu("kdu_instance")
            )
            self.assertEqual(help, None)

        self.assertEqual(mock_listdir.call_count, 3)
        self.assertEqual(mock_open.call_count, 0)


class StatusKduTest(K8sJujuConnTestCase):
    def setUp(self):
        super(StatusKduTest, self).setUp()
        self.k8s_juju_conn.libjuju.get_model_status = AsyncMock()

    def test_success(self):
        applications = {"app": {"status": {"status": "active"}}}
        model = FakeModel(applications=applications)
        self.k8s_juju_conn.libjuju.get_model_status.return_value = model
        status = self.loop.run_until_complete(
            self.k8s_juju_conn.status_kdu("cluster", "kdu_instance")
        )
        self.assertEqual(status, {"app": {"status": "active"}})
        self.k8s_juju_conn.libjuju.get_model_status.assert_called_once()

    def test_exception(self):
        self.k8s_juju_conn.libjuju.get_model_status.side_effect = Exception()
        status = None
        with self.assertRaises(Exception):
            status = self.loop.run_until_complete(
                self.k8s_juju_conn.status_kdu("cluster", "kdu_instance")
            )
        self.assertIsNone(status)
        self.k8s_juju_conn.libjuju.get_model_status.assert_called_once()


class GetServicesTest(K8sJujuConnTestCase):
    def setUp(self):
        super(GetServicesTest, self).setUp()

    @asynctest.mock.patch("osm_lcm.n2vc.k8s_juju_conn.K8sJujuConnector.get_credentials")
    def test_success(self, mock_get_credentials):
        mock_get_credentials.return_value = kubeconfig
        self.loop.run_until_complete(self.k8s_juju_conn.get_services("", "", ""))
        mock_get_credentials.assert_called_once()
        self.kubectl.get_services.assert_called_once()


class GetServiceTest(K8sJujuConnTestCase):
    def setUp(self):
        super(GetServiceTest, self).setUp()

    @asynctest.mock.patch("osm_lcm.n2vc.k8s_juju_conn.K8sJujuConnector.get_credentials")
    def test_success(self, mock_get_credentials):
        mock_get_credentials.return_value = kubeconfig
        self.loop.run_until_complete(self.k8s_juju_conn.get_service("", "", ""))
        mock_get_credentials.assert_called_once()
        self.kubectl.get_services.assert_called_once()


class GetCredentialsTest(K8sJujuConnTestCase):
    def setUp(self):
        super(GetCredentialsTest, self).setUp()

    @asynctest.mock.patch("yaml.safe_dump")
    def test_success(self, mock_safe_dump):
        self.k8s_juju_conn.db.get_one.return_value = {
            "_id": "id",
            "credentials": "credentials",
            "schema_version": "2",
        }
        self.k8s_juju_conn.get_credentials("cluster_uuid")
        self.k8s_juju_conn.db.get_one.assert_called_once()
        self.k8s_juju_conn.db.encrypt_decrypt_fields.assert_called_once()
        mock_safe_dump.assert_called_once()


class UpdateVcaStatusTest(K8sJujuConnTestCase):
    def setUp(self):
        super(UpdateVcaStatusTest, self).setUp()
        self.vcaStatus = {"model": {"applications": {"app": {"actions": {}}}}}
        self.k8s_juju_conn.libjuju.get_executed_actions = AsyncMock()
        self.k8s_juju_conn.libjuju.get_actions = AsyncMock()
        self.k8s_juju_conn.libjuju.get_application_configs = AsyncMock()

    def test_success(self):
        self.loop.run_until_complete(
            self.k8s_juju_conn.update_vca_status(self.vcaStatus, self.kdu_instance)
        )
        self.k8s_juju_conn.libjuju.get_executed_actions.assert_called_once()
        self.k8s_juju_conn.libjuju.get_application_configs.assert_called_once()

    def test_exception(self):
        self.k8s_juju_conn.libjuju.get_model.return_value = None
        self.k8s_juju_conn.libjuju.get_executed_actions.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.k8s_juju_conn.update_vca_status(self.vcaStatus, self.kdu_instance)
            )
            self.k8s_juju_conn.libjuju.get_executed_actions.assert_not_called()
            self.k8s_juju_conn.libjuju.get_application_configs.assert_not_called_once()


class ScaleTest(K8sJujuConnTestCase):
    def setUp(self):
        super(ScaleTest, self).setUp()
        self.application_name = "app"
        self.kdu_name = "kdu-instance"
        self._scale = 2
        self.k8s_juju_conn.libjuju.scale_application = AsyncMock()

    def test_success(self):
        self.loop.run_until_complete(
            self.k8s_juju_conn.scale(self.kdu_name, self._scale, self.application_name)
        )
        self.k8s_juju_conn.libjuju.scale_application.assert_called_once()

    def test_exception(self):
        self.k8s_juju_conn.libjuju.scale_application.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.k8s_juju_conn.scale(
                    self.kdu_name, self._scale, self.application_name
                )
            )
        self.k8s_juju_conn.libjuju.scale_application.assert_called_once()


class GetScaleCount(K8sJujuConnTestCase):
    def setUp(self):
        super(GetScaleCount, self).setUp()
        self.k8s_juju_conn.libjuju.get_model_status = AsyncMock()

    def test_success(self):
        applications = {"app": FakeApplication()}
        model = FakeModel(applications=applications)
        self.k8s_juju_conn.libjuju.get_model_status.return_value = model
        status = self.loop.run_until_complete(
            self.k8s_juju_conn.get_scale_count("app", "kdu_instance")
        )
        self.assertEqual(status, 2)
        self.k8s_juju_conn.libjuju.get_model_status.assert_called_once()

    def test_exception(self):
        self.k8s_juju_conn.libjuju.get_model_status.side_effect = Exception()
        status = None
        with self.assertRaises(Exception):
            status = self.loop.run_until_complete(
                self.k8s_juju_conn.status_kdu("app", "kdu_instance")
            )
        self.assertIsNone(status)
        self.k8s_juju_conn.libjuju.get_model_status.assert_called_once()


class AddRelationTest(K8sJujuConnTestCase):
    def setUp(self):
        super(AddRelationTest, self).setUp()
        self.k8s_juju_conn.libjuju.add_relation = AsyncMock()
        self.k8s_juju_conn.libjuju.offer = AsyncMock()
        self.k8s_juju_conn.libjuju.get_controller = AsyncMock()
        self.k8s_juju_conn.libjuju.consume = AsyncMock()

    def test_standard_relation_same_model_and_controller(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint1")
        relation_endpoint_2 = RelationEndpoint("model-1.app2.1", None, "endpoint2")
        self.loop.run_until_complete(
            self.k8s_juju_conn.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.k8s_juju_conn.libjuju.add_relation.assert_called_once_with(
            model_name="model-1",
            endpoint_1="app1:endpoint1",
            endpoint_2="app2:endpoint2",
        )
        self.k8s_juju_conn.libjuju.offer.assert_not_called()
        self.k8s_juju_conn.libjuju.consume.assert_not_called()

    def test_cmr_relation_same_controller(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint")
        relation_endpoint_2 = RelationEndpoint("model-2.app2.1", None, "endpoint")
        offer = Offer("admin/model-1.app1")
        self.k8s_juju_conn.libjuju.offer.return_value = offer
        self.k8s_juju_conn.libjuju.consume.return_value = "saas"
        self.loop.run_until_complete(
            self.k8s_juju_conn.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.k8s_juju_conn.libjuju.offer.assert_called_once_with(relation_endpoint_1)
        self.k8s_juju_conn.libjuju.consume.assert_called_once()
        self.k8s_juju_conn.libjuju.add_relation.assert_called_once_with(
            "model-2", "app2:endpoint", "saas"
        )

    def test_cmr_relation_different_controller(self):
        self.k8s_juju_conn._get_libjuju = AsyncMock(
            return_value=self.k8s_juju_conn.libjuju
        )
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", "vca-id-1", "endpoint")
        relation_endpoint_2 = RelationEndpoint("model-1.app2.1", "vca-id-2", "endpoint")
        offer = Offer("admin/model-1.app1")
        self.k8s_juju_conn.libjuju.offer.return_value = offer
        self.k8s_juju_conn.libjuju.consume.return_value = "saas"
        self.loop.run_until_complete(
            self.k8s_juju_conn.add_relation(relation_endpoint_1, relation_endpoint_2)
        )
        self.k8s_juju_conn.libjuju.offer.assert_called_once_with(relation_endpoint_1)
        self.k8s_juju_conn.libjuju.consume.assert_called_once()
        self.k8s_juju_conn.libjuju.add_relation.assert_called_once_with(
            "model-1", "app2:endpoint", "saas"
        )

    def test_relation_exception(self):
        relation_endpoint_1 = RelationEndpoint("model-1.app1.0", None, "endpoint")
        relation_endpoint_2 = RelationEndpoint("model-2.app2.1", None, "endpoint")
        self.k8s_juju_conn.libjuju.offer.side_effect = Exception()
        with self.assertRaises(Exception):
            self.loop.run_until_complete(
                self.k8s_juju_conn.add_relation(
                    relation_endpoint_1, relation_endpoint_2
                )
            )
