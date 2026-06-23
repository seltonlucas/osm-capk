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

from asynctest.mock import Mock, patch
from osm_common.dbmemory import DbMemory
from osm_common.fslocal import FsLocal
from osm_lcm.n2vc.k8s_helm3_conn import K8sHelm3Connector, K8sException

__author__ = "Isabel Lloret <illoret@indra.es>"


class TestK8sHelm3Conn(asynctest.TestCase):
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    @patch("osm_lcm.n2vc.k8s_helm_base_conn.EnvironConfig")
    async def setUp(self, mock_env):
        mock_env.return_value = {"stablerepourl": "https://charts.helm.sh/stable"}
        self.db = Mock(DbMemory())
        self.fs = asynctest.Mock(FsLocal())
        self.fs.path = "./tmp/"
        self.namespace = "testk8s"
        self.cluster_id = "helm3_cluster_id"
        self.cluster_uuid = self.cluster_id
        # pass fake kubectl and helm commands to make sure it does not call actual commands
        K8sHelm3Connector._check_file_exists = asynctest.Mock(return_value=True)
        cluster_dir = self.fs.path + self.cluster_id
        self.env = {
            "HELM_CACHE_HOME": "{}/.cache/helm".format(cluster_dir),
            "HELM_CONFIG_HOME": "{}/.config/helm".format(cluster_dir),
            "HELM_DATA_HOME": "{}/.local/share/helm".format(cluster_dir),
            "KUBECONFIG": "{}/.kube/config".format(cluster_dir),
        }
        self.helm_conn = K8sHelm3Connector(self.fs, self.db, log=self.logger)
        self.logger.debug("Set up executed")

    @asynctest.fail_on(active_handles=True)
    async def test_init_env(self):
        k8s_creds = "false_credentials_string"
        self.helm_conn._get_namespaces = asynctest.CoroutineMock(return_value=[])
        self.helm_conn._create_namespace = asynctest.CoroutineMock()
        self.helm_conn.repo_list = asynctest.CoroutineMock(return_value=[])
        self.helm_conn.repo_add = asynctest.CoroutineMock()

        k8scluster_uuid, installed = await self.helm_conn.init_env(
            k8s_creds, namespace=self.namespace, reuse_cluster_uuid=self.cluster_id
        )

        self.assertEqual(
            k8scluster_uuid,
            self.cluster_id,
            "Check cluster_uuid",
        )
        self.helm_conn._get_namespaces.assert_called_once_with(self.cluster_id)
        self.helm_conn._create_namespace.assert_called_once_with(
            self.cluster_id, self.namespace
        )
        self.helm_conn.repo_list.assert_called_once_with(k8scluster_uuid)
        self.helm_conn.repo_add.assert_called_once_with(
            k8scluster_uuid, "stable", "https://charts.helm.sh/stable"
        )
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        self.logger.debug(f"cluster_uuid: {k8scluster_uuid}")

    @asynctest.fail_on(active_handles=True)
    async def test_repo_add(self):
        repo_name = "bitnami"
        repo_url = "https://charts.bitnami.com/bitnami"
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=(0, ""))

        await self.helm_conn.repo_add(self.cluster_uuid, repo_name, repo_url)

        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        self.assertEqual(
            self.helm_conn._local_async_exec.call_count,
            2,
            "local_async_exec expected 2 calls, called {}".format(
                self.helm_conn._local_async_exec.call_count
            ),
        )

        repo_update_command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 repo update {}"
        ).format(repo_name)
        repo_add_command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 repo add {} {}"
        ).format(repo_name, repo_url)
        calls = self.helm_conn._local_async_exec.call_args_list
        call0_kargs = calls[0][1]
        self.assertEqual(
            call0_kargs.get("command"),
            repo_add_command,
            "Invalid repo add command: {}".format(call0_kargs.get("command")),
        )
        self.assertEqual(
            call0_kargs.get("env"),
            self.env,
            "Invalid env for add command: {}".format(call0_kargs.get("env")),
        )
        call1_kargs = calls[1][1]
        self.assertEqual(
            call1_kargs.get("command"),
            repo_update_command,
            "Invalid repo update command: {}".format(call1_kargs.get("command")),
        )
        self.assertEqual(
            call1_kargs.get("env"),
            self.env,
            "Invalid env for update command: {}".format(call1_kargs.get("env")),
        )

    @asynctest.fail_on(active_handles=True)
    async def test_repo_list(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        await self.helm_conn.repo_list(self.cluster_uuid)

        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        command = "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 repo list --output yaml"
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

    @asynctest.fail_on(active_handles=True)
    async def test_repo_remove(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        repo_name = "bitnami"
        await self.helm_conn.repo_remove(self.cluster_uuid, repo_name)

        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        command = "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 repo remove {}".format(
            repo_name
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=True
        )

    @asynctest.fail_on(active_handles=True)
    async def test_install(self):
        kdu_model = "stable/openldap:1.2.2"
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._status_kdu = asynctest.CoroutineMock(return_value=None)
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn._repo_to_oci_url = Mock(return_value=None)
        self.kdu_instance = "stable-openldap-0005399828"
        self.helm_conn.generate_kdu_instance_name = Mock(return_value=self.kdu_instance)
        self.helm_conn._get_namespaces = asynctest.CoroutineMock(return_value=[])
        self.helm_conn._namespace_exists = asynctest.CoroutineMock(
            side_effect=self.helm_conn._namespace_exists
        )
        self.helm_conn._create_namespace = asynctest.CoroutineMock()

        await self.helm_conn.install(
            self.cluster_uuid,
            kdu_model,
            self.kdu_instance,
            atomic=True,
            namespace=self.namespace,
            db_dict=db_dict,
        )

        self.helm_conn._namespace_exists.assert_called_once()
        self.helm_conn._get_namespaces.assert_called_once()
        self.helm_conn._create_namespace.assert_called_once_with(
            self.cluster_id, self.namespace
        )
        self.helm_conn.fs.sync.assert_has_calls(
            [
                asynctest.call(from_path=self.cluster_id),
                asynctest.call(from_path=self.cluster_id),
            ]
        )
        self.helm_conn.fs.reverse_sync.assert_has_calls(
            [
                asynctest.call(from_path=self.cluster_id),
                asynctest.call(from_path=self.cluster_id),
            ]
        )
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="install",
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 "
            "install stable-openldap-0005399828 --atomic --output yaml   "
            "--timeout 300s --namespace testk8s   stable/openldap --version 1.2.2"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

        # Exception test if namespace could not being created for some reason
        self.helm_conn._namespace_exists.return_value = False
        self.helm_conn._create_namespace.side_effect = Exception()

        with self.assertRaises(K8sException):
            await self.helm_conn.install(
                self.cluster_uuid,
                kdu_model,
                self.kdu_instance,
                atomic=True,
                namespace=self.namespace,
                db_dict=db_dict,
            )

    @asynctest.fail_on(active_handles=True)
    async def test_namespace_exists(self):
        self.helm_conn._get_namespaces = asynctest.CoroutineMock()

        self.helm_conn._get_namespaces.return_value = ["testk8s", "kube-system"]
        result = await self.helm_conn._namespace_exists(self.cluster_id, self.namespace)
        self.helm_conn._get_namespaces.assert_called_once()
        self.assertEqual(result, True)

        self.helm_conn._get_namespaces.reset_mock()
        result = await self.helm_conn._namespace_exists(
            self.cluster_id, "none-exists-namespace"
        )
        self.helm_conn._get_namespaces.assert_called_once()
        self.assertEqual(result, False)

    @asynctest.fail_on(active_handles=True)
    async def test_upgrade(self):
        kdu_model = "stable/openldap:1.2.3"
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        instance_info = {
            "chart": "openldap-1.2.2",
            "name": kdu_instance,
            "namespace": self.namespace,
            "revision": 1,
            "status": "DEPLOYED",
        }
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn._repo_to_oci_url = Mock(return_value=None)
        self.helm_conn.get_instance_info = asynctest.CoroutineMock(
            return_value=instance_info
        )
        # TEST-1 (--force true)
        await self.helm_conn.upgrade(
            self.cluster_uuid,
            kdu_instance,
            kdu_model,
            atomic=True,
            db_dict=db_dict,
            force=True,
        )
        self.helm_conn.fs.sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_has_calls(
            [
                asynctest.call(from_path=self.cluster_id),
                asynctest.call(from_path=self.cluster_id),
            ]
        )
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="upgrade",
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config "
            "/usr/bin/helm3 upgrade stable-openldap-0005399828 stable/openldap "
            "--namespace testk8s --atomic --force --output yaml  --timeout 300s   "
            "--reuse-values --version 1.2.3"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

        # TEST-2 (--force false)
        await self.helm_conn.upgrade(
            self.cluster_uuid,
            kdu_instance,
            kdu_model,
            atomic=True,
            db_dict=db_dict,
        )
        self.helm_conn.fs.sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_has_calls(
            [
                asynctest.call(from_path=self.cluster_id),
                asynctest.call(from_path=self.cluster_id),
            ]
        )
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="upgrade",
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config "
            "/usr/bin/helm3 upgrade stable-openldap-0005399828 stable/openldap "
            "--namespace testk8s --atomic --output yaml  --timeout 300s   "
            "--reuse-values --version 1.2.3"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

    @asynctest.fail_on(active_handles=True)
    async def test_upgrade_namespace(self):
        kdu_model = "stable/openldap:1.2.3"
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        instance_info = {
            "chart": "openldap-1.2.2",
            "name": kdu_instance,
            "namespace": self.namespace,
            "revision": 1,
            "status": "DEPLOYED",
        }
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn._repo_to_oci_url = Mock(return_value=None)
        self.helm_conn.get_instance_info = asynctest.CoroutineMock(
            return_value=instance_info
        )

        await self.helm_conn.upgrade(
            self.cluster_uuid,
            kdu_instance,
            kdu_model,
            atomic=True,
            db_dict=db_dict,
            namespace="default",
        )
        self.helm_conn.fs.sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_has_calls(
            [
                asynctest.call(from_path=self.cluster_id),
                asynctest.call(from_path=self.cluster_id),
            ]
        )
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace="default",
            db_dict=db_dict,
            operation="upgrade",
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config "
            "/usr/bin/helm3 upgrade stable-openldap-0005399828 stable/openldap "
            "--namespace default --atomic --output yaml  --timeout 300s   "
            "--reuse-values --version 1.2.3"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

    @asynctest.fail_on(active_handles=True)
    async def test_scale(self):
        kdu_model = "stable/openldap:1.2.3"
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        instance_info = {
            "chart": "openldap-1.2.3",
            "name": kdu_instance,
            "namespace": self.namespace,
            "revision": 1,
            "status": "DEPLOYED",
        }
        repo_list = [
            {
                "name": "stable",
                "url": "https://kubernetes-charts.storage.googleapis.com/",
            }
        ]
        kdu_values = """
            # Default values for openldap.
            # This is a YAML-formatted file.
            # Declare variables to be passed into your templates.

            replicaCount: 1
            dummy-app:
              replicas: 2
        """

        self.helm_conn.repo_list = asynctest.CoroutineMock(return_value=repo_list)
        self.helm_conn.values_kdu = asynctest.CoroutineMock(return_value=kdu_values)
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn._repo_to_oci_url = Mock(return_value=None)
        self.helm_conn.get_instance_info = asynctest.CoroutineMock(
            return_value=instance_info
        )

        # TEST-1
        await self.helm_conn.scale(
            kdu_instance,
            2,
            "",
            kdu_model=kdu_model,
            cluster_uuid=self.cluster_uuid,
            atomic=True,
            db_dict=db_dict,
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config "
            "/usr/bin/helm3 upgrade stable-openldap-0005399828 stable/openldap "
            "--namespace testk8s --atomic --output yaml --set replicaCount=2 --timeout 1800s   "
            "--reuse-values --version 1.2.3"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )
        # TEST-2
        await self.helm_conn.scale(
            kdu_instance,
            3,
            "dummy-app",
            kdu_model=kdu_model,
            cluster_uuid=self.cluster_uuid,
            atomic=True,
            db_dict=db_dict,
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config "
            "/usr/bin/helm3 upgrade stable-openldap-0005399828 stable/openldap "
            "--namespace testk8s --atomic --output yaml --set dummy-app.replicas=3 --timeout 1800s   "
            "--reuse-values --version 1.2.3"
        )
        self.helm_conn._local_async_exec.assert_called_with(
            command=command, env=self.env, raise_exception_on_error=False
        )
        self.helm_conn.fs.reverse_sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="scale",
        )

    @asynctest.fail_on(active_handles=True)
    async def test_rollback(self):
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        instance_info = {
            "chart": "openldap-1.2.3",
            "name": kdu_instance,
            "namespace": self.namespace,
            "revision": 2,
            "status": "DEPLOYED",
        }
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn.get_instance_info = asynctest.CoroutineMock(
            return_value=instance_info
        )

        await self.helm_conn.rollback(
            self.cluster_uuid, kdu_instance=kdu_instance, revision=1, db_dict=db_dict
        )
        self.helm_conn.fs.sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        self.helm_conn._store_status.assert_called_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="rollback",
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 "
            "rollback stable-openldap-0005399828 1 --namespace=testk8s --wait"
        )
        self.helm_conn._local_async_exec.assert_called_once_with(
            command=command, env=self.env, raise_exception_on_error=False
        )

    @asynctest.fail_on(active_handles=True)
    async def test_uninstall(self):
        kdu_instance = "stable-openldap-0005399828"
        instance_info = {
            "chart": "openldap-1.2.2",
            "name": kdu_instance,
            "namespace": self.namespace,
            "revision": 3,
            "status": "DEPLOYED",
        }
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        self.helm_conn._store_status = asynctest.CoroutineMock()
        self.helm_conn.get_instance_info = asynctest.CoroutineMock(
            return_value=instance_info
        )

        await self.helm_conn.uninstall(self.cluster_uuid, kdu_instance)
        self.helm_conn.fs.sync.assert_called_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 uninstall {} --namespace={}"
        ).format(kdu_instance, self.namespace)
        self.helm_conn._local_async_exec.assert_called_once_with(
            command=command, env=self.env, raise_exception_on_error=True
        )

    @asynctest.fail_on(active_handles=True)
    async def test_get_services(self):
        kdu_instance = "test_services_1"
        service = {"name": "testservice", "type": "LoadBalancer"}
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=(0, ""))
        self.helm_conn._parse_services = Mock(return_value=["testservice"])
        self.helm_conn._get_service = asynctest.CoroutineMock(return_value=service)

        services = await self.helm_conn.get_services(
            self.cluster_uuid, kdu_instance, self.namespace
        )
        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        self.helm_conn._parse_services.assert_called_once()
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 get manifest {} --namespace=testk8s"
        ).format(kdu_instance)
        self.helm_conn._local_async_exec.assert_called_once_with(
            command, env=self.env, raise_exception_on_error=True
        )
        self.assertEqual(
            services, [service], "Invalid service returned from get_service"
        )

    @asynctest.fail_on(active_handles=True)
    async def test_get_service(self):
        service_name = "service1"

        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))
        await self.helm_conn.get_service(
            self.cluster_uuid, service_name, self.namespace
        )

        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        command = (
            "/usr/bin/kubectl --kubeconfig=./tmp/helm3_cluster_id/.kube/config "
            "--namespace=testk8s get service service1 -o=yaml"
        )
        self.helm_conn._local_async_exec.assert_called_once_with(
            command=command, env=self.env, raise_exception_on_error=True
        )

    @asynctest.fail_on(active_handles=True)
    async def test_inspect_kdu(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        kdu_model = "stable/openldap:1.2.4"
        repo_url = "https://kubernetes-charts.storage.googleapis.com/"
        await self.helm_conn.inspect_kdu(kdu_model, repo_url)

        command = (
            "/usr/bin/helm3 show all openldap --repo "
            "https://kubernetes-charts.storage.googleapis.com/ "
            "--version 1.2.4"
        )
        self.helm_conn._local_async_exec.assert_called_with(command=command)

    @asynctest.fail_on(active_handles=True)
    async def test_help_kdu(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        kdu_model = "stable/openldap:1.2.4"
        repo_url = "https://kubernetes-charts.storage.googleapis.com/"
        await self.helm_conn.help_kdu(kdu_model, repo_url)

        command = (
            "/usr/bin/helm3 show readme openldap --repo "
            "https://kubernetes-charts.storage.googleapis.com/ "
            "--version 1.2.4"
        )
        self.helm_conn._local_async_exec.assert_called_with(command=command)

    @asynctest.fail_on(active_handles=True)
    async def test_values_kdu(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        kdu_model = "stable/openldap:1.2.4"
        repo_url = "https://kubernetes-charts.storage.googleapis.com/"
        await self.helm_conn.values_kdu(kdu_model, repo_url)

        command = (
            "/usr/bin/helm3 show values openldap --repo "
            "https://kubernetes-charts.storage.googleapis.com/ "
            "--version 1.2.4"
        )
        self.helm_conn._local_async_exec.assert_called_with(command=command)

    @asynctest.fail_on(active_handles=True)
    async def test_get_values_kdu(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        kdu_instance = "stable-openldap-0005399828"
        await self.helm_conn.get_values_kdu(
            kdu_instance, self.namespace, self.env["KUBECONFIG"]
        )

        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 get values "
            "stable-openldap-0005399828 --namespace=testk8s --output yaml"
        )
        self.helm_conn._local_async_exec.assert_called_with(command=command)

    @asynctest.fail_on(active_handles=True)
    async def test_instances_list(self):
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        await self.helm_conn.instances_list(self.cluster_uuid)
        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.reverse_sync.assert_called_once_with(
            from_path=self.cluster_id
        )
        command = "/usr/bin/helm3 list --all-namespaces  --output yaml"
        self.helm_conn._local_async_exec.assert_called_once_with(
            command=command, env=self.env, raise_exception_on_error=True
        )

    @asynctest.fail_on(active_handles=True)
    async def test_status_kdu(self):
        kdu_instance = "stable-openldap-0005399828"
        self.helm_conn._local_async_exec = asynctest.CoroutineMock(return_value=("", 0))

        await self.helm_conn._status_kdu(
            self.cluster_id, kdu_instance, self.namespace, yaml_format=True
        )
        command = (
            "env KUBECONFIG=./tmp/helm3_cluster_id/.kube/config /usr/bin/helm3 status {} --namespace={} --output yaml"
        ).format(kdu_instance, self.namespace)
        self.helm_conn._local_async_exec.assert_called_once_with(
            command=command,
            env=self.env,
            raise_exception_on_error=True,
            show_error_log=False,
        )

    @asynctest.fail_on(active_handles=True)
    async def test_store_status(self):
        kdu_instance = "stable-openldap-0005399828"
        db_dict = {}
        status = {
            "info": {
                "description": "Install complete",
                "status": {
                    "code": "1",
                    "notes": "The openldap helm chart has been installed",
                },
            }
        }
        self.helm_conn._status_kdu = asynctest.CoroutineMock(return_value=status)
        self.helm_conn.write_app_status_to_db = asynctest.CoroutineMock(
            return_value=status
        )

        await self.helm_conn._store_status(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            db_dict=db_dict,
            operation="install",
        )
        self.helm_conn._status_kdu.assert_called_once_with(
            cluster_id=self.cluster_id,
            kdu_instance=kdu_instance,
            namespace=self.namespace,
            yaml_format=False,
        )
        self.helm_conn.write_app_status_to_db.assert_called_once_with(
            db_dict=db_dict,
            status="Install complete",
            detailed_status=str(status),
            operation="install",
        )

    @asynctest.fail_on(active_handles=True)
    async def test_reset_uninstall_false(self):
        self.helm_conn._uninstall_sw = asynctest.CoroutineMock()

        await self.helm_conn.reset(self.cluster_uuid, force=False, uninstall_sw=False)
        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.file_delete.assert_called_once_with(
            self.cluster_id, ignore_non_exist=True
        )
        self.helm_conn._uninstall_sw.assert_not_called()

    @asynctest.fail_on(active_handles=True)
    async def test_reset_uninstall(self):
        kdu_instance = "stable-openldap-0021099429"
        instances = [
            {
                "app_version": "2.4.48",
                "chart": "openldap-1.2.3",
                "name": kdu_instance,
                "namespace": self.namespace,
                "revision": "1",
                "status": "deployed",
                "updated": "2020-10-30 11:11:20.376744191 +0000 UTC",
            }
        ]
        self.helm_conn._get_namespace = Mock(return_value=self.namespace)
        self.helm_conn._uninstall_sw = asynctest.CoroutineMock()
        self.helm_conn.instances_list = asynctest.CoroutineMock(return_value=instances)
        self.helm_conn.uninstall = asynctest.CoroutineMock()

        await self.helm_conn.reset(self.cluster_uuid, force=True, uninstall_sw=True)
        self.helm_conn.fs.sync.assert_called_once_with(from_path=self.cluster_id)
        self.helm_conn.fs.file_delete.assert_called_once_with(
            self.cluster_id, ignore_non_exist=True
        )
        self.helm_conn._get_namespace.assert_called_once_with(
            cluster_uuid=self.cluster_uuid
        )
        self.helm_conn.instances_list.assert_called_once_with(
            cluster_uuid=self.cluster_uuid
        )
        self.helm_conn.uninstall.assert_called_once_with(
            cluster_uuid=self.cluster_uuid, kdu_instance=kdu_instance
        )
        self.helm_conn._uninstall_sw.assert_called_once_with(
            cluster_id=self.cluster_id, namespace=self.namespace
        )

    @asynctest.fail_on(active_handles=True)
    async def test_sync_repos_add(self):
        repo_list = [
            {
                "name": "stable",
                "url": "https://kubernetes-charts.storage.googleapis.com/",
            }
        ]
        self.helm_conn.repo_list = asynctest.CoroutineMock(return_value=repo_list)

        def get_one_result(*args, **kwargs):
            if args[0] == "k8sclusters":
                return {
                    "_admin": {
                        "helm_chart_repos": ["4b5550a9-990d-4d95-8a48-1f4614d6ac9c"]
                    }
                }
            elif args[0] == "k8srepos":
                return {
                    "_id": "4b5550a9-990d-4d95-8a48-1f4614d6ac9c",
                    "type": "helm-chart",
                    "name": "bitnami",
                    "url": "https://charts.bitnami.com/bitnami",
                }

        self.helm_conn.db.get_one = asynctest.Mock()
        self.helm_conn.db.get_one.side_effect = get_one_result

        self.helm_conn.repo_add = asynctest.CoroutineMock()
        self.helm_conn.repo_remove = asynctest.CoroutineMock()

        deleted_repo_list, added_repo_dict = await self.helm_conn.synchronize_repos(
            self.cluster_uuid
        )
        self.helm_conn.repo_remove.assert_not_called()
        self.helm_conn.repo_add.assert_called_once_with(
            self.cluster_uuid,
            "bitnami",
            "https://charts.bitnami.com/bitnami",
            cert=None,
            user=None,
            password=None,
            oci=False,
        )
        self.assertEqual(deleted_repo_list, [], "Deleted repo list should be empty")
        self.assertEqual(
            added_repo_dict,
            {"4b5550a9-990d-4d95-8a48-1f4614d6ac9c": "bitnami"},
            "Repos added should include only one bitnami",
        )

    @asynctest.fail_on(active_handles=True)
    async def test_sync_repos_delete(self):
        repo_list = [
            {
                "name": "stable",
                "url": "https://kubernetes-charts.storage.googleapis.com/",
            },
            {"name": "bitnami", "url": "https://charts.bitnami.com/bitnami"},
        ]
        self.helm_conn.repo_list = asynctest.CoroutineMock(return_value=repo_list)

        def get_one_result(*args, **kwargs):
            if args[0] == "k8sclusters":
                return {"_admin": {"helm_chart_repos": []}}

        self.helm_conn.db.get_one = asynctest.Mock()
        self.helm_conn.db.get_one.side_effect = get_one_result

        self.helm_conn.repo_add = asynctest.CoroutineMock()
        self.helm_conn.repo_remove = asynctest.CoroutineMock()

        deleted_repo_list, added_repo_dict = await self.helm_conn.synchronize_repos(
            self.cluster_uuid
        )
        self.helm_conn.repo_add.assert_not_called()
        self.helm_conn.repo_remove.assert_called_once_with(self.cluster_uuid, "bitnami")
        self.assertEqual(
            deleted_repo_list, ["bitnami"], "Deleted repo list should be bitnami"
        )
        self.assertEqual(added_repo_dict, {}, "No repos should be added")
