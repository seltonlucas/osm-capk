#######################################################################################
# Copyright ETSI Contributors and Others.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#######################################################################################


import base64


async def create_secret(self, secret_name, secret_namespace, secret_key, secret_value):
    async def check_secret(secret_name, secret_namespace, secret_key, secret_value):
        self.logger.info(f"Checking content of secret {secret_name} ...")
        returned_secret_data = await self._kubectl.get_secret_content(
            name=secret_name,
            namespace=secret_namespace,
        )
        returned_secret_value = base64.b64decode(
            returned_secret_data[secret_key]
        ).decode("utf-8")
        # self.logger.debug(f"secret_data_original={secret_value}")
        # self.logger.debug(f"secret_data_received={returned_secret_value}")
        self.logger.info(
            f"Result of secret comparison: {secret_value==returned_secret_value}"
        )

    self.logger.info(
        f"Creating secret {secret_name} in namespace {secret_namespace} ..."
    )
    secret_data = {secret_key: base64.b64encode(secret_value.encode()).decode("utf-8")}
    self.logger.info(
        f"Calling N2VC kubectl to create secret. Namespace: {secret_namespace}. Secret name: {secret_name}. Secret data:{secret_data}."
    )
    await self._kubectl.create_secret(
        name=secret_name,
        data=secret_data,
        namespace=secret_namespace,
        secret_type="Opaque",
    )
    self.logger.info(f"Secret {secret_name} CREATED")

    await check_secret(secret_name, secret_namespace, secret_key, secret_value)


def delete_secret(self, secret_name, secret_namespace):
    try:
        self._kubectl.delete_secret(name=secret_name, namespace=secret_namespace)
        self.logger.info(
            f"Deleted secret {secret_name} in namespace {secret_namespace}"
        )
    except Exception as e:
        self.logger.error(
            f"Could not delete secret {secret_name} in namespace {secret_namespace}: {e}"
        )


async def create_configmap(self, configmap_name, configmap_namespace, data):
    self.logger.info(f"Checking content of configmap {data} ...")
    self.logger.info(
        f"Calling N2VC kubectl to create configmap. Namespace: {configmap_namespace}. configmap name: {configmap_name}. data:{data}."
    )
    await self._kubectl.create_configmap(
        name=configmap_name,
        data=data,
        namespace=configmap_namespace,
    )
    self.logger.info(f"configmap {configmap_name} CREATED")


def delete_configmap(self, configmap_name, configmap_namespace):
    try:
        self._kubectl.delete_configmap(
            name=configmap_name, namespace=configmap_namespace
        )
        self.logger.info(
            f"Deleted configmap {configmap_name} in namespace {configmap_namespace}"
        )
    except Exception as e:
        self.logger.error(
            f"Could not delete configmap {configmap_name} in namespace {configmap_namespace}: {e}"
        )
