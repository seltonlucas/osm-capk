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

import typing

from osm_lcm.n2vc.config import EnvironConfig, ModelConfig
from osm_lcm.n2vc.store import Store
from osm_lcm.n2vc.vca.cloud import Cloud
from osm_lcm.n2vc.vca.connection_data import ConnectionData


class Connection:
    def __init__(self, store: Store, vca_id: str = None):
        """
        Contructor

        :param: store: Store object. Used to communicate wuth the DB
        :param: vca_id: Id of the VCA. If none specified, the default VCA will be used.
        """
        self._data = None
        self.default = vca_id is None
        self._vca_id = vca_id
        self._store = store

    async def load(self):
        """Load VCA connection data"""
        await self._load_vca_connection_data()

    @property
    def is_default(self):
        return self._vca_id is None

    @property
    def data(self) -> ConnectionData:
        return self._data

    async def _load_vca_connection_data(self) -> typing.NoReturn:
        """
        Load VCA connection data

        If self._vca_id is None, it will get the VCA data from the Environment variables,
        and the default VCA will be used. If it is not None, then it means that it will
        load the credentials from the database (A non-default VCA will be used).
        """
        if self._vca_id:
            self._data = await self._store.get_vca_connection_data(self._vca_id)
        else:
            envs = EnvironConfig()
            # Get endpoints from the DB and ENV. Check if update in the database is needed or not.
            db_endpoints = await self._store.get_vca_endpoints()
            env_endpoints = (
                envs["endpoints"].split(",")
                if "endpoints" in envs
                else ["{}:{}".format(envs["host"], envs.get("port", 17070))]
            )

            db_update_needed = not all(e in db_endpoints for e in env_endpoints)

            endpoints = env_endpoints if db_update_needed else db_endpoints
            config = {
                "endpoints": endpoints,
                "user": envs["user"],
                "secret": envs["secret"],
                "cacert": envs["cacert"],
                "pubkey": envs.get("pubkey"),
                "lxd-cloud": envs.get("cloud"),
                "lxd-credentials": envs.get("credentials", envs.get("cloud")),
                "k8s-cloud": envs.get("k8s_cloud"),
                "k8s-credentials": envs.get("k8s_credentials", envs.get("k8s_cloud")),
                "model-config": ModelConfig(envs),
                "api-proxy": envs.get("api_proxy", None),
            }
            self._data = ConnectionData(**config)
            if db_update_needed:
                await self.update_endpoints(endpoints)

    @property
    def endpoints(self):
        return self._data.endpoints

    async def update_endpoints(self, endpoints: typing.List[str]):
        await self._store.update_vca_endpoints(endpoints, self._vca_id)
        self._data.endpoints = endpoints

    @property
    def lxd_cloud(self) -> Cloud:
        return Cloud(self.data.lxd_cloud, self.data.lxd_credentials)

    @property
    def k8s_cloud(self) -> Cloud:
        return Cloud(self.data.k8s_cloud, self.data.k8s_credentials)


async def get_connection(store: Store, vca_id: str = None) -> Connection:
    """
    Get Connection

    Method to get a Connection object with the VCA information loaded
    """
    connection = Connection(store, vca_id=vca_id)
    await connection.load()
    return connection
