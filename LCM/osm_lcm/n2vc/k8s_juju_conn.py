# Copyright 2019 Canonical Ltd.
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
from typing import Union
import os
import uuid
import yaml
import tempfile
import binascii

from osm_lcm.n2vc.config import EnvironConfig
from osm_lcm.n2vc.definitions import RelationEndpoint
from osm_lcm.n2vc.exceptions import K8sException
from osm_lcm.n2vc.k8s_conn import K8sConnector
from osm_lcm.n2vc.kubectl import Kubectl
from .exceptions import MethodNotImplemented
from osm_lcm.n2vc.libjuju import Libjuju
from osm_lcm.n2vc.utils import obj_to_dict, obj_to_yaml
from osm_lcm.n2vc.store import MotorStore
from osm_lcm.n2vc.vca.cloud import Cloud
from osm_lcm.n2vc.vca.connection import get_connection


RBAC_LABEL_KEY_NAME = "rbac-id"
RBAC_STACK_PREFIX = "juju-credential"


def generate_rbac_id():
    return binascii.hexlify(os.urandom(4)).decode()


class K8sJujuConnector(K8sConnector):
    libjuju = None

    def __init__(
        self,
        fs: object,
        db: object,
        kubectl_command: str = "/usr/bin/kubectl",
        juju_command: str = "/usr/bin/juju",
        log: object = None,
        on_update_db=None,
    ):
        """
        :param fs: file system for kubernetes and helm configuration
        :param db: Database object
        :param kubectl_command: path to kubectl executable
        :param helm_command: path to helm executable
        :param log: logger
        """

        # parent class
        K8sConnector.__init__(self, db, log=log, on_update_db=on_update_db)

        self.fs = fs
        self.log.debug("Initializing K8S Juju connector")

        db_uri = EnvironConfig(prefixes=["OSMLCM_", "OSMMON_"]).get("database_uri")
        self._store = MotorStore(db_uri)
        self.loading_libjuju = asyncio.Lock()
        self.uninstall_locks = {}

        self.log.debug("K8S Juju connector initialized")
        # TODO: Remove these commented lines:
        # self.authenticated = False
        # self.models = {}
        # self.juju_secret = ""

    """Initialization"""

    async def init_env(
        self,
        k8s_creds: str,
        namespace: str = "kube-system",
        reuse_cluster_uuid: str = None,
        **kwargs,
    ) -> (str, bool):
        """
        It prepares a given K8s cluster environment to run Juju bundles.

        :param k8s_creds: credentials to access a given K8s cluster, i.e. a valid
            '.kube/config'
        :param namespace: optional namespace to be used for juju. By default,
            'kube-system' will be used
        :param reuse_cluster_uuid: existing cluster uuid for reuse
        :param: kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: uuid of the K8s cluster and True if connector has installed some
            software in the cluster
            (on error, an exception will be raised)
        """
        libjuju = await self._get_libjuju(kwargs.get("vca_id"))

        cluster_uuid = reuse_cluster_uuid or str(uuid.uuid4())
        kubectl = self._get_kubectl(k8s_creds)

        # CREATING RESOURCES IN K8S
        rbac_id = generate_rbac_id()
        metadata_name = "{}-{}".format(RBAC_STACK_PREFIX, rbac_id)
        labels = {RBAC_STACK_PREFIX: rbac_id}

        # Create cleanup dictionary to clean up created resources
        # if it fails in the middle of the process
        cleanup_data = []
        try:
            self.log.debug("Initializing K8s cluster for juju")
            kubectl.create_cluster_role(name=metadata_name, labels=labels)
            self.log.debug("Cluster role created")
            cleanup_data.append(
                {"delete": kubectl.delete_cluster_role, "args": (metadata_name,)}
            )

            kubectl.create_service_account(name=metadata_name, labels=labels)
            self.log.debug("Service account created")
            cleanup_data.append(
                {"delete": kubectl.delete_service_account, "args": (metadata_name,)}
            )

            kubectl.create_cluster_role_binding(name=metadata_name, labels=labels)
            self.log.debug("Role binding created")
            cleanup_data.append(
                {
                    "delete": kubectl.delete_cluster_role_binding,
                    "args": (metadata_name,),
                }
            )
            token, client_cert_data = await kubectl.get_secret_data(metadata_name)

            default_storage_class = kubectl.get_default_storage_class()
            self.log.debug("Default storage class: {}".format(default_storage_class))
            await libjuju.add_k8s(
                name=cluster_uuid,
                rbac_id=rbac_id,
                token=token,
                client_cert_data=client_cert_data,
                configuration=kubectl.configuration,
                storage_class=default_storage_class,
                credential_name=self._get_credential_name(cluster_uuid),
            )
            self.log.debug("K8s cluster added to juju controller")
            return cluster_uuid, True
        except Exception as e:
            self.log.error("Error initializing k8scluster: {}".format(e), exc_info=True)
            if len(cleanup_data) > 0:
                self.log.debug("Cleaning up created resources in k8s cluster...")
                for item in cleanup_data:
                    delete_function = item["delete"]
                    delete_args = item["args"]
                    delete_function(*delete_args)
                self.log.debug("Cleanup finished")
            raise e

    """Repo Management"""

    async def repo_add(
        self,
        name: str,
        url: str,
        _type: str = "charm",
        cert: str = None,
        user: str = None,
        password: str = None,
    ):
        raise MethodNotImplemented()

    async def repo_list(self):
        raise MethodNotImplemented()

    async def repo_remove(self, name: str):
        raise MethodNotImplemented()

    async def synchronize_repos(self, cluster_uuid: str, name: str):
        """
        Returns None as currently add_repo is not implemented
        """
        return None

    """Reset"""

    async def reset(
        self,
        cluster_uuid: str,
        force: bool = False,
        uninstall_sw: bool = False,
        **kwargs,
    ) -> bool:
        """Reset a cluster

        Resets the Kubernetes cluster by removing the model that represents it.

        :param cluster_uuid str: The UUID of the cluster to reset
        :param force: Force reset
        :param uninstall_sw: Boolean to uninstall sw
        :param: kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: Returns True if successful or raises an exception.
        """

        try:
            self.log.debug("[reset] Removing k8s cloud")
            libjuju = await self._get_libjuju(kwargs.get("vca_id"))

            cloud = Cloud(cluster_uuid, self._get_credential_name(cluster_uuid))

            cloud_creds = await libjuju.get_cloud_credentials(cloud)

            await libjuju.remove_cloud(cluster_uuid)

            credentials = self.get_credentials(cluster_uuid=cluster_uuid)

            kubectl = self._get_kubectl(credentials)

            delete_functions = [
                kubectl.delete_cluster_role_binding,
                kubectl.delete_service_account,
                kubectl.delete_cluster_role,
            ]

            credential_attrs = cloud_creds[0].result["attrs"]
            if RBAC_LABEL_KEY_NAME in credential_attrs:
                rbac_id = credential_attrs[RBAC_LABEL_KEY_NAME]
                metadata_name = "{}-{}".format(RBAC_STACK_PREFIX, rbac_id)
                for delete_func in delete_functions:
                    try:
                        delete_func(metadata_name)
                    except Exception as e:
                        self.log.warning("Cannot remove resource in K8s {}".format(e))

        except Exception as e:
            self.log.debug("Caught exception during reset: {}".format(e))
            raise e
        return True

    """Deployment"""

    async def install(
        self,
        cluster_uuid: str,
        kdu_model: str,
        kdu_instance: str,
        atomic: bool = True,
        timeout: float = 1800,
        params: dict = None,
        db_dict: dict = None,
        kdu_name: str = None,
        namespace: str = None,
        **kwargs,
    ) -> bool:
        """Install a bundle

        :param cluster_uuid str: The UUID of the cluster to install to
        :param kdu_model str: The name or path of a bundle to install
        :param kdu_instance: Kdu instance name
        :param atomic bool: If set, waits until the model is active and resets
                            the cluster on failure.
        :param timeout int: The time, in seconds, to wait for the install
                            to finish
        :param params dict: Key-value pairs of instantiation parameters
        :param kdu_name: Name of the KDU instance to be installed
        :param namespace: K8s namespace to use for the KDU instance
        :param kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: If successful, returns ?
        """
        libjuju = await self._get_libjuju(kwargs.get("vca_id"))
        bundle = kdu_model

        if not db_dict:
            raise K8sException("db_dict must be set")
        if not bundle:
            raise K8sException("bundle must be set")

        if bundle.startswith("cs:"):
            # For Juju Bundles provided by the Charm Store
            pass
        elif bundle.startswith("ch:"):
            # For Juju Bundles provided by the Charm Hub (this only works for juju version >= 2.9)
            pass
        elif bundle.startswith("http"):
            # Download the file
            pass
        else:
            new_workdir = kdu_model.strip(kdu_model.split("/")[-1])
            os.chdir(new_workdir)
            bundle = "local:{}".format(kdu_model)

        # default namespace to kdu_instance
        if not namespace:
            namespace = kdu_instance

        self.log.debug("Checking for model named {}".format(namespace))

        # Create the new model
        self.log.debug("Adding model: {}".format(namespace))
        cloud = Cloud(cluster_uuid, self._get_credential_name(cluster_uuid))
        await libjuju.add_model(namespace, cloud)

        # if model:
        # TODO: Instantiation parameters

        """
        "Juju bundle that models the KDU, in any of the following ways:
            - <juju-repo>/<juju-bundle>
            - <juju-bundle folder under k8s_models folder in the package>
            - <juju-bundle tgz file (w/ or w/o extension) under k8s_models folder
                in the package>
            - <URL_where_to_fetch_juju_bundle>
        """
        try:
            previous_workdir = os.getcwd()
        except FileNotFoundError:
            previous_workdir = "/app/storage"

        self.log.debug("[install] deploying {}".format(bundle))
        instantiation_params = params.get("overlay") if params else None
        await libjuju.deploy(
            bundle,
            model_name=namespace,
            wait=atomic,
            timeout=timeout,
            instantiation_params=instantiation_params,
        )
        os.chdir(previous_workdir)

        # update information in the database (first, the VCA status, and then, the namespace)
        if self.on_update_db:
            await self.on_update_db(
                cluster_uuid,
                kdu_instance,
                filter=db_dict["filter"],
                vca_id=kwargs.get("vca_id"),
            )

        self.db.set_one(
            table="nsrs",
            q_filter={"_admin.deployed.K8s.kdu-instance": kdu_instance},
            update_dict={"_admin.deployed.K8s.$.namespace": namespace},
        )

        return True

    async def scale(
        self,
        kdu_instance: str,
        scale: int,
        resource_name: str,
        total_timeout: float = 1800,
        namespace: str = None,
        **kwargs,
    ) -> bool:
        """Scale an application in a model

        :param: kdu_instance str:        KDU instance name
        :param: scale int:               Scale to which to set the application
        :param: resource_name str:       The application name in the Juju Bundle
        :param: timeout float:           The time, in seconds, to wait for the install
                                         to finish
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param kwargs:                   Additional parameters
                                            vca_id (str): VCA ID

        :return: If successful, returns True
        """

        model_name = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )
        try:
            libjuju = await self._get_libjuju(kwargs.get("vca_id"))
            await libjuju.scale_application(
                model_name=model_name,
                application_name=resource_name,
                scale=scale,
                total_timeout=total_timeout,
            )
        except Exception as e:
            error_msg = "Error scaling application {} of the model {} of the kdu instance {}: {}".format(
                resource_name, model_name, kdu_instance, e
            )
            self.log.error(error_msg)
            raise K8sException(message=error_msg)
        return True

    async def get_scale_count(
        self, resource_name: str, kdu_instance: str, namespace: str = None, **kwargs
    ) -> int:
        """Get an application scale count

        :param: resource_name str:       The application name in the Juju Bundle
        :param: kdu_instance str:        KDU instance name
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param kwargs:                   Additional parameters
                                            vca_id (str): VCA ID
        :return: Return application instance count
        """

        model_name = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )
        try:
            libjuju = await self._get_libjuju(kwargs.get("vca_id"))
            status = await libjuju.get_model_status(model_name=model_name)
            return len(status.applications[resource_name].units)
        except Exception as e:
            error_msg = (
                f"Error getting scale count from application {resource_name} of the model {model_name} of "
                f"the kdu instance {kdu_instance}: {e}"
            )
            self.log.error(error_msg)
            raise K8sException(message=error_msg)

    async def instances_list(self, cluster_uuid: str) -> list:
        """
        returns a list of deployed releases in a cluster

        :param cluster_uuid: the cluster
        :return:
        """
        return []

    async def upgrade(
        self,
        cluster_uuid: str,
        kdu_instance: str,
        kdu_model: str = None,
        params: dict = None,
    ) -> str:
        """Upgrade a model

        :param cluster_uuid str: The UUID of the cluster to upgrade
        :param kdu_instance str: The unique name of the KDU instance
        :param kdu_model str: The name or path of the bundle to upgrade to
        :param params dict: Key-value pairs of instantiation parameters

        :return: If successful, reference to the new revision number of the
                 KDU instance.
        """

        # TODO: Loop through the bundle and upgrade each charm individually

        """
        The API doesn't have a concept of bundle upgrades, because there are
        many possible changes: charm revision, disk, number of units, etc.

        As such, we are only supporting a limited subset of upgrades. We'll
        upgrade the charm revision but leave storage and scale untouched.

        Scale changes should happen through OSM constructs, and changes to
        storage would require a redeployment of the service, at least in this
        initial release.
        """
        raise MethodNotImplemented()

    """Rollback"""

    async def rollback(
        self, cluster_uuid: str, kdu_instance: str, revision: int = 0
    ) -> str:
        """Rollback a model

        :param cluster_uuid str: The UUID of the cluster to rollback
        :param kdu_instance str: The unique name of the KDU instance
        :param revision int: The revision to revert to. If omitted, rolls back
                             the previous upgrade.

        :return: If successful, returns the revision of active KDU instance,
                 or raises an exception
        """
        raise MethodNotImplemented()

    """Deletion"""

    async def uninstall(
        self, cluster_uuid: str, kdu_instance: str, namespace: str = None, **kwargs
    ) -> bool:
        """Uninstall a KDU instance

        :param cluster_uuid str: The UUID of the cluster
        :param kdu_instance str: The unique name of the KDU instance
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: Returns True if successful, or raises an exception
        """
        model_name = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )

        self.log.debug(f"[uninstall] Destroying model: {model_name}")

        will_not_delete = False
        if model_name not in self.uninstall_locks:
            self.uninstall_locks[model_name] = asyncio.Lock()
        delete_lock = self.uninstall_locks[model_name]

        while delete_lock.locked():
            will_not_delete = True
            await asyncio.sleep(0.1)

        if will_not_delete:
            self.log.info("Model {} deleted by another worker.".format(model_name))
            return True

        try:
            async with delete_lock:
                libjuju = await self._get_libjuju(kwargs.get("vca_id"))

                await libjuju.destroy_model(model_name, total_timeout=3600)
        finally:
            self.uninstall_locks.pop(model_name)

        self.log.debug(f"[uninstall] Model {model_name} destroyed")
        return True

    async def upgrade_charm(
        self,
        ee_id: str = None,
        path: str = None,
        charm_id: str = None,
        charm_type: str = None,
        timeout: float = None,
    ) -> str:
        """This method upgrade charms in VNFs

        Args:
            ee_id:  Execution environment id
            path:   Local path to the charm
            charm_id:   charm-id
            charm_type: Charm type can be lxc-proxy-charm, native-charm or k8s-proxy-charm
            timeout: (Float)    Timeout for the ns update operation

        Returns:
            The output of the update operation if status equals to "completed"
        """
        raise K8sException(
            "KDUs deployed with Juju Bundle do not support charm upgrade"
        )

    async def exec_primitive(
        self,
        cluster_uuid: str = None,
        kdu_instance: str = None,
        primitive_name: str = None,
        timeout: float = 300,
        params: dict = None,
        db_dict: dict = None,
        namespace: str = None,
        **kwargs,
    ) -> str:
        """Exec primitive (Juju action)

        :param cluster_uuid str: The UUID of the cluster
        :param kdu_instance str: The unique name of the KDU instance
        :param primitive_name: Name of action that will be executed
        :param timeout: Timeout for action execution
        :param params: Dictionary of all the parameters needed for the action
        :param db_dict: Dictionary for any additional data
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: Returns the output of the action
        """
        libjuju = await self._get_libjuju(kwargs.get("vca_id"))

        namespace = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )

        if not params or "application-name" not in params:
            raise K8sException(
                "Missing application-name argument, \
                                argument needed for K8s actions"
            )
        try:
            self.log.debug(
                "[exec_primitive] Getting model "
                "{} for the kdu_instance: {}".format(namespace, kdu_instance)
            )
            application_name = params["application-name"]
            actions = await libjuju.get_actions(
                application_name=application_name, model_name=namespace
            )
            if primitive_name not in actions:
                raise K8sException("Primitive {} not found".format(primitive_name))
            output, status = await libjuju.execute_action(
                application_name=application_name,
                model_name=namespace,
                action_name=primitive_name,
                **params,
            )

            if status != "completed":
                raise K8sException(
                    "status is not completed: {} output: {}".format(status, output)
                )
            if self.on_update_db:
                await self.on_update_db(
                    cluster_uuid=cluster_uuid,
                    kdu_instance=kdu_instance,
                    filter=db_dict["filter"],
                )

            return output

        except Exception as e:
            error_msg = "Error executing primitive {}: {}".format(primitive_name, e)
            self.log.error(error_msg)
            raise K8sException(message=error_msg)

    """Introspection"""

    async def inspect_kdu(self, kdu_model: str) -> dict:
        """Inspect a KDU

        Inspects a bundle and returns a dictionary of config parameters and
        their default values.

        :param kdu_model str: The name or path of the bundle to inspect.

        :return: If successful, returns a dictionary of available parameters
                 and their default values.
        """

        kdu = {}
        if not os.path.exists(kdu_model):
            raise K8sException("file {} not found".format(kdu_model))

        with open(kdu_model, "r") as f:
            bundle = yaml.safe_load(f.read())

            """
            {
                'description': 'Test bundle',
                'bundle': 'kubernetes',
                'applications': {
                    'mariadb-k8s': {
                        'charm': 'cs:~charmed-osm/mariadb-k8s-20',
                        'scale': 1,
                        'options': {
                            'password': 'manopw',
                            'root_password': 'osm4u',
                            'user': 'mano'
                        },
                        'series': 'kubernetes'
                    }
                }
            }
            """
            # TODO: This should be returned in an agreed-upon format
            kdu = bundle["applications"]

        return kdu

    async def help_kdu(self, kdu_model: str) -> str:
        """View the README

                If available, returns the README of the bundle.

                :param kdu_model str: The name or path of a bundle
        f
                :return: If found, returns the contents of the README.
        """
        readme = None

        files = ["README", "README.txt", "README.md"]
        path = os.path.dirname(kdu_model)
        for file in os.listdir(path):
            if file in files:
                with open(file, "r") as f:
                    readme = f.read()
                    break

        return readme

    async def status_kdu(
        self,
        cluster_uuid: str,
        kdu_instance: str,
        complete_status: bool = False,
        yaml_format: bool = False,
        namespace: str = None,
        **kwargs,
    ) -> Union[str, dict]:
        """Get the status of the KDU

        Get the current status of the KDU instance.

        :param cluster_uuid str: The UUID of the cluster
        :param kdu_instance str: The unique id of the KDU instance
        :param complete_status: To get the complete_status of the KDU
        :param yaml_format: To get the status in proper format for NSR record
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param: kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: Returns a dictionary containing namespace, state, resources,
                 and deployment_time and returns complete_status if complete_status is True
        """
        libjuju = await self._get_libjuju(kwargs.get("vca_id"))
        status = {}

        model_name = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )
        model_status = await libjuju.get_model_status(model_name=model_name)

        if not complete_status:
            for name in model_status.applications:
                application = model_status.applications[name]
                status[name] = {"status": application["status"]["status"]}
        else:
            if yaml_format:
                return obj_to_yaml(model_status)
            else:
                return obj_to_dict(model_status)

        return status

    async def add_relation(
        self, provider: RelationEndpoint, requirer: RelationEndpoint
    ):
        """
        Add relation between two charmed endpoints

        :param: provider: Provider relation endpoint
        :param: requirer: Requirer relation endpoint
        """
        self.log.debug(f"adding new relation between {provider} and {requirer}")
        cross_model_relation = (
            provider.model_name != requirer.model_name
            or provider.vca_id != requirer.vca_id
        )
        try:
            if cross_model_relation:
                # Cross-model relation
                provider_libjuju = await self._get_libjuju(provider.vca_id)
                requirer_libjuju = await self._get_libjuju(requirer.vca_id)
                offer = await provider_libjuju.offer(provider)
                if offer:
                    saas_name = await requirer_libjuju.consume(
                        requirer.model_name, offer, provider_libjuju
                    )
                    await requirer_libjuju.add_relation(
                        requirer.model_name, requirer.endpoint, saas_name
                    )
            else:
                # Standard relation
                vca_id = provider.vca_id
                model = provider.model_name
                libjuju = await self._get_libjuju(vca_id)
                # add juju relations between two applications
                await libjuju.add_relation(
                    model_name=model,
                    endpoint_1=provider.endpoint,
                    endpoint_2=requirer.endpoint,
                )
        except Exception as e:
            message = f"Error adding relation between {provider} and {requirer}: {e}"
            self.log.error(message)
            raise Exception(message=message)

    async def update_vca_status(
        self, vcastatus: dict, kdu_instance: str, namespace: str = None, **kwargs
    ):
        """
        Add all configs, actions, executed actions of all applications in a model to vcastatus dict

        :param vcastatus dict: dict containing vcastatus
        :param kdu_instance str: The unique id of the KDU instance
        :param namespace str: The namespace (model) where the Bundle was deployed
        :param: kwargs: Additional parameters
            vca_id (str): VCA ID

        :return: None
        """

        model_name = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )

        libjuju = await self._get_libjuju(kwargs.get("vca_id"))
        try:
            for vca_model_name in vcastatus:
                # Adding executed actions
                vcastatus[vca_model_name][
                    "executedActions"
                ] = await libjuju.get_executed_actions(model_name=model_name)

                for application in vcastatus[vca_model_name]["applications"]:
                    # Adding application actions
                    vcastatus[vca_model_name]["applications"][application][
                        "actions"
                    ] = {}
                    # Adding application configs
                    vcastatus[vca_model_name]["applications"][application][
                        "configs"
                    ] = await libjuju.get_application_configs(
                        model_name=model_name, application_name=application
                    )

        except Exception as e:
            self.log.debug("Error in updating vca status: {}".format(str(e)))

    async def get_services(
        self, cluster_uuid: str, kdu_instance: str, namespace: str
    ) -> list:
        """Return a list of services of a kdu_instance"""

        namespace = self._obtain_namespace(
            kdu_instance=kdu_instance, namespace=namespace
        )

        credentials = self.get_credentials(cluster_uuid=cluster_uuid)
        kubectl = self._get_kubectl(credentials)
        return kubectl.get_services(
            field_selector="metadata.namespace={}".format(namespace)
        )

    async def get_service(
        self, cluster_uuid: str, service_name: str, namespace: str
    ) -> object:
        """Return data for a specific service inside a namespace"""

        credentials = self.get_credentials(cluster_uuid=cluster_uuid)
        kubectl = self._get_kubectl(credentials)
        return kubectl.get_services(
            field_selector="metadata.name={},metadata.namespace={}".format(
                service_name, namespace
            )
        )[0]

    def get_credentials(self, cluster_uuid: str) -> str:
        """
        Get Cluster Kubeconfig
        """
        k8scluster = self.db.get_one(
            "k8sclusters", q_filter={"_id": cluster_uuid}, fail_on_empty=False
        )

        self.db.encrypt_decrypt_fields(
            k8scluster.get("credentials"),
            "decrypt",
            ["password", "secret"],
            schema_version=k8scluster["schema_version"],
            salt=k8scluster["_id"],
        )

        return yaml.safe_dump(k8scluster.get("credentials"))

    def _get_credential_name(self, cluster_uuid: str) -> str:
        """
        Get credential name for a k8s cloud

        We cannot use the cluster_uuid for the credential name directly,
        because it cannot start with a number, it must start with a letter.
        Therefore, the k8s cloud credential name will be "cred-" followed
        by the cluster uuid.

        :param: cluster_uuid:   Cluster UUID of the kubernetes cloud (=cloud_name)

        :return:                Name to use for the credential name.
        """
        return "cred-{}".format(cluster_uuid)

    def get_namespace(self, cluster_uuid: str) -> str:
        """Get the namespace UUID
        Gets the namespace's unique name

        :param cluster_uuid str: The UUID of the cluster
        :returns: The namespace UUID, or raises an exception
        """
        pass

    @staticmethod
    def generate_kdu_instance_name(**kwargs):
        db_dict = kwargs.get("db_dict")
        kdu_name = kwargs.get("kdu_name", None)
        if kdu_name:
            kdu_instance = "{}-{}".format(kdu_name, db_dict["filter"]["_id"])
        else:
            kdu_instance = db_dict["filter"]["_id"]
        return kdu_instance

    async def _get_libjuju(self, vca_id: str = None) -> Libjuju:
        """
        Get libjuju object

        :param: vca_id: VCA ID
                        If None, get a libjuju object with a Connection to the default VCA
                        Else, geta libjuju object with a Connection to the specified VCA
        """
        if not vca_id:
            while self.loading_libjuju.locked():
                await asyncio.sleep(0.1)
            if not self.libjuju:
                async with self.loading_libjuju:
                    vca_connection = await get_connection(self._store)
                    self.libjuju = Libjuju(vca_connection, log=self.log)
            return self.libjuju
        else:
            vca_connection = await get_connection(self._store, vca_id)
            return Libjuju(vca_connection, log=self.log, n2vc=self)

    def _get_kubectl(self, credentials: str) -> Kubectl:
        """
        Get Kubectl object

        :param: kubeconfig_credentials: Kubeconfig credentials
        """
        kubecfg = tempfile.NamedTemporaryFile()
        with open(kubecfg.name, "w") as kubecfg_file:
            kubecfg_file.write(credentials)
        return Kubectl(config_file=kubecfg.name)

    def _obtain_namespace(self, kdu_instance: str, namespace: str = None) -> str:
        """
        Obtain the namespace/model name to use in the instantiation of a Juju Bundle in K8s. The default namespace is
        the kdu_instance name. However, if the user passes the namespace where he wants to deploy the bundle,
        that namespace will be used.

        :param kdu_instance: the default KDU instance name
        :param namespace: the namespace passed by the User
        """

        # deault the namespace/model name to the kdu_instance name TODO -> this should be the real return... But
        #  once the namespace is not passed in most methods, I had to do this in another way. But I think this should
        #  be the procedure in the future return namespace if namespace else kdu_instance

        # TODO -> has referred above, this should be avoided in the future, this is temporary, in order to avoid
        #  compatibility issues
        return (
            namespace
            if namespace
            else self._obtain_namespace_from_db(kdu_instance=kdu_instance)
        )

    def _obtain_namespace_from_db(self, kdu_instance: str) -> str:
        db_nsrs = self.db.get_one(
            table="nsrs", q_filter={"_admin.deployed.K8s.kdu-instance": kdu_instance}
        )
        for k8s in db_nsrs["_admin"]["deployed"]["K8s"]:
            if k8s.get("kdu-instance") == kdu_instance:
                return k8s.get("namespace")
        return ""
