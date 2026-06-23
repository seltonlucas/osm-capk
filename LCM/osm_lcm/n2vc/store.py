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

import abc
import typing

from motor.motor_asyncio import AsyncIOMotorClient
from osm_lcm.n2vc.config import EnvironConfig
from osm_lcm.n2vc.vca.connection_data import ConnectionData
from osm_common.dbmongo import DbMongo, DbException
from osm_common.dbbase import Encryption


DB_NAME = "osm"


class Store(abc.ABC):
    @abc.abstractmethod
    async def get_vca_connection_data(self, vca_id: str) -> ConnectionData:
        """
        Get VCA connection data

        :param: vca_id: VCA ID

        :returns: ConnectionData with the information of the database
        """

    @abc.abstractmethod
    async def update_vca_endpoints(self, hosts: typing.List[str], vca_id: str):
        """
        Update VCA endpoints

        :param: endpoints: List of endpoints to write in the database
        :param: vca_id: VCA ID
        """

    @abc.abstractmethod
    async def get_vca_endpoints(self, vca_id: str = None) -> typing.List[str]:
        """
        Get list if VCA endpoints

        :param: vca_id: VCA ID

        :returns: List of endpoints
        """

    @abc.abstractmethod
    async def get_vca_id(self, vim_id: str = None) -> str:
        """
        Get VCA id for a VIM account

        :param: vim_id: Vim account ID
        """


class DbMongoStore(Store):
    def __init__(self, db: DbMongo):
        """
        Constructor

        :param: db: osm_common.dbmongo.DbMongo object
        """
        self.db = db

    async def get_vca_connection_data(self, vca_id: str) -> ConnectionData:
        """
        Get VCA connection data

        :param: vca_id: VCA ID

        :returns: ConnectionData with the information of the database
        """
        data = self.db.get_one("vca", q_filter={"_id": vca_id})
        self.db.encrypt_decrypt_fields(
            data,
            "decrypt",
            ["secret", "cacert"],
            schema_version=data["schema_version"],
            salt=data["_id"],
        )
        return ConnectionData(**data)

    async def update_vca_endpoints(
        self, endpoints: typing.List[str], vca_id: str = None
    ):
        """
        Update VCA endpoints

        :param: endpoints: List of endpoints to write in the database
        :param: vca_id: VCA ID
        """
        if vca_id:
            data = self.db.get_one("vca", q_filter={"_id": vca_id})
            data["endpoints"] = endpoints
            self._update("vca", vca_id, data)
        else:
            # The default VCA. Data for the endpoints is in a different place
            juju_info = self._get_juju_info()
            # If it doesn't, then create it
            if not juju_info:
                try:
                    self.db.create(
                        "vca",
                        {"_id": "juju"},
                    )
                except DbException as e:
                    # Racing condition: check if another N2VC worker has created it
                    juju_info = self._get_juju_info()
                    if not juju_info:
                        raise e
            self.db.set_one(
                "vca",
                {"_id": "juju"},
                {"api_endpoints": endpoints},
            )

    async def get_vca_endpoints(self, vca_id: str = None) -> typing.List[str]:
        """
        Get list if VCA endpoints

        :param: vca_id: VCA ID

        :returns: List of endpoints
        """
        endpoints = []
        if vca_id:
            endpoints = self.get_vca_connection_data(vca_id).endpoints
        else:
            juju_info = self._get_juju_info()
            if juju_info and "api_endpoints" in juju_info:
                endpoints = juju_info["api_endpoints"]
        return endpoints

    async def get_vca_id(self, vim_id: str = None) -> str:
        """
        Get VCA ID from the database for a given VIM account ID

        :param: vim_id: VIM account ID
        """
        return (
            self.db.get_one(
                "vim_accounts",
                q_filter={"_id": vim_id},
                fail_on_empty=False,
            ).get("vca")
            if vim_id
            else None
        )

    def _update(self, collection: str, id: str, data: dict):
        """
        Update object in database

        :param: collection: Collection name
        :param: id: ID of the object
        :param: data: Object data
        """
        self.db.replace(
            collection,
            id,
            data,
        )

    def _get_juju_info(self):
        """Get Juju information (the default VCA) from the admin collection"""
        return self.db.get_one(
            "vca",
            q_filter={"_id": "juju"},
            fail_on_empty=False,
        )


class MotorStore(Store):
    def __init__(self, uri: str):
        """
        Constructor

        :param: uri: Connection string to connect to the database.
        """
        self._client = AsyncIOMotorClient(uri)
        self._secret_key = None
        self._config = EnvironConfig(prefixes=["OSMLCM_", "OSMMON_"])
        self.encryption = Encryption(
            uri=uri,
            config=self._config,
            encoding_type="utf-8",
            logger_name="db",
        )

    @property
    def _database(self):
        return self._client[DB_NAME]

    @property
    def _vca_collection(self):
        return self._database["vca"]

    @property
    def _admin_collection(self):
        return self._database["admin"]

    @property
    def _vim_accounts_collection(self):
        return self._database["vim_accounts"]

    async def get_vca_connection_data(self, vca_id: str) -> ConnectionData:
        """
        Get VCA connection data

        :param: vca_id: VCA ID

        :returns: ConnectionData with the information of the database
        """
        data = await self._vca_collection.find_one({"_id": vca_id})
        if not data:
            raise Exception("vca with id {} not found".format(vca_id))
        await self.encryption.decrypt_fields(
            data,
            ["secret", "cacert"],
            schema_version=data["schema_version"],
            salt=data["_id"],
        )
        return ConnectionData(**data)

    async def update_vca_endpoints(
        self, endpoints: typing.List[str], vca_id: str = None
    ):
        """
        Update VCA endpoints

        :param: endpoints: List of endpoints to write in the database
        :param: vca_id: VCA ID
        """
        if vca_id:
            data = await self._vca_collection.find_one({"_id": vca_id})
            data["endpoints"] = endpoints
            await self._vca_collection.replace_one({"_id": vca_id}, data)
        else:
            # The default VCA. Data for the endpoints is in a different place
            juju_info = await self._get_juju_info()
            # If it doesn't, then create it
            if not juju_info:
                try:
                    await self._admin_collection.insert_one({"_id": "juju"})
                except Exception as e:
                    # Racing condition: check if another N2VC worker has created it
                    juju_info = await self._get_juju_info()
                    if not juju_info:
                        raise e

            await self._admin_collection.replace_one(
                {"_id": "juju"}, {"api_endpoints": endpoints}
            )

    async def get_vca_endpoints(self, vca_id: str = None) -> typing.List[str]:
        """
        Get list if VCA endpoints

        :param: vca_id: VCA ID

        :returns: List of endpoints
        """
        endpoints = []
        if vca_id:
            endpoints = (await self.get_vca_connection_data(vca_id)).endpoints
        else:
            juju_info = await self._get_juju_info()
            if juju_info and "api_endpoints" in juju_info:
                endpoints = juju_info["api_endpoints"]
        return endpoints

    async def get_vca_id(self, vim_id: str = None) -> str:
        """
        Get VCA ID from the database for a given VIM account ID

        :param: vim_id: VIM account ID
        """
        vca_id = None
        if vim_id:
            vim_account = await self._vim_accounts_collection.find_one({"_id": vim_id})
            if vim_account and "vca" in vim_account:
                vca_id = vim_account["vca"]
        return vca_id

    async def _get_juju_info(self):
        """Get Juju information (the default VCA) from the admin collection"""
        return await self._admin_collection.find_one({"_id": "juju"})
