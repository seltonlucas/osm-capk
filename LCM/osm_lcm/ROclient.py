#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##
# Copyright 2015 Telefónica Investigación y Desarrollo, S.A.U.
#
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
##

"""
asyncio RO python client to interact with RO-server
"""

import asyncio
import aiohttp
import json
import yaml
import logging
from urllib.parse import quote
from uuid import UUID
from copy import deepcopy

__author__ = "Alfonso Tierno"
__date__ = "$09-Jan-2018 09:09:48$"
__version__ = "0.1.2"
version_date = "2018-05-16"
requests = None


class ROClientException(Exception):
    def __init__(self, message, http_code=400):
        """Common Exception for all RO client exceptions"""
        self.http_code = http_code
        Exception.__init__(self, message)


def remove_envelop(item, indata=None):
    """
    Obtain the useful data removing the envelop. It goes through the vnfd or nsd catalog and returns the
    vnfd or nsd content
    :param item: can be 'tenant', 'vim', 'vnfd', 'nsd', 'ns'
    :param indata: Content to be inspected
    :return: the useful part of indata (a reference, not a new dictionay)
    """
    clean_indata = indata
    if not indata:
        return {}
    if item == "vnfd":
        if clean_indata.get("vnfd:vnfd-catalog"):
            clean_indata = clean_indata["vnfd:vnfd-catalog"]
        elif clean_indata.get("vnfd-catalog"):
            clean_indata = clean_indata["vnfd-catalog"]
        if clean_indata.get("vnfd"):
            if (
                not isinstance(clean_indata["vnfd"], list)
                or len(clean_indata["vnfd"]) != 1
            ):
                raise ROClientException("'vnfd' must be a list only one element")
            clean_indata = clean_indata["vnfd"][0]
    elif item == "nsd":
        if clean_indata.get("nsd:nsd-catalog"):
            clean_indata = clean_indata["nsd:nsd-catalog"]
        elif clean_indata.get("nsd-catalog"):
            clean_indata = clean_indata["nsd-catalog"]
        if clean_indata.get("nsd"):
            if (
                not isinstance(clean_indata["nsd"], list)
                or len(clean_indata["nsd"]) != 1
            ):
                raise ROClientException("'nsd' must be a list only one element")
            clean_indata = clean_indata["nsd"][0]
    elif item == "sdn":
        if len(indata) == 1 and "sdn_controller" in indata:
            clean_indata = indata["sdn_controller"]
    elif item == "tenant":
        if len(indata) == 1 and "tenant" in indata:
            clean_indata = indata["tenant"]
    elif item in ("vim", "vim_account", "datacenters"):
        if len(indata) == 1 and "datacenter" in indata:
            clean_indata = indata["datacenter"]
    elif item == "wim":
        if len(indata) == 1 and "wim" in indata:
            clean_indata = indata["wim"]
    elif item == "wim_account":
        if len(indata) == 1 and "wim_account" in indata:
            clean_indata = indata["wim_account"]
    elif item == "ns" or item == "instances":
        if len(indata) == 1 and "instance" in indata:
            clean_indata = indata["instance"]
    else:
        raise ROClientException("remove_envelop with unknown item {}".format(item))

    return clean_indata


class ROClient:
    headers_req = {"Accept": "application/yaml", "content-type": "application/yaml"}
    client_to_RO = {
        "tenant": "tenants",
        "vim": "datacenters",
        "vim_account": "datacenters",
        "sdn": "sdn_controllers",
        "vnfd": "vnfs",
        "nsd": "scenarios",
        "wim": "wims",
        "wim_account": "wims",
        "ns": "instances",
    }
    mandatory_for_create = {
        "tenant": ("name",),
        "vnfd": ("name", "id"),
        "nsd": ("name", "id"),
        "ns": ("name", "scenario", "datacenter"),
        "vim": ("name", "vim_url"),
        "wim": ("name", "wim_url"),
        "vim_account": (),
        "wim_account": (),
        "sdn": ("name", "type"),
    }
    timeout_large = 120
    timeout_short = 30

    def __init__(self, uri, **kwargs):
        self.uri = uri

        self.username = kwargs.get("username")
        self.password = kwargs.get("password")
        self.tenant_id_name = kwargs.get("tenant")
        self.tenant = None
        self.datacenter_id_name = kwargs.get("datacenter")
        self.datacenter = None
        logger_name = kwargs.get("logger_name", "lcm.ro")
        self.logger = logging.getLogger(logger_name)
        if kwargs.get("loglevel"):
            self.logger.setLevel(kwargs["loglevel"])
        global requests
        requests = kwargs.get("TODO remove")

    def __getitem__(self, index):
        if index == "tenant":
            return self.tenant_id_name
        elif index == "datacenter":
            return self.datacenter_id_name
        elif index == "username":
            return self.username
        elif index == "password":
            return self.password
        elif index == "uri":
            return self.uri
        else:
            raise KeyError("Invalid key '{}'".format(index))

    def __setitem__(self, index, value):
        if index == "tenant":
            self.tenant_id_name = value
        elif index == "datacenter" or index == "vim":
            self.datacenter_id_name = value
        elif index == "username":
            self.username = value
        elif index == "password":
            self.password = value
        elif index == "uri":
            self.uri = value
        else:
            raise KeyError("Invalid key '{}'".format(index))
        self.tenant = None  # force to reload tenant with different credentials
        self.datacenter = None  # force to reload datacenter with different credentials

    @staticmethod
    def _parse(descriptor, descriptor_format, response=False):
        if (
            descriptor_format
            and descriptor_format != "json"
            and descriptor_format != "yaml"
        ):
            raise ROClientException(
                "'descriptor_format' must be a 'json' or 'yaml' text"
            )
        if descriptor_format != "json":
            try:
                return yaml.safe_load(descriptor)
            except yaml.YAMLError as exc:
                error_pos = ""
                if hasattr(exc, "problem_mark"):
                    mark = exc.problem_mark
                    error_pos = " at line:{} column:{}s".format(
                        mark.line + 1, mark.column + 1
                    )
                error_text = "yaml format error" + error_pos
        elif descriptor_format != "yaml":
            try:
                return json.loads(descriptor)
            except Exception as e:
                if response:
                    error_text = "json format error" + str(e)

        if response:
            raise ROClientException(error_text)
        raise ROClientException(error_text)

    @staticmethod
    def _parse_error_yaml(descriptor):
        json_error = None
        try:
            json_error = yaml.safe_load(descriptor)
            return json_error["error"]["description"]
        except Exception:
            return str(json_error or descriptor)

    @staticmethod
    def _parse_yaml(descriptor, response=False):
        try:
            return yaml.safe_load(descriptor)
        except yaml.YAMLError as exc:
            error_pos = ""
            if hasattr(exc, "problem_mark"):
                mark = exc.problem_mark
                error_pos = " at line:{} column:{}s".format(
                    mark.line + 1, mark.column + 1
                )
            error_text = "yaml format error" + error_pos
            if response:
                raise ROClientException(error_text)
            raise ROClientException(error_text)

    @staticmethod
    def check_if_uuid(uuid_text):
        """
        Check if text correspond to an uuid foramt
        :param uuid_text:
        :return: True if it is an uuid False if not
        """
        try:
            UUID(uuid_text)
            return True
        except Exception:
            return False

    @staticmethod
    def _create_envelop(item, indata=None):
        """
        Returns a new dict that incledes indata with the expected envelop
        :param item: can be 'tenant', 'vim', 'vnfd', 'nsd', 'ns'
        :param indata: Content to be enveloped
        :return: a new dic with {<envelop>: {indata} } where envelop can be e.g. tenant, datacenter, ...
        """
        if item == "vnfd":
            return {"vnfd-catalog": {"vnfd": [indata]}}
        elif item == "nsd":
            return {"nsd-catalog": {"nsd": [indata]}}
        elif item == "tenant":
            return {"tenant": indata}
        elif item in ("vim", "vim_account", "datacenter"):
            return {"datacenter": indata}
        elif item == "wim":
            return {"wim": indata}
        elif item == "wim_account":
            return {"wim_account": indata}
        elif item == "ns" or item == "instances":
            return {"instance": indata}
        elif item == "sdn":
            return {"sdn_controller": indata}
        else:
            raise ROClientException("remove_envelop with unknown item {}".format(item))

    @staticmethod
    def update_descriptor(desc, kwargs):
        desc = deepcopy(desc)  # do not modify original descriptor
        try:
            for k, v in kwargs.items():
                update_content = desc
                kitem_old = None
                klist = k.split(".")
                for kitem in klist:
                    if kitem_old is not None:
                        update_content = update_content[kitem_old]
                    if isinstance(update_content, dict):
                        kitem_old = kitem
                    elif isinstance(update_content, list):
                        kitem_old = int(kitem)
                    else:
                        raise ROClientException(
                            "Invalid query string '{}'. Descriptor is not a list nor dict at '{}'".format(
                                k, kitem
                            )
                        )
                if v == "__DELETE__":
                    del update_content[kitem_old]
                else:
                    update_content[kitem_old] = v
            return desc
        except KeyError:
            raise ROClientException(
                "Invalid query string '{}'. Descriptor does not contain '{}'".format(
                    k, kitem_old
                )
            )
        except ValueError:
            raise ROClientException(
                "Invalid query string '{}'. Expected integer index list instead of '{}'".format(
                    k, kitem
                )
            )
        except IndexError:
            raise ROClientException(
                "Invalid query string '{}'. Index '{}' out of  range".format(
                    k, kitem_old
                )
            )

    async def _get_item_uuid(self, session, item, item_id_name, all_tenants=False):
        if all_tenants:
            tenant_text = "/any"
        elif all_tenants is None:
            tenant_text = ""
        else:
            if not self.tenant:
                await self._get_tenant(session)
            tenant_text = "/" + self.tenant

        item_id = 0
        url = "{}{}/{}".format(self.uri, tenant_text, item)
        if self.check_if_uuid(item_id_name):
            item_id = item_id_name
            url += "/" + item_id_name
        elif (
            item_id_name and item_id_name.startswith("'") and item_id_name.endswith("'")
        ):
            item_id_name = item_id_name[1:-1]
        self.logger.debug("RO GET %s", url)
        # timeout = aiohttp.ClientTimeout(total=self.timeout_short)
        async with session.get(url, headers=self.headers_req) as response:
            response_text = await response.read()
            self.logger.debug(
                "GET {} [{}] {}".format(url, response.status, response_text[:100])
            )
            if response.status == 404:  # NOT_FOUND
                raise ROClientException(
                    "No {} found with id '{}'".format(item[:-1], item_id_name),
                    http_code=404,
                )
            if response.status >= 300:
                raise ROClientException(
                    self._parse_error_yaml(response_text), http_code=response.status
                )
        content = self._parse_yaml(response_text, response=True)

        if item_id:
            return item_id
        desc = content[item]
        if not isinstance(desc, list):
            raise ROClientException(
                "_get_item_uuid get a non dict with a list inside {}".format(type(desc))
            )
        uuid = None
        for i in desc:
            if item_id_name and i["name"] != item_id_name:
                continue
            if uuid:  # found more than one
                raise ROClientException(
                    "Found more than one {} with name '{}'. uuid must be used".format(
                        item, item_id_name
                    ),
                    http_code=404,
                )
            uuid = i["uuid"]
        if not uuid:
            raise ROClientException(
                "No {} found with name '{}'".format(item[:-1], item_id_name),
                http_code=404,
            )
        return uuid

    async def _get_tenant(self, session):
        if not self.tenant:
            self.tenant = await self._get_item_uuid(
                session, "tenants", self.tenant_id_name, None
            )
        return self.tenant

    async def _get_datacenter(self, session):
        if not self.tenant:
            await self._get_tenant(session)
        if not self.datacenter:
            self.datacenter = await self._get_item_uuid(
                session, "datacenters", self.datacenter_id_name, True
            )
        return self.datacenter

    async def _create_item(
        self,
        session,
        item,
        descriptor,
        item_id_name=None,
        action=None,
        all_tenants=False,
    ):
        if all_tenants:
            tenant_text = "/any"
        elif all_tenants is None:
            tenant_text = ""
        else:
            if not self.tenant:
                await self._get_tenant(session)
            tenant_text = "/" + self.tenant
        payload_req = yaml.safe_dump(descriptor)
        # print payload_req

        api_version_text = ""
        if item == "vnfs":
            # assumes version v3 only
            api_version_text = "/v3"
            item = "vnfd"
        elif item == "scenarios":
            # assumes version v3 only
            api_version_text = "/v3"
            item = "nsd"

        if not item_id_name:
            uuid = ""
        elif self.check_if_uuid(item_id_name):
            uuid = "/{}".format(item_id_name)
        else:
            # check that exist
            uuid = await self._get_item_uuid(session, item, item_id_name, all_tenants)
            uuid = "/{}".format(uuid)
        if not action:
            action = ""
        else:
            action = "/{}".format(action)

        url = "{}{apiver}{tenant}/{item}{id}{action}".format(
            self.uri,
            apiver=api_version_text,
            tenant=tenant_text,
            item=item,
            id=uuid,
            action=action,
        )
        self.logger.debug("RO POST %s %s", url, payload_req)
        # timeout = aiohttp.ClientTimeout(total=self.timeout_large)
        async with session.post(
            url, headers=self.headers_req, data=payload_req
        ) as response:
            response_text = await response.read()
            self.logger.debug(
                "POST {} [{}] {}".format(url, response.status, response_text[:100])
            )
            if response.status >= 300:
                raise ROClientException(
                    self._parse_error_yaml(response_text), http_code=response.status
                )

        return self._parse_yaml(response_text, response=True)

    async def _del_item(self, session, item, item_id_name, all_tenants=False):
        if all_tenants:
            tenant_text = "/any"
        elif all_tenants is None:
            tenant_text = ""
        else:
            if not self.tenant:
                await self._get_tenant(session)
            tenant_text = "/" + self.tenant
        if not self.check_if_uuid(item_id_name):
            # check that exist
            _all_tenants = all_tenants
            if item in ("datacenters", "wims"):
                _all_tenants = True
            uuid = await self._get_item_uuid(
                session, item, item_id_name, all_tenants=_all_tenants
            )
        else:
            uuid = item_id_name

        url = "{}{}/{}/{}".format(self.uri, tenant_text, item, uuid)
        self.logger.debug("DELETE %s", url)
        # timeout = aiohttp.ClientTimeout(total=self.timeout_short)
        async with session.delete(url, headers=self.headers_req) as response:
            response_text = await response.read()
            self.logger.debug(
                "DELETE {} [{}] {}".format(url, response.status, response_text[:100])
            )
            if response.status >= 300:
                raise ROClientException(
                    self._parse_error_yaml(response_text), http_code=response.status
                )

        return self._parse_yaml(response_text, response=True)

    async def _list_item(self, session, item, all_tenants=False, filter_dict=None):
        if all_tenants:
            tenant_text = "/any"
        elif all_tenants is None:
            tenant_text = ""
        else:
            if not self.tenant:
                await self._get_tenant(session)
            tenant_text = "/" + self.tenant

        url = "{}{}/{}".format(self.uri, tenant_text, item)
        separator = "?"
        if filter_dict:
            for k in filter_dict:
                url += separator + quote(str(k)) + "=" + quote(str(filter_dict[k]))
                separator = "&"
        self.logger.debug("RO GET %s", url)
        # timeout = aiohttp.ClientTimeout(total=self.timeout_short)
        async with session.get(url, headers=self.headers_req) as response:
            response_text = await response.read()
            self.logger.debug(
                "GET {} [{}] {}".format(url, response.status, response_text[:100])
            )
            if response.status >= 300:
                raise ROClientException(
                    self._parse_error_yaml(response_text), http_code=response.status
                )

        return self._parse_yaml(response_text, response=True)

    async def _edit_item(self, session, item, item_id, descriptor, all_tenants=False):
        if all_tenants:
            tenant_text = "/any"
        elif all_tenants is None:
            tenant_text = ""
        else:
            if not self.tenant:
                await self._get_tenant(session)
            tenant_text = "/" + self.tenant

        payload_req = yaml.safe_dump(descriptor)

        # print payload_req
        url = "{}{}/{}/{}".format(self.uri, tenant_text, item, item_id)
        self.logger.debug("RO PUT %s %s", url, payload_req)
        # timeout = aiohttp.ClientTimeout(total=self.timeout_large)
        async with session.put(
            url, headers=self.headers_req, data=payload_req
        ) as response:
            response_text = await response.read()
            self.logger.debug(
                "PUT {} [{}] {}".format(url, response.status, response_text[:100])
            )
            if response.status >= 300:
                raise ROClientException(
                    self._parse_error_yaml(response_text), http_code=response.status
                )

        return self._parse_yaml(response_text, response=True)

    async def get_version(self):
        """
        Obtain RO server version.
        :return: a list with integers ["major", "minor", "release"]. Raises ROClientException on Error,
        """
        try:
            response_text = ""
            async with aiohttp.ClientSession() as session:
                url = "{}/version".format(self.uri)
                self.logger.debug("RO GET %s", url)
                # timeout = aiohttp.ClientTimeout(total=self.timeout_short)
                async with session.get(url, headers=self.headers_req) as response:
                    response_text = await response.read()
                    self.logger.debug(
                        "GET {} [{}] {}".format(
                            url, response.status, response_text[:100]
                        )
                    )
                    if response.status >= 300:
                        raise ROClientException(
                            self._parse_error_yaml(response_text),
                            http_code=response.status,
                        )

                for word in str(response_text).split(" "):
                    if "." in word:
                        version_text, _, _ = word.partition("-")
                        return version_text
                raise ROClientException(
                    "Got invalid version text: '{}'".format(response_text),
                    http_code=500,
                )
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)
        except Exception as e:
            self.logger.critical(
                "Got invalid version text: '{}'; causing exception {}".format(
                    response_text, str(e)
                )
            )
            raise ROClientException(
                "Got invalid version text: '{}'; causing exception {}".format(
                    response_text, e
                ),
                http_code=500,
            )

    async def get_list(self, item, all_tenants=False, filter_by=None):
        """
        List of items filtered by the contents in the dictionary "filter_by".
        :param item: can be 'tenant', 'vim', 'vnfd', 'nsd', 'ns'
        :param all_tenants: True if not filtering by tenant. Only allowed for admin
        :param filter_by: dictionary with filtering
        :return: a list of dict. It can be empty. Raises ROClientException on Error,
        """
        try:
            if item not in self.client_to_RO:
                raise ROClientException("Invalid item {}".format(item))
            if item == "tenant":
                all_tenants = None
            async with aiohttp.ClientSession() as session:
                content = await self._list_item(
                    session,
                    self.client_to_RO[item],
                    all_tenants=all_tenants,
                    filter_dict=filter_by,
                )
            if isinstance(content, dict):
                if len(content) == 1:
                    for _, v in content.items():
                        return v
                    return content.values()[0]
                else:
                    raise ROClientException(
                        "Output not a list neither dict with len equal 1", http_code=500
                    )
                return content
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)

    async def delete(self, item, item_id_name=None, all_tenants=False):
        """
        Delete  the information of an item from its id or name
        :param item: can be 'tenant', 'vim', 'vnfd', 'nsd', 'ns'
        :param item_id_name: RO id or name of the item. Raise and exception if more than one found
        :param all_tenants: True if not filtering by tenant. Only allowed for admin
        :return: dictionary with the information or raises ROClientException on Error, NotFound, found several
        """
        try:
            if item not in self.client_to_RO:
                raise ROClientException("Invalid item {}".format(item))
            if item in ("tenant", "vim", "wim"):
                all_tenants = None

            async with aiohttp.ClientSession() as session:
                result = await self._del_item(
                    session,
                    self.client_to_RO[item],
                    item_id_name,
                    all_tenants=all_tenants,
                )
                # in case of ns delete, get the action_id embeded in text
                if item == "ns" and result.get("result"):
                    _, _, action_id = result["result"].partition("action_id=")
                    action_id, _, _ = action_id.partition(" ")
                    if action_id:
                        result["action_id"] = action_id
                return result
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)

    async def edit(
        self, item, item_id_name, descriptor=None, descriptor_format=None, **kwargs
    ):
        """Edit an item
        :param item: can be 'tenant', 'vim', 'vnfd', 'nsd', 'ns', 'vim'
        :param item_id_name: RO id or name of the item. Raise and exception if more than one found
        :param descriptor: can be a dict, or a yaml/json text. Autodetect unless descriptor_format is provided
        :param descriptor_format: Can be 'json' or 'yaml'
        :param kwargs: Overrides descriptor with values as name, description, vim_url, vim_url_admin, vim_type
               keys can be a dot separated list to specify elements inside dict
        :return: dictionary with the information or raises ROClientException on Error
        """
        try:
            if isinstance(descriptor, str):
                descriptor = self._parse(descriptor, descriptor_format)
            elif descriptor:
                pass
            else:
                descriptor = {}

            if item not in self.client_to_RO:
                raise ROClientException("Invalid item {}".format(item))
            desc = remove_envelop(item, descriptor)

            # Override descriptor with kwargs
            if kwargs:
                desc = self.update_descriptor(desc, kwargs)
            all_tenants = False
            if item in ("tenant", "vim"):
                all_tenants = None

            create_desc = self._create_envelop(item, desc)

            async with aiohttp.ClientSession() as session:
                _all_tenants = all_tenants
                if item == "vim":
                    _all_tenants = True
                item_id = await self._get_item_uuid(
                    session,
                    self.client_to_RO[item],
                    item_id_name,
                    all_tenants=_all_tenants,
                )
                if item == "vim":
                    _all_tenants = None
                # await self._get_tenant(session)
                outdata = await self._edit_item(
                    session,
                    self.client_to_RO[item],
                    item_id,
                    create_desc,
                    all_tenants=_all_tenants,
                )
                return remove_envelop(item, outdata)
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)

    async def create(self, item, descriptor=None, descriptor_format=None, **kwargs):
        """
        Creates an item from its descriptor
        :param item: can be 'tenant', 'vnfd', 'nsd', 'ns', 'vim', 'vim_account', 'sdn'
        :param descriptor: can be a dict, or a yaml/json text. Autodetect unless descriptor_format is provided
        :param descriptor_format: Can be 'json' or 'yaml'
        :param kwargs: Overrides descriptor with values as name, description, vim_url, vim_url_admin, vim_type
               keys can be a dot separated list to specify elements inside dict
        :return: dictionary with the information or raises ROClientException on Error
        """
        try:
            if isinstance(descriptor, str):
                descriptor = self._parse(descriptor, descriptor_format)
            elif descriptor:
                pass
            else:
                descriptor = {}

            if item not in self.client_to_RO:
                raise ROClientException("Invalid item {}".format(item))
            desc = remove_envelop(item, descriptor)

            # Override descriptor with kwargs
            if kwargs:
                desc = self.update_descriptor(desc, kwargs)

            for mandatory in self.mandatory_for_create[item]:
                if mandatory not in desc:
                    raise ROClientException(
                        "'{}' is mandatory parameter for {}".format(mandatory, item)
                    )

            all_tenants = False
            if item in ("tenant", "vim", "wim"):
                all_tenants = None

            create_desc = self._create_envelop(item, desc)

            async with aiohttp.ClientSession() as session:
                outdata = await self._create_item(
                    session,
                    self.client_to_RO[item],
                    create_desc,
                    all_tenants=all_tenants,
                )
                return remove_envelop(item, outdata)
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)

    async def attach(
        self, item, item_id_name=None, descriptor=None, descriptor_format=None, **kwargs
    ):
        """
        Attach a datacenter or wim to a tenant, creating a vim_account, wim_account
        :param item: can be vim_account or wim_account
        :param item_id_name: id or name of the datacenter, wim
        :param descriptor:
        :param descriptor_format:
        :param kwargs:
        :return:
        """
        try:
            if isinstance(descriptor, str):
                descriptor = self._parse(descriptor, descriptor_format)
            elif descriptor:
                pass
            else:
                descriptor = {}

            desc = remove_envelop(item, descriptor)

            # # check that exist
            # uuid = self._get_item_uuid(session, "datacenters", uuid_name, all_tenants=True)
            # tenant_text = "/" + self._get_tenant()
            if kwargs:
                desc = self.update_descriptor(desc, kwargs)

            if item == "vim_account":
                if not desc.get("vim_tenant_name") and not desc.get("vim_tenant_id"):
                    raise ROClientException(
                        "Wrong descriptor. At least vim_tenant_name or vim_tenant_id must be "
                        "provided"
                    )
            elif item != "wim_account":
                raise ROClientException(
                    "Attach with unknown item {}. Must be 'vim_account' or 'wim_account'".format(
                        item
                    )
                )
            create_desc = self._create_envelop(item, desc)
            payload_req = yaml.safe_dump(create_desc)
            async with aiohttp.ClientSession() as session:
                # check that exist
                item_id = await self._get_item_uuid(
                    session, self.client_to_RO[item], item_id_name, all_tenants=True
                )
                await self._get_tenant(session)

                url = "{}/{tenant}/{item}/{item_id}".format(
                    self.uri,
                    tenant=self.tenant,
                    item=self.client_to_RO[item],
                    item_id=item_id,
                )
                self.logger.debug("RO POST %s %s", url, payload_req)
                # timeout = aiohttp.ClientTimeout(total=self.timeout_large)
                async with session.post(
                    url, headers=self.headers_req, data=payload_req
                ) as response:
                    response_text = await response.read()
                    self.logger.debug(
                        "POST {} [{}] {}".format(
                            url, response.status, response_text[:100]
                        )
                    )
                    if response.status >= 300:
                        raise ROClientException(
                            self._parse_error_yaml(response_text),
                            http_code=response.status,
                        )

                response_desc = self._parse_yaml(response_text, response=True)
                desc = remove_envelop(item, response_desc)
                return desc
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)

    async def detach(self, item, item_id_name=None):
        # TODO replace the code with delete_item(vim_account,...)
        try:
            async with aiohttp.ClientSession() as session:
                # check that exist
                item_id = await self._get_item_uuid(
                    session, self.client_to_RO[item], item_id_name, all_tenants=False
                )
                tenant = await self._get_tenant(session)

                url = "{}/{tenant}/{item}/{datacenter}".format(
                    self.uri,
                    tenant=tenant,
                    item=self.client_to_RO[item],
                    datacenter=item_id,
                )
                self.logger.debug("RO DELETE %s", url)

                # timeout = aiohttp.ClientTimeout(total=self.timeout_large)
                async with session.delete(url, headers=self.headers_req) as response:
                    response_text = await response.read()
                    self.logger.debug(
                        "DELETE {} [{}] {}".format(
                            url, response.status, response_text[:100]
                        )
                    )
                    if response.status >= 300:
                        raise ROClientException(
                            self._parse_error_yaml(response_text),
                            http_code=response.status,
                        )

                response_desc = self._parse_yaml(response_text, response=True)
                desc = remove_envelop(item, response_desc)
                return desc
        except (aiohttp.ClientOSError, aiohttp.ClientError) as e:
            raise ROClientException(e, http_code=504)
        except asyncio.TimeoutError:
            raise ROClientException("Timeout", http_code=504)
