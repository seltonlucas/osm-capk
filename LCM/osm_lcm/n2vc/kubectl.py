#######################################################################################
# Copyright 2020 Canonical Ltd.
# Copyright ETSI Contributors and Others.
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
#######################################################################################

import base64
import logging
import typing
import uuid
import json
import yaml
import tarfile
import io
import os
from time import sleep

from distutils.version import LooseVersion

from kubernetes import client as kclient, config as kconfig
from kubernetes.client.api import VersionApi
from kubernetes.client.models import (
    V1ClusterRole,
    V1Role,
    V1ObjectMeta,
    V1PolicyRule,
    V1ServiceAccount,
    V1ClusterRoleBinding,
    V1RoleBinding,
    V1RoleRef,
    RbacV1Subject,
    V1Secret,
    V1SecretReference,
    V1Namespace,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1PersistentVolumeClaimVolumeSource,
    V1ResourceRequirements,
    V1Pod,
    V1PodSpec,
    V1Volume,
    V1VolumeMount,
    V1Container,
    V1ConfigMap,
)
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from osm_lcm.n2vc.libjuju import retry_callback
from retrying_async import retry

SERVICE_ACCOUNT_TOKEN_KEY = "token"
SERVICE_ACCOUNT_ROOT_CA_KEY = "ca.crt"
# clients
CORE_CLIENT = "core_v1"
RBAC_CLIENT = "rbac_v1"
STORAGE_CLIENT = "storage_v1"
CUSTOM_OBJECT_CLIENT = "custom_object"


class Kubectl:
    def __init__(self, config_file=None):
        self.logger = logging.getLogger("lcm.kubectl")
        self._config_file = config_file
        self.logger.info(f"Kubectl cfg file: {config_file}")

        # Create default configuration for API client
        self._configuration = kclient.Configuration()

        # Get proxy_url
        proxy_url = None
        if config_file:
            with open(config_file, "r", encoding="utf-8") as f:
                kubeconfig_yaml = f.read()
            try:
                kubeconfig_dict = yaml.safe_load(kubeconfig_yaml)
            except yaml.YAMLError as e:
                raise e
            proxy_url = (
                kubeconfig_dict.get("clusters", [])[0]
                .get("cluster", {})
                .get("proxy-url")
            )

        # If kubeconfig has proxy configured, use it
        if proxy_url:
            self._configuration.proxy = proxy_url
            self.logger.info(f"Using proxy for kubernetes: {proxy_url}")

        # Create API client
        self._api_client = kconfig.new_client_from_config(
            config_file=config_file,
            client_configuration=self._configuration,
        )
        # self._configuration = self._api_client.configuration.get_default_copy()

        # Carga la config base
        self._clients = {
            CORE_CLIENT: kclient.CoreV1Api(api_client=self._api_client),
            RBAC_CLIENT: kclient.RbacAuthorizationV1Api(api_client=self._api_client),
            STORAGE_CLIENT: kclient.StorageV1Api(api_client=self._api_client),
            CUSTOM_OBJECT_CLIENT: kclient.CustomObjectsApi(api_client=self._api_client),
        }
        self.logger.info(f"Kubectl cfg file: {config_file}")

    @property
    def configuration(self):
        return self._configuration

    @property
    def clients(self):
        return self._clients

    def get_services(
        self,
        field_selector: str = None,
        label_selector: str = None,
    ) -> typing.List[typing.Dict]:
        """
        Get Service list from a namespace

        :param: field_selector:     Kubernetes field selector for the namespace
        :param: label_selector:     Kubernetes label selector for the namespace

        :return: List of the services matching the selectors specified
        """
        kwargs = {}
        if field_selector:
            kwargs["field_selector"] = field_selector
        if label_selector:
            kwargs["label_selector"] = label_selector
        try:
            result = self.clients[CORE_CLIENT].list_service_for_all_namespaces(**kwargs)
            return [
                {
                    "name": i.metadata.name,
                    "cluster_ip": i.spec.cluster_ip,
                    "type": i.spec.type,
                    "ports": (
                        [
                            {
                                "name": p.name,
                                "node_port": p.node_port,
                                "port": p.port,
                                "protocol": p.protocol,
                                "target_port": p.target_port,
                            }
                            for p in i.spec.ports
                        ]
                        if i.spec.ports
                        else []
                    ),
                    "external_ip": [i.ip for i in i.status.load_balancer.ingress]
                    if i.status.load_balancer.ingress
                    else None,
                }
                for i in result.items
            ]
        except ApiException as e:
            self.logger.error("Error calling get services: {}".format(e))
            raise e

    def get_default_storage_class(self) -> str:
        """
        Default storage class

        :return:    Returns the default storage class name, if exists.
                    If not, it returns the first storage class.
                    If there are not storage classes, returns None
        """
        storage_classes = self.clients[STORAGE_CLIENT].list_storage_class()
        selected_sc = None
        default_sc_annotations = {
            "storageclass.kubernetes.io/is-default-class": "true",
            # Older clusters still use the beta annotation.
            "storageclass.beta.kubernetes.io/is-default-class": "true",
        }
        for sc in storage_classes.items:
            if not selected_sc:
                # Select the first storage class in case there is no a default-class
                selected_sc = sc.metadata.name
            annotations = sc.metadata.annotations or {}
            if any(
                k in annotations and annotations[k] == v
                for k, v in default_sc_annotations.items()
            ):
                # Default storage
                selected_sc = sc.metadata.name
                break
        return selected_sc

    def create_cluster_role(
        self,
        name: str,
        labels: typing.Dict[str, str],
        namespace: str = "kube-system",
    ):
        """
        Create a cluster role

        :param: name:       Name of the cluster role
        :param: labels:     Labels for cluster role metadata
        :param: namespace:  Kubernetes namespace for cluster role metadata
                            Default: kube-system
        """
        cluster_roles = self.clients[RBAC_CLIENT].list_cluster_role(
            field_selector="metadata.name={}".format(name)
        )

        if len(cluster_roles.items) > 0:
            raise Exception("Role with metadata.name={} already exists".format(name))

        metadata = V1ObjectMeta(name=name, labels=labels, namespace=namespace)
        # Cluster role
        cluster_role = V1ClusterRole(
            metadata=metadata,
            rules=[
                V1PolicyRule(api_groups=["*"], resources=["*"], verbs=["*"]),
                V1PolicyRule(non_resource_ur_ls=["*"], verbs=["*"]),
            ],
        )

        self.clients[RBAC_CLIENT].create_cluster_role(cluster_role)

    async def create_role(
        self,
        name: str,
        labels: typing.Dict[str, str],
        api_groups: list,
        resources: list,
        verbs: list,
        namespace: str,
    ):
        """
        Create a role with one PolicyRule

        :param: name:       Name of the namespaced Role
        :param: labels:     Labels for namespaced Role metadata
        :param: api_groups: List with api-groups allowed in the policy rule
        :param: resources:  List with resources allowed in the policy rule
        :param: verbs:      List with verbs allowed in the policy rule
        :param: namespace:  Kubernetes namespace for Role metadata

        :return: None
        """

        roles = self.clients[RBAC_CLIENT].list_namespaced_role(
            namespace, field_selector="metadata.name={}".format(name)
        )

        if len(roles.items) > 0:
            raise Exception("Role with metadata.name={} already exists".format(name))

        metadata = V1ObjectMeta(name=name, labels=labels, namespace=namespace)

        role = V1Role(
            metadata=metadata,
            rules=[
                V1PolicyRule(api_groups=api_groups, resources=resources, verbs=verbs),
            ],
        )

        self.clients[RBAC_CLIENT].create_namespaced_role(namespace, role)

    def delete_cluster_role(self, name: str):
        """
        Delete a cluster role

        :param: name:       Name of the cluster role
        """
        self.clients[RBAC_CLIENT].delete_cluster_role(name)

    def _get_kubectl_version(self):
        self.logger.debug("Enter _get_kubectl_version function")
        version = VersionApi(api_client=self._api_client).get_code()
        return "{}.{}".format(version.major, version.minor)

    def _need_to_create_new_secret(self):
        min_k8s_version = "1.24"
        current_k8s_version = self._get_kubectl_version()
        return LooseVersion(min_k8s_version) <= LooseVersion(current_k8s_version)

    def _get_secret_name(self, service_account_name: str):
        random_alphanum = str(uuid.uuid4())[:5]
        return "{}-token-{}".format(service_account_name, random_alphanum)

    def _create_service_account_secret(
        self,
        service_account_name: str,
        namespace: str,
        secret_name: str,
    ):
        """
        Create a secret for the service account. K8s version >= 1.24

        :param: service_account_name: Name of the service account
        :param: namespace:  Kubernetes namespace for service account metadata
        :param: secret_name: Name of the secret
        """
        v1_core = self.clients[CORE_CLIENT]
        secrets = v1_core.list_namespaced_secret(
            namespace, field_selector="metadata.name={}".format(secret_name)
        ).items

        if len(secrets) > 0:
            raise Exception(
                "Secret with metadata.name={} already exists".format(secret_name)
            )

        annotations = {"kubernetes.io/service-account.name": service_account_name}
        metadata = V1ObjectMeta(
            name=secret_name, namespace=namespace, annotations=annotations
        )
        type = "kubernetes.io/service-account-token"
        secret = V1Secret(metadata=metadata, type=type)
        v1_core.create_namespaced_secret(namespace, secret)

    def _get_secret_reference_list(self, namespace: str, secret_name: str):
        """
        Return a secret reference list with one secret.
        K8s version >= 1.24

        :param: namespace:  Kubernetes namespace for service account metadata
        :param: secret_name: Name of the secret
        :rtype: list[V1SecretReference]
        """
        return [V1SecretReference(name=secret_name, namespace=namespace)]

    def create_service_account(
        self,
        name: str,
        labels: typing.Dict[str, str],
        namespace: str = "kube-system",
    ):
        """
        Create a service account

        :param: name:       Name of the service account
        :param: labels:     Labels for service account metadata
        :param: namespace:  Kubernetes namespace for service account metadata
                            Default: kube-system
        """
        v1_core = self.clients[CORE_CLIENT]
        service_accounts = v1_core.list_namespaced_service_account(
            namespace, field_selector="metadata.name={}".format(name)
        )
        if len(service_accounts.items) > 0:
            raise Exception(
                "Service account with metadata.name={} already exists".format(name)
            )

        metadata = V1ObjectMeta(name=name, labels=labels, namespace=namespace)

        if self._need_to_create_new_secret():
            secret_name = self._get_secret_name(name)
            secrets = self._get_secret_reference_list(namespace, secret_name)
            service_account = V1ServiceAccount(metadata=metadata, secrets=secrets)
            v1_core.create_namespaced_service_account(namespace, service_account)
            self._create_service_account_secret(name, namespace, secret_name)
        else:
            service_account = V1ServiceAccount(metadata=metadata)
            v1_core.create_namespaced_service_account(namespace, service_account)

    def delete_secret(self, name: str, namespace: str = "kube-system"):
        """
        Delete a secret

        :param: name:       Name of the secret
        :param: namespace:  Kubernetes namespace
                            Default: kube-system
        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        self.clients[CORE_CLIENT].delete_namespaced_secret(name, namespace)

    def delete_service_account(self, name: str, namespace: str = "kube-system"):
        """
        Delete a service account

        :param: name:       Name of the service account
        :param: namespace:  Kubernetes namespace for service account metadata
                            Default: kube-system
        """
        self.clients[CORE_CLIENT].delete_namespaced_service_account(name, namespace)

    def create_cluster_role_binding(
        self, name: str, labels: typing.Dict[str, str], namespace: str = "kube-system"
    ):
        """
        Create a cluster role binding

        :param: name:       Name of the cluster role
        :param: labels:     Labels for cluster role binding metadata
        :param: namespace:  Kubernetes namespace for cluster role binding metadata
                            Default: kube-system
        """
        role_bindings = self.clients[RBAC_CLIENT].list_cluster_role_binding(
            field_selector="metadata.name={}".format(name)
        )
        if len(role_bindings.items) > 0:
            raise Exception("Generated rbac id already exists")

        role_binding = V1ClusterRoleBinding(
            metadata=V1ObjectMeta(name=name, labels=labels),
            role_ref=V1RoleRef(kind="ClusterRole", name=name, api_group=""),
            subjects=[
                RbacV1Subject(kind="ServiceAccount", name=name, namespace=namespace)
            ],
        )
        self.clients[RBAC_CLIENT].create_cluster_role_binding(role_binding)

    async def create_role_binding(
        self,
        name: str,
        role_name: str,
        sa_name: str,
        labels: typing.Dict[str, str],
        namespace: str,
    ):
        """
        Create a cluster role binding

        :param: name:       Name of the namespaced Role Binding
        :param: role_name:  Name of the namespaced Role to be bound
        :param: sa_name:    Name of the Service Account to be bound
        :param: labels:     Labels for Role Binding metadata
        :param: namespace:  Kubernetes namespace for Role Binding metadata

        :return: None
        """
        role_bindings = self.clients[RBAC_CLIENT].list_namespaced_role_binding(
            namespace, field_selector="metadata.name={}".format(name)
        )
        if len(role_bindings.items) > 0:
            raise Exception(
                "Role Binding with metadata.name={} already exists".format(name)
            )

        role_binding = V1RoleBinding(
            metadata=V1ObjectMeta(name=name, labels=labels),
            role_ref=V1RoleRef(kind="Role", name=role_name, api_group=""),
            subjects=[
                RbacV1Subject(kind="ServiceAccount", name=sa_name, namespace=namespace)
            ],
        )
        self.clients[RBAC_CLIENT].create_namespaced_role_binding(
            namespace, role_binding
        )

    def delete_cluster_role_binding(self, name: str):
        """
        Delete a cluster role binding

        :param: name:       Name of the cluster role binding
        """
        self.clients[RBAC_CLIENT].delete_cluster_role_binding(name)

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed getting the secret from service account"),
        callback=retry_callback,
    )
    async def get_secret_data(
        self, name: str, namespace: str = "kube-system"
    ) -> typing.Tuple[str, str]:
        """
        Get secret data

        :param: name:       Name of the secret data
        :param: namespace:  Name of the namespace where the secret is stored

        :return: Tuple with the token and client certificate
        """
        v1_core = self.clients[CORE_CLIENT]

        secret_name = None

        service_accounts = v1_core.list_namespaced_service_account(
            namespace, field_selector="metadata.name={}".format(name)
        )
        if len(service_accounts.items) == 0:
            raise Exception(
                "Service account not found with metadata.name={}".format(name)
            )
        service_account = service_accounts.items[0]
        if service_account.secrets and len(service_account.secrets) > 0:
            secret_name = service_account.secrets[0].name
        if not secret_name:
            raise Exception(
                "Failed getting the secret from service account {}".format(name)
            )
        # TODO: refactor to use get_secret_content
        secret = v1_core.list_namespaced_secret(
            namespace, field_selector="metadata.name={}".format(secret_name)
        ).items[0]

        token = secret.data[SERVICE_ACCOUNT_TOKEN_KEY]
        client_certificate_data = secret.data[SERVICE_ACCOUNT_ROOT_CA_KEY]

        return (
            base64.b64decode(token).decode("utf-8"),
            base64.b64decode(client_certificate_data).decode("utf-8"),
        )

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed getting data from the secret"),
    )
    async def get_secret_content(
        self,
        name: str,
        namespace: str,
    ) -> typing.Dict:
        """
        Get secret data

        :param: name:       Name of the secret
        :param: namespace:  Name of the namespace where the secret is stored

        :return: Dictionary with secret's data
        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        v1_core = self.clients[CORE_CLIENT]

        secret = v1_core.read_namespaced_secret(name, namespace)

        return secret.data

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the secret"),
    )
    async def create_secret(
        self, name: str, data: dict, namespace: str, secret_type: str
    ):
        """
        Create secret with data

        :param: name:        Name of the secret
        :param: data:        Dict with data content. Values must be already base64 encoded
        :param: namespace:   Name of the namespace where the secret will be stored
        :param: secret_type: Type of the secret, e.g., Opaque, kubernetes.io/service-account-token, kubernetes.io/tls

        :return: None
        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        self.logger.debug("Enter create_secret function")
        v1_core = self.clients[CORE_CLIENT]
        self.logger.debug(f"v1_core: {v1_core}")
        metadata = V1ObjectMeta(name=name, namespace=namespace)
        self.logger.debug(f"metadata: {metadata}")
        secret = V1Secret(metadata=metadata, data=data, type=secret_type)
        self.logger.debug(f"secret: {secret}")
        try:
            v1_core.create_namespaced_secret(namespace, secret)
            self.logger.info("Namespaced secret was created")
        except ApiException as e:
            self.logger.error(f"Failed to create namespaced secret: {e}")
            raise

    async def create_configmap(self, name: str, data: dict, namespace: str):
        """
        Create secret with data

        :param: name:        Name of the configmap
        :param: data:        Dict with data content.
        :param: namespace:   Name of the namespace where the configmap will be stored

        :return: None
        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        self.logger.debug("Enter create_configmap function")
        v1_core = self.clients[CORE_CLIENT]
        self.logger.debug(f"v1_core: {v1_core}")
        config_map = V1ConfigMap(
            metadata=V1ObjectMeta(name=name, namespace=namespace),
            data=data,
        )
        self.logger.debug(f"config_map: {config_map}")
        try:
            v1_core.create_namespaced_config_map(namespace, config_map)
            self.logger.info("Namespaced configmap was created")
        except ApiException as e:
            self.logger.error(f"Failed to create namespaced configmap: {e}")
            raise

    def delete_configmap(self, name: str, namespace: str):
        """
        Delete a configmap

        :param: name:       Name of the configmap
        :param: namespace:  Kubernetes namespace
        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        self.clients[CORE_CLIENT].delete_namespaced_config_map(name, namespace)

    async def create_certificate(
        self,
        namespace: str,
        name: str,
        dns_prefix: str,
        secret_name: str,
        usages: list,
        issuer_name: str,
    ):
        """
        Creates cert-manager certificate object

        :param: namespace:       Name of the namespace where the certificate and secret is stored
        :param: name:            Name of the certificate object
        :param: dns_prefix:      Prefix for the dnsNames. They will be prefixed to the common k8s svc suffixes
        :param: secret_name:     Name of the secret created by cert-manager
        :param: usages:          List of X.509 key usages
        :param: issuer_name:     Name of the cert-manager's Issuer or ClusterIssuer object

        """
        certificate_body = {
            "apiVersion": "cert-manager.io/v1",
            "kind": "Certificate",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "secretName": secret_name,
                "privateKey": {
                    "rotationPolicy": "Always",
                    "algorithm": "ECDSA",
                    "size": 256,
                },
                "duration": "8760h",  # 1 Year
                "renewBefore": "2208h",  # 9 months
                "subject": {"organizations": ["osm"]},
                "commonName": "osm",
                "isCA": False,
                "usages": usages,
                "dnsNames": [
                    "{}.{}".format(dns_prefix, namespace),
                    "{}.{}.svc".format(dns_prefix, namespace),
                    "{}.{}.svc.cluster".format(dns_prefix, namespace),
                    "{}.{}.svc.cluster.local".format(dns_prefix, namespace),
                ],
                "issuerRef": {"name": issuer_name, "kind": "ClusterIssuer"},
            },
        }
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            client.create_namespaced_custom_object(
                group="cert-manager.io",
                plural="certificates",
                version="v1",
                body=certificate_body,
                namespace=namespace,
            )
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "alreadyexists":
                self.logger.warning("Certificate already exists: {}".format(e))
            else:
                raise e

    async def delete_certificate(self, namespace, object_name):
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            client.delete_namespaced_custom_object(
                group="cert-manager.io",
                plural="certificates",
                version="v1",
                name=object_name,
                namespace=namespace,
            )
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "notfound":
                self.logger.warning("Certificate already deleted: {}".format(e))
            else:
                raise e

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the namespace"),
    )
    async def create_namespace(self, name: str, labels: dict = None):
        """
        Create a namespace

        :param: name:       Name of the namespace to be created
        :param: labels:     Dictionary with labels for the new namespace

        """
        v1_core = self.clients[CORE_CLIENT]
        metadata = V1ObjectMeta(name=name, labels=labels)
        namespace = V1Namespace(
            metadata=metadata,
        )

        try:
            v1_core.create_namespace(namespace)
            self.logger.debug("Namespace created: {}".format(name))
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "alreadyexists":
                self.logger.warning("Namespace already exists: {}".format(e))
            else:
                raise e

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed deleting the namespace"),
    )
    async def delete_namespace(self, name: str):
        """
        Delete a namespace

        :param: name:       Name of the namespace to be deleted

        """
        try:
            self.clients[CORE_CLIENT].delete_namespace(name)
        except ApiException as e:
            if e.reason == "Not Found":
                self.logger.warning("Namespace already deleted: {}".format(e))

    def get_secrets(
        self,
        namespace: str,
        field_selector: str = None,
    ) -> typing.List[typing.Dict]:
        """
        Get Secret list from a namespace

        :param: namespace:  Kubernetes namespace
        :param: field_selector:     Kubernetes field selector

        :return: List of the secrets matching the selectors specified
        """
        try:
            v1_core = self.clients[CORE_CLIENT]
            secrets = v1_core.list_namespaced_secret(
                namespace=namespace,
                field_selector=field_selector,
            ).items
            return secrets
        except ApiException as e:
            self.logger.error("Error calling get secrets: {}".format(e))
            raise e

    def create_generic_object(
        self,
        api_group: str,
        api_plural: str,
        api_version: str,
        namespace: str,
        manifest_dict: dict,
    ):
        """
        Creates generic object

        :param: api_group:       API Group
        :param: api_plural:      API Plural
        :param: api_version:     API Version
        :param: namespace:       Namespace
        :param: manifest_dict:   Dictionary with the content of the Kubernetes manifest

        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            if namespace:
                client.create_namespaced_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    body=manifest_dict,
                    namespace=namespace,
                )
            else:
                client.create_cluster_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    body=manifest_dict,
                )
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "alreadyexists":
                self.logger.warning("Object already exists: {}".format(e))
            else:
                raise e

    def delete_generic_object(
        self,
        api_group: str,
        api_plural: str,
        api_version: str,
        namespace: str,
        name: str,
    ):
        """
        Deletes generic object

        :param: api_group:       API Group
        :param: api_plural:      API Plural
        :param: api_version:     API Version
        :param: namespace:       Namespace
        :param: name:            Name of the object

        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            if namespace:
                client.delete_namespaced_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    name=name,
                    namespace=namespace,
                )
            else:
                client.delete_cluster_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    name=name,
                )
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "notfound":
                self.logger.warning("Object already deleted: {}".format(e))
            else:
                raise e

    async def get_generic_object(
        self,
        api_group: str,
        api_plural: str,
        api_version: str,
        namespace: str,
        name: str,
    ):
        """
        Gets generic object

        :param: api_group:       API Group
        :param: api_plural:      API Plural
        :param: api_version:     API Version
        :param: namespace:       Namespace
        :param: name:            Name of the object

        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            if namespace:
                object_dict = client.list_namespaced_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    namespace=namespace,
                    field_selector=f"metadata.name={name}",
                )
            else:
                object_dict = client.list_cluster_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    field_selector=f"metadata.name={name}",
                )
            if len(object_dict.get("items")) == 0:
                return None
            return object_dict.get("items")[0]
        except ApiException as e:
            self.logger.debug(f"Exception: {e}")
            info = json.loads(e.body)
            self.logger.debug(f"Api Exception: {e}. Reason: {info.get('reason')}")
            return None

    async def list_generic_object(
        self,
        api_group: str,
        api_plural: str,
        api_version: str,
        namespace: str,
    ):
        """
        Lists all generic objects of the requested API group

        :param: api_group:       API Group
        :param: api_plural:      API Plural
        :param: api_version:     API Version
        :param: namespace:       Namespace

        """
        self.logger.debug(f"Kubectl cfg file: {self._config_file}")
        client = self.clients[CUSTOM_OBJECT_CLIENT]
        try:
            if namespace:
                object_dict = client.list_namespaced_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                    namespace=namespace,
                )
            else:
                object_dict = client.list_cluster_custom_object(
                    group=api_group,
                    plural=api_plural,
                    version=api_version,
                )
            self.logger.debug(f"Object-list: {object_dict.get('items')}")
            return object_dict.get("items")
        except ApiException as e:
            self.logger.debug(f"Exception: {e}")
            info = json.loads(e.body)
            if info.get("reason").lower() == "notfound":
                self.logger.warning(
                    "Cannot find specified custom objects: {}".format(e)
                )
                return []
            else:
                raise e

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the secret"),
    )
    async def create_secret_string(
        self, name: str, string_data: str, namespace: str, secret_type: str
    ):
        """
        Create secret with data

        :param: name:        Name of the secret
        :param: string_data: String with data content
        :param: namespace:   Name of the namespace where the secret will be stored
        :param: secret_type: Type of the secret, e.g., Opaque, kubernetes.io/service-account-token, kubernetes.io/tls

        :return: None
        """
        v1_core = self.clients[CORE_CLIENT]
        metadata = V1ObjectMeta(name=name, namespace=namespace)
        secret = V1Secret(metadata=metadata, string_data=string_data, type=secret_type)
        v1_core.create_namespaced_secret(namespace, secret)

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the pvc"),
    )
    async def create_pvc(self, name: str, namespace: str):
        """
        Create a namespace

        :param: name:       Name of the pvc to be created
        :param: namespace:  Name of the namespace where the pvc will be stored

        """
        try:
            pvc = V1PersistentVolumeClaim(
                api_version="v1",
                kind="PersistentVolumeClaim",
                metadata=V1ObjectMeta(name=name),
                spec=V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    resources=V1ResourceRequirements(requests={"storage": "100Mi"}),
                ),
            )
            self.clients[CORE_CLIENT].create_namespaced_persistent_volume_claim(
                namespace=namespace, body=pvc
            )
        except ApiException as e:
            info = json.loads(e.body)
            if info.get("reason").lower() == "alreadyexists":
                self.logger.warning("PVC already exists: {}".format(e))
            else:
                raise e

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed deleting the pvc"),
    )
    async def delete_pvc(self, name: str, namespace: str):
        """
        Create a namespace

        :param: name:       Name of the pvc to be deleted
        :param: namespace:  Namespace

        """
        self.clients[CORE_CLIENT].delete_namespaced_persistent_volume_claim(
            name, namespace
        )

    def copy_file_to_pod(
        self, namespace, pod_name, container_name, src_file, dest_path
    ) -> bool:
        try:
            # Create the destination directory in the pod
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                self.logger.debug(f"Creating directory {dest_dir} in pod {pod_name}")
                mkdir_command = ["mkdir", "-p", dest_dir]

                resp = stream(
                    self.clients[CORE_CLIENT].connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=mkdir_command,
                    container=container_name,
                    stdin=False,
                    stderr=True,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )
                resp.close()
                self.logger.debug(f"Directory {dest_dir} created")

            # Create an in-memory tar file containing the source file
            self.logger.debug(
                f"Creating in-memory tar of {src_file} as {dest_path.split('/')[-1]}"
            )
            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
                tar.add(src_file, arcname=dest_path.split("/")[-1])

            tar_buffer.seek(0)
            self.logger.debug(
                f"Tar buffer created, size={tar_buffer.getbuffer().nbytes} bytes"
            )

            # Define the command to extract the tar file in the pod
            exec_command = ["tar", "xvf", "-", "-C", dest_dir]
            self.logger.debug(f"Exec command prepared: {exec_command}")

            # Execute the command
            resp = stream(
                self.clients[CORE_CLIENT].connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                container=container_name,
                stdin=True,
                stderr=True,
                stdout=True,
                tty=False,
                _preload_content=False,
            )
            self.logger.debug(
                f"Started exec stream to pod {pod_name} (ns={namespace}, container={container_name})"
            )

            # Write the tar data to the pod
            data = tar_buffer.read()
            self.logger.debug(f"Writing {len(data)} bytes to pod stdin")
            resp.write_stdin(data)
            self.logger.debug("Data written to pod stdin")
            resp.close()
            self.logger.debug("Exec stream closed")
            return True
        except Exception as e:
            self.logger.error(f"Failed to copy file {src_file} to pod: {e}")
            return False

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the pvc"),
    )
    async def create_pvc_with_content(
        self, name: str, namespace: str, src_files: typing.List, dest_files: typing.List
    ):
        """
        Create a PVC with content

        :param: name:       Name of the pvc to be created
        :param: namespace:  Name of the namespace where the pvc will be stored
        :param: src_files:  List of source files to be copied
        :param: dest_files: List of destination filenames (paired with src_files)
        """
        pod_name = f"copy-pod-{name}"
        self.logger.debug(f"Creating pvc {name}")
        await self.create_pvc(name=name, namespace=namespace)
        self.logger.debug("Sleeping")
        sleep(40)
        self.logger.debug(f"Creating pod {pod_name}")
        await self.create_copy_pod(name=pod_name, namespace=namespace, pvc_name=name)
        self.logger.debug("Sleeping")
        sleep(40)
        self.logger.debug(f"Copying files to pod {pod_name}")
        for src_f, dest_f in zip(src_files, dest_files):
            dest_path = f"/mnt/data/{dest_f}"
            self.logger.debug(f"Copying file {src_f} to {dest_path} in pod {pod_name}")
            result = self.copy_file_to_pod(
                namespace=namespace,
                pod_name=pod_name,
                container_name="copy-container",
                src_file=src_f,
                dest_path=dest_path,
            )
            if result:
                self.logger.debug(
                    f"Successfully copied file {src_f} to {dest_path} in pod {pod_name}"
                )
            else:
                raise Exception(
                    f"Failed copying file {src_f} to {dest_path} in pod {pod_name}"
                )
        self.logger.debug(f"Deleting pod {pod_name}")
        await self.delete_pod(pod_name, namespace)

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed creating the pvc"),
    )
    async def create_copy_pod(self, name: str, namespace: str, pvc_name: str):
        """
        Create a pod to copy content into a PVC

        :param: name:       Name of the pod to be created
        :param: namespace:  Name of the namespace where the pod will be stored
        :param: pvc_name:   Name of the PVC that the pod will mount as a volume

        """
        pod = V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=kclient.V1ObjectMeta(name=name),
            spec=V1PodSpec(
                containers=[
                    V1Container(
                        name="copy-container",
                        image="busybox",  # Imagen ligera para copiar archivos
                        command=["sleep", "3600"],  # Mantén el contenedor en ejecución
                        volume_mounts=[
                            V1VolumeMount(mount_path="/mnt/data", name="my-storage")
                        ],
                    )
                ],
                volumes=[
                    V1Volume(
                        name="my-storage",
                        persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                            claim_name=pvc_name
                        ),
                    )
                ],
            ),
        )
        # Create the pod
        self.clients[CORE_CLIENT].create_namespaced_pod(namespace=namespace, body=pod)

    @retry(
        attempts=10,
        delay=1,
        fallback=Exception("Failed deleting the pod"),
    )
    async def delete_pod(self, name: str, namespace: str):
        """
        Create a namespace

        :param: name:       Name of the pod to be deleted
        :param: namespace:  Namespace

        """
        self.clients[CORE_CLIENT].delete_namespaced_pod(name, namespace)
