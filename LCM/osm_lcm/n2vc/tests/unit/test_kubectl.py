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

import asynctest
import yaml
import os
from unittest import TestCase, mock
from osm_lcm.n2vc.kubectl import Kubectl, CORE_CLIENT, CUSTOM_OBJECT_CLIENT
from osm_lcm.n2vc.utils import Dict
from kubernetes.client.rest import ApiException
from kubernetes.client import (
    V1ObjectMeta,
    V1Secret,
    V1ServiceAccount,
    V1SecretReference,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    RbacV1Subject,
    V1PolicyRule,
    V1Namespace,
)


class FakeK8sResourceMetadata:
    def __init__(
        self,
        name: str = None,
        namespace: str = None,
        annotations: dict = {},
        labels: dict = {},
    ):
        self._annotations = annotations
        self._name = name or "name"
        self._namespace = namespace or "namespace"
        self._labels = labels or {"juju-app": "squid"}

    @property
    def name(self):
        return self._name

    @property
    def namespace(self):
        return self._namespace

    @property
    def labels(self):
        return self._labels

    @property
    def annotations(self):
        return self._annotations


class FakeK8sStorageClass:
    def __init__(self, metadata=None):
        self._metadata = metadata or FakeK8sResourceMetadata()

    @property
    def metadata(self):
        return self._metadata


class FakeK8sStorageClassesList:
    def __init__(self, items=[]):
        self._items = items

    @property
    def items(self):
        return self._items


class FakeK8sServiceAccountsList:
    def __init__(self, items=[]):
        self._items = items

    @property
    def items(self):
        return self._items


class FakeK8sSecretList:
    def __init__(self, items=[]):
        self._items = items

    @property
    def items(self):
        return self._items


class FakeK8sRoleList:
    def __init__(self, items=[]):
        self._items = items

    @property
    def items(self):
        return self._items


class FakeK8sRoleBindingList:
    def __init__(self, items=[]):
        self._items = items

    @property
    def items(self):
        return self._items


class FakeK8sVersionApiCode:
    def __init__(self, major: str, minor: str):
        self._major = major
        self._minor = minor

    @property
    def major(self):
        return self._major

    @property
    def minor(self):
        return self._minor


fake_list_services = Dict(
    {
        "items": [
            Dict(
                {
                    "metadata": Dict(
                        {
                            "name": "squid",
                            "namespace": "test",
                            "labels": {"juju-app": "squid"},
                        }
                    ),
                    "spec": Dict(
                        {
                            "cluster_ip": "10.152.183.79",
                            "type": "LoadBalancer",
                            "ports": [
                                Dict(
                                    {
                                        "name": None,
                                        "node_port": None,
                                        "port": 30666,
                                        "protocol": "TCP",
                                        "target_port": 30666,
                                    }
                                )
                            ],
                        }
                    ),
                    "status": Dict(
                        {
                            "load_balancer": Dict(
                                {
                                    "ingress": [
                                        Dict({"hostname": None, "ip": "192.168.0.201"})
                                    ]
                                }
                            )
                        }
                    ),
                }
            )
        ]
    }
)


class KubectlTestCase(TestCase):
    def setUp(
        self,
    ):
        pass


class FakeCoreV1Api:
    def list_service_for_all_namespaces(self, **kwargs):
        return fake_list_services


class GetServices(TestCase):
    @mock.patch("osm_lcm.n2vc.kubectl.kconfig.new_client_from_config")
    @mock.patch("osm_lcm.n2vc.kubectl.kclient.CoreV1Api")
    def setUp(self, mock_core, mock_config):
        mock_core.return_value = mock.MagicMock()
        mock_config.return_value = mock.MagicMock()
        self.kubectl = Kubectl()

    @mock.patch("osm_lcm.n2vc.kubectl.kclient.CoreV1Api")
    def test_get_service(self, mock_corev1api):
        mock_corev1api.return_value = FakeCoreV1Api()
        services = self.kubectl.get_services(
            field_selector="metadata.namespace", label_selector="juju-operator=squid"
        )
        keys = ["name", "cluster_ip", "type", "ports", "external_ip"]
        self.assertTrue(k in service for service in services for k in keys)

    def test_get_service_exception(self):
        self.kubectl.clients[
            CORE_CLIENT
        ].list_service_for_all_namespaces.side_effect = ApiException()
        with self.assertRaises(ApiException):
            self.kubectl.get_services()


@mock.patch("osm_lcm.n2vc.kubectl.kclient")
@mock.patch("osm_lcm.n2vc.kubectl.kconfig.new_client_from_config")
class GetConfiguration(KubectlTestCase):
    def setUp(self):
        super(GetConfiguration, self).setUp()

    def test_get_configuration(
        self,
        mock_new_client_from_config,
        mock_kclient,
    ):
        kubectl = Kubectl()
        kubectl.configuration
        mock_new_client_from_config.assert_called_once()
        mock_kclient.CoreV1Api.assert_called_once()
        mock_kclient.RbacAuthorizationV1Api.assert_called_once()
        mock_kclient.StorageV1Api.assert_called_once()
        mock_kclient.CustomObjectsApi.assert_called_once()


@mock.patch("kubernetes.client.StorageV1Api.list_storage_class")
@mock.patch("kubernetes.config.new_client_from_config")
class GetDefaultStorageClass(KubectlTestCase):
    def setUp(self):
        super(GetDefaultStorageClass, self).setUp()

        # Default Storage Class
        self.default_sc_name = "default-sc"
        default_sc_metadata = FakeK8sResourceMetadata(
            name=self.default_sc_name,
            annotations={"storageclass.kubernetes.io/is-default-class": "true"},
        )
        self.default_sc = FakeK8sStorageClass(metadata=default_sc_metadata)

        # Default Storage Class with old annotation
        self.default_sc_old_name = "default-sc-old"
        default_sc_old_metadata = FakeK8sResourceMetadata(
            name=self.default_sc_old_name,
            annotations={"storageclass.beta.kubernetes.io/is-default-class": "true"},
        )
        self.default_sc_old = FakeK8sStorageClass(metadata=default_sc_old_metadata)

        # Storage class - not default
        self.sc_name = "default-sc-old"
        self.sc = FakeK8sStorageClass(
            metadata=FakeK8sResourceMetadata(name=self.sc_name)
        )

    def test_get_default_storage_class_exists_default(
        self,
        mock_new_client_from_config,
        mock_list_storage_class,
    ):
        kubectl = Kubectl()
        items = [self.default_sc]
        mock_list_storage_class.return_value = FakeK8sStorageClassesList(items=items)
        sc_name = kubectl.get_default_storage_class()
        self.assertEqual(sc_name, self.default_sc_name)
        mock_list_storage_class.assert_called_once()

    def test_get_default_storage_class_exists_default_old(
        self,
        mock_new_client_from_config,
        mock_list_storage_class,
    ):
        kubectl = Kubectl()
        items = [self.default_sc_old]
        mock_list_storage_class.return_value = FakeK8sStorageClassesList(items=items)
        sc_name = kubectl.get_default_storage_class()
        self.assertEqual(sc_name, self.default_sc_old_name)
        mock_list_storage_class.assert_called_once()

    def test_get_default_storage_class_none(
        self,
        mock_new_client_from_config,
        mock_list_storage_class,
    ):
        kubectl = Kubectl()
        mock_list_storage_class.return_value = FakeK8sStorageClassesList(items=[])
        sc_name = kubectl.get_default_storage_class()
        self.assertEqual(sc_name, None)
        mock_list_storage_class.assert_called_once()

    def test_get_default_storage_class_exists_not_default(
        self,
        mock_new_client_from_config,
        mock_list_storage_class,
    ):
        kubectl = Kubectl()
        items = [self.sc]
        mock_list_storage_class.return_value = FakeK8sStorageClassesList(items=items)
        sc_name = kubectl.get_default_storage_class()
        self.assertEqual(sc_name, self.sc_name)
        mock_list_storage_class.assert_called_once()

    def test_get_default_storage_class_choose(
        self,
        mock_new_client_from_config,
        mock_list_storage_class,
    ):
        kubectl = Kubectl()
        items = [self.sc, self.default_sc]
        mock_list_storage_class.return_value = FakeK8sStorageClassesList(items=items)
        sc_name = kubectl.get_default_storage_class()
        self.assertEqual(sc_name, self.default_sc_name)
        mock_list_storage_class.assert_called_once()


@mock.patch("kubernetes.client.VersionApi.get_code")
@mock.patch("kubernetes.client.CoreV1Api.list_namespaced_secret")
@mock.patch("kubernetes.client.CoreV1Api.create_namespaced_secret")
@mock.patch("kubernetes.client.CoreV1Api.create_namespaced_service_account")
@mock.patch("kubernetes.client.CoreV1Api.list_namespaced_service_account")
class CreateServiceAccountClass(KubectlTestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(CreateServiceAccountClass, self).setUp()
        self.service_account_name = "Service_account"
        self.labels = {"Key1": "Value1", "Key2": "Value2"}
        self.namespace = "kubernetes"
        self.token_id = "abc12345"
        self.kubectl = Kubectl()

    def assert_create_secret(self, mock_create_secret, secret_name):
        annotations = {"kubernetes.io/service-account.name": self.service_account_name}
        secret_metadata = V1ObjectMeta(
            name=secret_name, namespace=self.namespace, annotations=annotations
        )
        secret_type = "kubernetes.io/service-account-token"
        secret = V1Secret(metadata=secret_metadata, type=secret_type)
        mock_create_secret.assert_called_once_with(self.namespace, secret)

    def assert_create_service_account_v_1_24(
        self, mock_create_service_account, secret_name
    ):
        sevice_account_metadata = V1ObjectMeta(
            name=self.service_account_name, labels=self.labels, namespace=self.namespace
        )
        secrets = [V1SecretReference(name=secret_name, namespace=self.namespace)]
        service_account = V1ServiceAccount(
            metadata=sevice_account_metadata, secrets=secrets
        )
        mock_create_service_account.assert_called_once_with(
            self.namespace, service_account
        )

    def assert_create_service_account_v_1_23(self, mock_create_service_account):
        metadata = V1ObjectMeta(
            name=self.service_account_name, labels=self.labels, namespace=self.namespace
        )
        service_account = V1ServiceAccount(metadata=metadata)
        mock_create_service_account.assert_called_once_with(
            self.namespace, service_account
        )

    @mock.patch("osm_lcm.n2vc.kubectl.uuid.uuid4")
    def test_secret_is_created_when_k8s_1_24(
        self,
        mock_uuid4,
        mock_list_service_account,
        mock_create_service_account,
        mock_create_secret,
        mock_list_secret,
        mock_version,
    ):
        mock_list_service_account.return_value = FakeK8sServiceAccountsList(items=[])
        mock_list_secret.return_value = FakeK8sSecretList(items=[])
        mock_version.return_value = FakeK8sVersionApiCode("1", "24")
        mock_uuid4.return_value = self.token_id
        self.kubectl.create_service_account(
            self.service_account_name, self.labels, self.namespace
        )
        secret_name = "{}-token-{}".format(self.service_account_name, self.token_id[:5])
        self.assert_create_service_account_v_1_24(
            mock_create_service_account, secret_name
        )
        self.assert_create_secret(mock_create_secret, secret_name)

    def test_secret_is_not_created_when_k8s_1_23(
        self,
        mock_list_service_account,
        mock_create_service_account,
        mock_create_secret,
        mock_list_secret,
        mock_version,
    ):
        mock_list_service_account.return_value = FakeK8sServiceAccountsList(items=[])
        mock_version.return_value = FakeK8sVersionApiCode("1", "23+")
        self.kubectl.create_service_account(
            self.service_account_name, self.labels, self.namespace
        )
        self.assert_create_service_account_v_1_23(mock_create_service_account)
        mock_create_secret.assert_not_called()
        mock_list_secret.assert_not_called()

    def test_raise_exception_if_service_account_already_exists(
        self,
        mock_list_service_account,
        mock_create_service_account,
        mock_create_secret,
        mock_list_secret,
        mock_version,
    ):
        mock_list_service_account.return_value = FakeK8sServiceAccountsList(items=[1])
        with self.assertRaises(Exception) as context:
            self.kubectl.create_service_account(
                self.service_account_name, self.labels, self.namespace
            )
        self.assertTrue(
            "Service account with metadata.name={} already exists".format(
                self.service_account_name
            )
            in str(context.exception)
        )
        mock_create_service_account.assert_not_called()
        mock_create_secret.assert_not_called()

    @mock.patch("osm_lcm.n2vc.kubectl.uuid.uuid4")
    def test_raise_exception_if_secret_already_exists(
        self,
        mock_uuid4,
        mock_list_service_account,
        mock_create_service_account,
        mock_create_secret,
        mock_list_secret,
        mock_version,
    ):
        mock_list_service_account.return_value = FakeK8sServiceAccountsList(items=[])
        mock_list_secret.return_value = FakeK8sSecretList(items=[1])
        mock_version.return_value = FakeK8sVersionApiCode("1", "24+")
        mock_uuid4.return_value = self.token_id
        with self.assertRaises(Exception) as context:
            self.kubectl.create_service_account(
                self.service_account_name, self.labels, self.namespace
            )
        self.assertTrue(
            "Secret with metadata.name={}-token-{} already exists".format(
                self.service_account_name, self.token_id[:5]
            )
            in str(context.exception)
        )
        mock_create_service_account.assert_called()
        mock_create_secret.assert_not_called()


@mock.patch("kubernetes.client.CustomObjectsApi.create_namespaced_custom_object")
class CreateCertificateClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(
        self,
        mock_new_client_from_config,
    ):
        super(CreateCertificateClass, self).setUp()
        self.namespace = "osm"
        self.name = "test-cert"
        self.dns_prefix = "*"
        self.secret_name = "test-cert-secret"
        self.usages = ["server auth"]
        self.issuer_name = "ca-issuer"
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def test_certificate_is_created(
        self,
        mock_create_certificate,
    ):
        with open(
            os.path.join(
                os.path.dirname(__file__), "testdata", "test_certificate.yaml"
            ),
            "r",
        ) as test_certificate:
            certificate_body = yaml.safe_load(test_certificate.read())
            print(certificate_body)
        await self.kubectl.create_certificate(
            namespace=self.namespace,
            name=self.name,
            dns_prefix=self.dns_prefix,
            secret_name=self.secret_name,
            usages=self.usages,
            issuer_name=self.issuer_name,
        )
        mock_create_certificate.assert_called_once_with(
            group="cert-manager.io",
            plural="certificates",
            version="v1",
            body=certificate_body,
            namespace=self.namespace,
        )

    @asynctest.fail_on(active_handles=True)
    async def test_no_exception_if_alreadyexists(
        self,
        mock_create_certificate,
    ):
        api_exception = ApiException()
        api_exception.body = '{"reason": "AlreadyExists"}'
        self.kubectl.clients[
            CUSTOM_OBJECT_CLIENT
        ].create_namespaced_custom_object.side_effect = api_exception
        raised = False
        try:
            await self.kubectl.create_certificate(
                namespace=self.namespace,
                name=self.name,
                dns_prefix=self.dns_prefix,
                secret_name=self.secret_name,
                usages=self.usages,
                issuer_name=self.issuer_name,
            )
        except Exception:
            raised = True
        self.assertFalse(raised, "An exception was raised")

    @asynctest.fail_on(active_handles=True)
    async def test_other_exceptions(
        self,
        mock_create_certificate,
    ):
        self.kubectl.clients[
            CUSTOM_OBJECT_CLIENT
        ].create_namespaced_custom_object.side_effect = Exception()
        with self.assertRaises(Exception):
            await self.kubectl.create_certificate(
                namespace=self.namespace,
                name=self.name,
                dns_prefix=self.dns_prefix,
                secret_name=self.secret_name,
                usages=self.usages,
                issuer_name=self.issuer_name,
            )


@mock.patch("kubernetes.client.CustomObjectsApi.delete_namespaced_custom_object")
class DeleteCertificateClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(DeleteCertificateClass, self).setUp()
        self.namespace = "osm"
        self.object_name = "test-cert"
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def test_no_exception_if_notfound(
        self,
        mock_create_certificate,
    ):
        api_exception = ApiException()
        api_exception.body = '{"reason": "NotFound"}'
        self.kubectl.clients[
            CUSTOM_OBJECT_CLIENT
        ].delete_namespaced_custom_object.side_effect = api_exception
        raised = False
        try:
            await self.kubectl.delete_certificate(
                namespace=self.namespace,
                object_name=self.object_name,
            )
        except Exception:
            raised = True
        self.assertFalse(raised, "An exception was raised")

    @asynctest.fail_on(active_handles=True)
    async def test_other_exceptions(
        self,
        mock_create_certificate,
    ):
        self.kubectl.clients[
            CUSTOM_OBJECT_CLIENT
        ].delete_namespaced_custom_object.side_effect = Exception()
        with self.assertRaises(Exception):
            await self.kubectl.delete_certificate(
                namespace=self.namespace,
                object_name=self.object_name,
            )


@mock.patch("kubernetes.client.RbacAuthorizationV1Api.create_namespaced_role")
@mock.patch("kubernetes.client.RbacAuthorizationV1Api.list_namespaced_role")
class CreateRoleClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(CreateRoleClass, self).setUp()
        self.name = "role"
        self.namespace = "osm"
        self.resources = ["*"]
        self.api_groups = ["*"]
        self.verbs = ["*"]
        self.labels = {}
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def assert_create_role(self, mock_create_role):
        metadata = V1ObjectMeta(
            name=self.name, labels=self.labels, namespace=self.namespace
        )
        role = V1Role(
            metadata=metadata,
            rules=[
                V1PolicyRule(
                    api_groups=self.api_groups,
                    resources=self.resources,
                    verbs=self.verbs,
                ),
            ],
        )
        await self.kubectl.create_role(
            namespace=self.namespace,
            api_groups=self.api_groups,
            name=self.name,
            resources=self.resources,
            verbs=self.verbs,
            labels=self.labels,
        )
        mock_create_role.assert_called_once_with(self.namespace, role)

    @asynctest.fail_on(active_handles=True)
    async def test_raise_exception_if_role_already_exists(
        self,
        mock_list_role,
        mock_create_role,
    ):
        mock_list_role.return_value = FakeK8sRoleList(items=[1])
        with self.assertRaises(Exception) as context:
            await self.kubectl.create_role(
                self.name,
                self.labels,
                self.api_groups,
                self.resources,
                self.verbs,
                self.namespace,
            )
        self.assertTrue(
            "Role with metadata.name={} already exists".format(self.name)
            in str(context.exception)
        )
        mock_create_role.assert_not_called()


@mock.patch("kubernetes.client.RbacAuthorizationV1Api.create_namespaced_role_binding")
@mock.patch("kubernetes.client.RbacAuthorizationV1Api.list_namespaced_role_binding")
class CreateRoleBindingClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(CreateRoleBindingClass, self).setUp()
        self.name = "rolebinding"
        self.namespace = "osm"
        self.role_name = "role"
        self.sa_name = "Default"
        self.labels = {}
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def assert_create_role_binding(self, mock_create_role_binding):
        role_binding = V1RoleBinding(
            metadata=V1ObjectMeta(name=self.name, labels=self.labels),
            role_ref=V1RoleRef(kind="Role", name=self.role_name, api_group=""),
            subjects=[
                RbacV1Subject(
                    kind="ServiceAccount",
                    name=self.sa_name,
                    namespace=self.namespace,
                )
            ],
        )
        await self.kubectl.create_role_binding(
            namespace=self.namespace,
            role_name=self.role_name,
            name=self.name,
            sa_name=self.sa_name,
            labels=self.labels,
        )
        mock_create_role_binding.assert_called_once_with(self.namespace, role_binding)

    @asynctest.fail_on(active_handles=True)
    async def test_raise_exception_if_role_binding_already_exists(
        self,
        mock_list_role_binding,
        mock_create_role_binding,
    ):
        mock_list_role_binding.return_value = FakeK8sRoleBindingList(items=[1])
        with self.assertRaises(Exception) as context:
            await self.kubectl.create_role_binding(
                self.name,
                self.role_name,
                self.sa_name,
                self.labels,
                self.namespace,
            )
        self.assertTrue(
            "Role Binding with metadata.name={} already exists".format(self.name)
            in str(context.exception)
        )
        mock_create_role_binding.assert_not_called()


@mock.patch("kubernetes.client.CoreV1Api.create_namespaced_secret")
class CreateSecretClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(CreateSecretClass, self).setUp()
        self.name = "secret"
        self.namespace = "osm"
        self.data = {"test": "1234"}
        self.secret_type = "Opaque"
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def assert_create_secret(self, mock_create_secret):
        secret_metadata = V1ObjectMeta(name=self.name, namespace=self.namespace)
        secret = V1Secret(
            metadata=secret_metadata,
            data=self.data,
            type=self.secret_type,
        )
        await self.kubectl.create_secret(
            namespace=self.namespace,
            data=self.data,
            name=self.name,
            secret_type=self.secret_type,
        )
        mock_create_secret.assert_called_once_with(self.namespace, secret)


@mock.patch("kubernetes.client.CoreV1Api.create_namespace")
class CreateNamespaceClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(CreateNamespaceClass, self).setUp()
        self.namespace = "osm"
        self.labels = {"key": "value"}
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def test_namespace_is_created(
        self,
        mock_create_namespace,
    ):
        metadata = V1ObjectMeta(name=self.namespace, labels=self.labels)
        namespace = V1Namespace(
            metadata=metadata,
        )
        await self.kubectl.create_namespace(
            name=self.namespace,
            labels=self.labels,
        )
        mock_create_namespace.assert_called_once_with(namespace)

    async def test_namespace_is_created_default_labels(
        self,
        mock_create_namespace,
    ):
        metadata = V1ObjectMeta(name=self.namespace, labels=None)
        namespace = V1Namespace(
            metadata=metadata,
        )
        await self.kubectl.create_namespace(
            name=self.namespace,
        )
        mock_create_namespace.assert_called_once_with(namespace)

    @asynctest.fail_on(active_handles=True)
    async def test_no_exception_if_alreadyexists(
        self,
        mock_create_namespace,
    ):
        api_exception = ApiException()
        api_exception.body = '{"reason": "AlreadyExists"}'
        self.kubectl.clients[CORE_CLIENT].create_namespace.side_effect = api_exception
        raised = False
        try:
            await self.kubectl.create_namespace(
                name=self.namespace,
            )
        except Exception:
            raised = True
        self.assertFalse(raised, "An exception was raised")

    @asynctest.fail_on(active_handles=True)
    async def test_other_exceptions(
        self,
        mock_create_namespace,
    ):
        self.kubectl.clients[CORE_CLIENT].create_namespace.side_effect = Exception()
        with self.assertRaises(Exception):
            await self.kubectl.create_namespace(
                name=self.namespace,
            )


@mock.patch("kubernetes.client.CoreV1Api.delete_namespace")
class DeleteNamespaceClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(DeleteNamespaceClass, self).setUp()
        self.namespace = "osm"
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def test_no_exception_if_notfound(
        self,
        mock_delete_namespace,
    ):
        api_exception = ApiException()
        api_exception.body = '{"reason": "NotFound"}'
        self.kubectl.clients[CORE_CLIENT].delete_namespace.side_effect = api_exception
        raised = False
        try:
            await self.kubectl.delete_namespace(
                name=self.namespace,
            )
        except Exception:
            raised = True
        self.assertFalse(raised, "An exception was raised")

    @asynctest.fail_on(active_handles=True)
    async def test_other_exceptions(
        self,
        mock_delete_namespace,
    ):
        self.kubectl.clients[CORE_CLIENT].delete_namespace.side_effect = Exception()
        with self.assertRaises(Exception):
            await self.kubectl.delete_namespace(
                name=self.namespace,
            )


@mock.patch("kubernetes.client.CoreV1Api.read_namespaced_secret")
class GetSecretContentClass(asynctest.TestCase):
    @mock.patch("kubernetes.config.new_client_from_config")
    def setUp(self, mock_new_client_from_config):
        super(GetSecretContentClass, self).setUp()
        self.name = "my_secret"
        self.namespace = "osm"
        self.data = {"my_key": "my_value"}
        self.type = "Opaque"
        self.kubectl = Kubectl()

    @asynctest.fail_on(active_handles=True)
    async def test_return_type_is_dict(
        self,
        mock_read_namespaced_secret,
    ):
        metadata = V1ObjectMeta(name=self.name, namespace=self.namespace)
        secret = V1Secret(metadata=metadata, data=self.data, type=self.type)
        mock_read_namespaced_secret.return_value = secret
        content = await self.kubectl.get_secret_content(self.name, self.namespace)
        assert type(content) is dict
