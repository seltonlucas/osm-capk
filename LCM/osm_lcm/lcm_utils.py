# -*- coding: utf-8 -*-

##
# Copyright 2018 Telefonica S.A.
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
##

import asyncio
import checksumdir
from collections import OrderedDict
import hashlib
import os
import shutil
import traceback
from time import time

from osm_common.fsbase import FsException
from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem
import yaml
from zipfile import ZipFile, BadZipfile

# from osm_common.dbbase import DbException

__author__ = "Alfonso Tierno"


class LcmException(Exception):
    pass


class LcmExceptionExit(LcmException):
    pass


def versiontuple(v):
    """utility for compare dot separate versions. Fills with zeros to proper number comparison
    package version will be something like 4.0.1.post11+gb3f024d.dirty-1. Where 4.0.1 is the git tag, postXX is the
    number of commits from this tag, and +XXXXXXX is the git commit short id. Total length is 16 with until 999 commits
    """
    filled = []
    for point in v.split("."):
        point, _, _ = point.partition("+")
        point, _, _ = point.partition("-")
        filled.append(point.zfill(20))
    return tuple(filled)


def deep_get(target_dict, key_list, default_value=None):
    """
    Get a value from target_dict entering in the nested keys. If keys does not exist, it returns None
    Example target_dict={a: {b: 5}}; key_list=[a,b] returns 5; both key_list=[a,b,c] and key_list=[f,h] return None
    :param target_dict: dictionary to be read
    :param key_list: list of keys to read from  target_dict
    :param default_value: value to return if key is not present in the nested dictionary
    :return: The wanted value if exist, None otherwise
    """
    for key in key_list:
        if not isinstance(target_dict, dict) or key not in target_dict:
            return default_value
        target_dict = target_dict[key]
    return target_dict


def get_iterable(in_dict, in_key):
    """
    Similar to <dict>.get(), but if value is None, False, ..., An empty tuple is returned instead
    :param in_dict: a dictionary
    :param in_key: the key to look for at in_dict
    :return: in_dict[in_var] or () if it is None or not present
    """
    if not in_dict.get(in_key):
        return ()
    return in_dict[in_key]


def check_juju_bundle_existence(vnfd: dict) -> str:
    """Checks the existence of juju-bundle in the descriptor

    Args:
        vnfd:   Descriptor as a dictionary

    Returns:
        Juju bundle if dictionary has juju-bundle else None

    """
    if vnfd.get("vnfd"):
        vnfd = vnfd["vnfd"]

    for kdu in vnfd.get("kdu", []):
        return kdu.get("juju-bundle", None)


def get_charm_artifact_path(base_folder, charm_name, charm_type, revision=str()) -> str:
    """Finds the charm artifact paths

    Args:
        base_folder:    Main folder which will be looked up for charm
        charm_name:   Charm name
        charm_type:   Type of charm native_charm, lxc_proxy_charm or k8s_proxy_charm
        revision:   vnf package revision number if there is

    Returns:
        artifact_path: (str)

    """
    extension = ""
    if revision:
        extension = ":" + str(revision)

    if base_folder.get("pkg-dir"):
        artifact_path = "{}/{}/{}/{}".format(
            base_folder["folder"].split(":")[0] + extension,
            base_folder["pkg-dir"],
            "charms"
            if charm_type in ("native_charm", "lxc_proxy_charm", "k8s_proxy_charm")
            else "helm-charts",
            charm_name,
        )

    else:
        # For SOL004 packages
        artifact_path = "{}/Scripts/{}/{}".format(
            base_folder["folder"].split(":")[0] + extension,
            "charms"
            if charm_type in ("native_charm", "lxc_proxy_charm", "k8s_proxy_charm")
            else "helm-charts",
            charm_name,
        )

    return artifact_path


def populate_dict(target_dict, key_list, value):
    """
    Update target_dict creating nested dictionaries with the key_list. Last key_list item is asigned the value.
    Example target_dict={K: J}; key_list=[a,b,c];  target_dict will be {K: J, a: {b: {c: value}}}
    :param target_dict: dictionary to be changed
    :param key_list: list of keys to insert at target_dict
    :param value:
    :return: None
    """
    for key in key_list[0:-1]:
        if key not in target_dict:
            target_dict[key] = {}
        target_dict = target_dict[key]
    target_dict[key_list[-1]] = value


def get_ee_id_parts(ee_id):
    """
    Parses ee_id stored at database that can be either 'version:namespace.helm_id' or only
    namespace.helm_id for backward compatibility
    If exists helm version can be helm-v3 or helm (helm-v2 old version)
    """
    version, _, part_id = ee_id.rpartition(":")
    namespace, _, helm_id = part_id.rpartition(".")
    return version, namespace, helm_id


def vld_to_ro_ip_profile(source_data):
    if source_data:
        return {
            "ip_version": "IPv4"
            if "v4" in source_data.get("ip-version", "ipv4")
            else "IPv6",
            "subnet_address": source_data.get("cidr")
            or source_data.get("subnet-address"),
            "gateway_address": source_data.get("gateway-ip")
            or source_data.get("gateway-address"),
            "dns_address": ";".join(
                [v["address"] for v in source_data["dns-server"] if v.get("address")]
            )
            if source_data.get("dns-server")
            else None,
            "dhcp_enabled": source_data.get("dhcp-params", {}).get("enabled", False)
            or source_data.get("dhcp-enabled", False),
            "dhcp_start_address": source_data["dhcp-params"].get("start-address")
            if source_data.get("dhcp-params")
            else None,
            "dhcp_count": source_data["dhcp-params"].get("count")
            if source_data.get("dhcp-params")
            else None,
            "ipv6_address_mode": source_data["ipv6-address-mode"]
            if "ipv6-address-mode" in source_data
            else None,
        }


class LcmBase:
    def __init__(self, msg, logger):
        """

        :param db: database connection
        """
        self.db = Database().instance.db
        self.msg = msg
        self.fs = Filesystem().instance.fs
        self.logger = logger

    def update_db_2(self, item, _id, _desc):
        """
        Updates database with _desc information. If success _desc is cleared
        :param item: collection
        :param _id: the _id to use in the query filter
        :param _desc: dictionary with the content to update. Keys are dot separated keys for
        :return: None. Exception is raised on error
        """
        if not _desc:
            return
        now = time()
        _desc["_admin.modified"] = now
        self.logger.info("Desc: {} Item: {} _id: {}".format(_desc, item, _id))
        self.db.set_one(item, {"_id": _id}, _desc)
        _desc.clear()
        # except DbException as e:
        #     self.logger.error("Updating {} _id={} with '{}'. Error: {}".format(item, _id, _desc, e))

    @staticmethod
    def calculate_charm_hash(zipped_file):
        """Calculate the hash of charm files which ends with .charm

        Args:
            zipped_file (str): Existing charm package full path

        Returns:
            hex digest  (str): The hash of the charm file
        """
        filehash = hashlib.sha256()
        with open(zipped_file, mode="rb") as file:
            contents = file.read()
            filehash.update(contents)
            return filehash.hexdigest()

    @staticmethod
    def compare_charm_hash(current_charm, target_charm):
        """Compare the existing charm and the target charm if the charms
        are given as zip files ends with .charm

        Args:
            current_charm (str): Existing charm package full path
            target_charm  (str): Target charm package full path

        Returns:
            True/False (bool): if charm has changed it returns True
        """
        return LcmBase.calculate_charm_hash(
            current_charm
        ) != LcmBase.calculate_charm_hash(target_charm)

    @staticmethod
    def compare_charmdir_hash(current_charm_dir, target_charm_dir):
        """Compare the existing charm and the target charm if the charms
        are given as directories

        Args:
            current_charm_dir (str): Existing charm package directory path
            target_charm_dir  (str): Target charm package directory path

        Returns:
            True/False (bool): if charm has changed it returns True
        """
        return checksumdir.dirhash(current_charm_dir) != checksumdir.dirhash(
            target_charm_dir
        )

    def check_charm_hash_changed(
        self, current_charm_path: str, target_charm_path: str
    ) -> bool:
        """Find the target charm has changed or not by checking the hash of
        old and new charm packages

        Args:
            current_charm_path (str): Existing charm package artifact path
            target_charm_path  (str): Target charm package artifact path

        Returns:
            True/False (bool): if charm has changed it returns True

        """
        try:
            # Check if the charm artifacts are available
            current_charm = self.fs.path + current_charm_path
            target_charm = self.fs.path + target_charm_path

            if os.path.exists(current_charm) and os.path.exists(target_charm):
                # Compare the hash of .charm files
                if current_charm.endswith(".charm"):
                    return LcmBase.compare_charm_hash(current_charm, target_charm)

                # Compare the hash of charm folders
                return LcmBase.compare_charmdir_hash(current_charm, target_charm)

            else:
                raise LcmException(
                    "Charm artifact {} does not exist in the VNF Package".format(
                        self.fs.path + target_charm_path
                    )
                )
        except (IOError, OSError, TypeError) as error:
            self.logger.debug(traceback.format_exc())
            self.logger.error(f"{error} occured while checking the charm hashes")
            raise LcmException(error)

    @staticmethod
    def get_charm_name(charm_metadata_file: str) -> str:
        """Get the charm name from metadata file.

        Args:
            charm_metadata_file    (str):  charm metadata file full path

        Returns:
            charm_name    (str):  charm name

        """
        # Read charm metadata.yaml to get the charm name
        with open(charm_metadata_file, "r") as metadata_file:
            content = yaml.safe_load(metadata_file)
            charm_name = content["name"]
            return str(charm_name)

    def _get_charm_path(
        self, nsd_package_path: str, nsd_package_name: str, charm_folder_name: str
    ) -> str:
        """Get the full path of charm folder.

        Args:
            nsd_package_path    (str):  NSD package full path
            nsd_package_name    (str):  NSD package name
            charm_folder_name   (str):  folder name

        Returns:
            charm_path    (str):  charm folder full path
        """
        charm_path = (
            self.fs.path
            + nsd_package_path
            + "/"
            + nsd_package_name
            + "/charms/"
            + charm_folder_name
        )
        return charm_path

    def _get_charm_metadata_file(
        self,
        charm_folder_name: str,
        nsd_package_path: str,
        nsd_package_name: str,
        charm_path: str = None,
    ) -> str:
        """Get the path of charm metadata file.

        Args:
            charm_folder_name   (str):  folder name
            nsd_package_path    (str):  NSD package full path
            nsd_package_name    (str):  NSD package name
            charm_path  (str):  Charm full path

        Returns:
            charm_metadata_file_path    (str):  charm metadata file full path

        """
        # Locate the charm metadata.yaml
        if charm_folder_name.endswith(".charm"):
            extract_path = (
                self.fs.path
                + nsd_package_path
                + "/"
                + nsd_package_name
                + "/charms/"
                + charm_folder_name.replace(".charm", "")
            )
            # Extract .charm to extract path
            with ZipFile(charm_path, "r") as zipfile:
                zipfile.extractall(extract_path)
            return extract_path + "/metadata.yaml"
        else:
            return charm_path + "/metadata.yaml"

    def find_charm_name(self, db_nsr: dict, charm_folder_name: str) -> str:
        """Get the charm name from metadata.yaml of charm package.

        Args:
            db_nsr  (dict): NS record as a dictionary
            charm_folder_name   (str): charm folder name

        Returns:
             charm_name (str):  charm name
        """
        try:
            if not charm_folder_name:
                raise LcmException("charm_folder_name should be provided.")

            # Find nsd_package details: path, name
            revision = db_nsr.get("revision", "")

            # Get the NSD package path
            if revision:
                nsd_package_path = db_nsr["nsd-id"] + ":" + str(revision)
                db_nsd = self.db.get_one("nsds_revisions", {"_id": nsd_package_path})

            else:
                nsd_package_path = db_nsr["nsd-id"]

                db_nsd = self.db.get_one("nsds", {"_id": nsd_package_path})

            # Get the NSD package name
            nsd_package_name = db_nsd["_admin"]["storage"]["pkg-dir"]

            # Remove the existing nsd package and sync from FsMongo
            shutil.rmtree(self.fs.path + nsd_package_path, ignore_errors=True)
            self.fs.sync(from_path=nsd_package_path)

            # Get the charm path
            charm_path = self._get_charm_path(
                nsd_package_path, nsd_package_name, charm_folder_name
            )

            # Find charm metadata file full path
            charm_metadata_file = self._get_charm_metadata_file(
                charm_folder_name, nsd_package_path, nsd_package_name, charm_path
            )

            # Return charm name
            return self.get_charm_name(charm_metadata_file)

        except (
            yaml.YAMLError,
            IOError,
            FsException,
            KeyError,
            TypeError,
            FileNotFoundError,
            BadZipfile,
        ) as error:
            self.logger.debug(traceback.format_exc())
            self.logger.error(f"{error} occured while getting the charm name")
            raise LcmException(error)

    def get_vca_info(self, ee_item, db_nsr, get_charm_name: bool):
        vca_name = charm_name = vca_type = None
        if ee_item.get("juju"):
            vca_name = ee_item["juju"].get("charm")
            if get_charm_name:
                charm_name = self.find_charm_name(db_nsr, str(vca_name))
            vca_type = (
                "lxc_proxy_charm"
                if ee_item["juju"].get("charm") is not None
                else "native_charm"
            )
            if ee_item["juju"].get("cloud") == "k8s":
                vca_type = "k8s_proxy_charm"
            elif ee_item["juju"].get("proxy") is False:
                vca_type = "native_charm"
        elif ee_item.get("helm-chart"):
            vca_name = ee_item["helm-chart"]
            vca_type = "helm-v3"
        return vca_name, charm_name, vca_type


class TaskRegistry(LcmBase):
    """
    Implements a registry of task needed for later cancelation, look for related tasks that must be completed before
    etc. It stores a four level dict
    First level is the topic, ns, vim_account, sdn
    Second level is the _id
    Third level is the operation id
    Fourth level is a descriptive name, the value is the task class

    The HA (High-Availability) methods are used when more than one LCM instance is running.
    To register the current task in the external DB, use LcmBase as base class, to be able
    to reuse LcmBase.update_db_2()
    The DB registry uses the following fields to distinguish a task:
    - op_type: operation type ("nslcmops" or "nsilcmops")
    - op_id:   operation ID
    - worker:  the worker ID for this process
    """

    # NS/NSI: "services" VIM/WIM/SDN: "accounts"
    topic_service_list = ["ns", "nsi"]
    topic_account_list = [
        "vim",
        "wim",
        "sdn",
        "k8scluster",
        "vca",
        "k8srepo",
        "cluster",
        "k8s_app",
        "k8s_resource",
        "k8s_infra_controller",
        "k8s_infra_config",
        "oka",
        "ksu",
        "appinstance",
    ]

    # Map topic to InstanceID
    topic2instid_dict = {"ns": "nsInstanceId", "nsi": "netsliceInstanceId"}

    # Map topic to DB table name
    topic2dbtable_dict = {
        "ns": "nslcmops",
        "nsi": "nsilcmops",
        "vim": "vim_accounts",
        "wim": "wim_accounts",
        "sdn": "sdns",
        "k8scluster": "k8sclusters",
        "vca": "vca",
        "k8srepo": "k8srepos",
        "cluster": "k8sclusters",
        "k8s_app": "k8sapp",
        "k8s_resource": "k8sresource",
        "k8s_infra_controller": "k8sinfra_controller",
        "k8s_infra_config": "k8sinfra_config",
        "oka": "oka",
        "ksu": "ksus",
        "appinstance": "appinstances",
    }

    def __init__(self, worker_id=None, logger=None):
        self.task_registry = {
            "ns": {},
            "nsi": {},
            "vim_account": {},
            "wim_account": {},
            "sdn": {},
            "k8scluster": {},
            "vca": {},
            "k8srepo": {},
            "cluster": {},
            "k8s_app": {},
            "k8s_resource": {},
            "k8s_infra_controller": {},
            "k8s_infra_config": {},
            "oka": {},
            "ksu": {},
            "odu": {},
            "appinstance": {},
        }
        self.worker_id = worker_id
        self.db = Database().instance.db
        self.logger = logger
        # self.logger.info("Task registry: {}".format(self.task_registry))

    def register(self, topic, _id, op_id, task_name, task):
        """
        Register a new task
        :param topic: Can be "ns", "nsi", "vim_account", "sdn"
        :param _id: _id of the related item
        :param op_id: id of the operation of the related item
        :param task_name: Task descriptive name, as create, instantiate, terminate. Must be unique in this op_id
        :param task: Task class
        :return: none
        """
        self.logger.info(
            "topic : {}, _id:{}, op_id:{}, taskname:{}, task:{}".format(
                topic, _id, op_id, task_name, task
            )
        )
        if _id not in self.task_registry[topic]:
            self.task_registry[topic][_id] = OrderedDict()
        if op_id not in self.task_registry[topic][_id]:
            self.task_registry[topic][_id][op_id] = {task_name: task}
        else:
            self.task_registry[topic][_id][op_id][task_name] = task
        self.logger.info("Task registry: {}".format(self.task_registry))
        # print("registering task", topic, _id, op_id, task_name, task)

    def remove(self, topic, _id, op_id, task_name=None):
        """
        When task is ended, it should be removed. It ignores missing tasks. It also removes tasks done with this _id
        :param topic: Can be "ns", "nsi", "vim_account", "sdn"
        :param _id: _id of the related item
        :param op_id: id of the operation of the related item
        :param task_name: Task descriptive name. If none it deletes all tasks with same _id and op_id
        :return: None
        """
        if not self.task_registry[topic].get(_id):
            return
        if not task_name:
            self.task_registry[topic][_id].pop(op_id, None)
        elif self.task_registry[topic][_id].get(op_id):
            self.task_registry[topic][_id][op_id].pop(task_name, None)

        # delete done tasks
        for op_id_ in list(self.task_registry[topic][_id]):
            for name, task in self.task_registry[topic][_id][op_id_].items():
                if not task.done():
                    break
            else:
                del self.task_registry[topic][_id][op_id_]
        if not self.task_registry[topic][_id]:
            del self.task_registry[topic][_id]

    def lookfor_related(self, topic, _id, my_op_id=None):
        task_list = []
        task_name_list = []
        if _id not in self.task_registry[topic]:
            return "", task_name_list
        for op_id in reversed(self.task_registry[topic][_id]):
            if my_op_id:
                if my_op_id == op_id:
                    my_op_id = None  # so that the next task is taken
                continue

            for task_name, task in self.task_registry[topic][_id][op_id].items():
                if not task.done():
                    task_list.append(task)
                    task_name_list.append(task_name)
            break
        return ", ".join(task_name_list), task_list

    def cancel(self, topic, _id, target_op_id=None, target_task_name=None):
        """
        Cancel all active tasks of a concrete ns, nsi, vim_account, sdn identified for _id. If op_id is supplied only
        this is cancelled, and the same with task_name
        :return: cancelled task to be awaited if needed
        """
        if not self.task_registry[topic].get(_id):
            return
        for op_id in reversed(self.task_registry[topic][_id]):
            if target_op_id and target_op_id != op_id:
                continue
            for task_name, task in list(self.task_registry[topic][_id][op_id].items()):
                if target_task_name and target_task_name != task_name:
                    continue
                # result =
                task.cancel()
                yield task
                # if result:
                #     self.logger.debug("{} _id={} order_id={} task={} cancelled".format(topic, _id, op_id, task_name))

    # Is topic NS/NSI?
    def _is_service_type_HA(self, topic):
        return topic in self.topic_service_list

    # Is topic VIM/WIM/SDN?
    def _is_account_type_HA(self, topic):
        return topic in self.topic_account_list

    # Input: op_id, example: 'abc123def:3' Output: account_id='abc123def', op_index=3
    def _get_account_and_op_HA(self, op_id):
        if not op_id:
            return None, None
        account_id, _, op_index = op_id.rpartition(":")
        if not account_id or not op_index.isdigit():
            return None, None
        return account_id, op_index

    # Get '_id' for any topic and operation
    def _get_instance_id_HA(self, topic, op_type, op_id):
        _id = None
        # Special operation 'ANY', for SDN account associated to a VIM account: op_id as '_id'
        if op_type == "ANY":
            _id = op_id
        # NS/NSI: Use op_id as '_id'
        elif self._is_service_type_HA(topic):
            _id = op_id
        # VIM/SDN/WIM/K8SCLUSTER: Split op_id to get Account ID and Operation Index, use Account ID as '_id'
        elif self._is_account_type_HA(topic):
            _id, _ = self._get_account_and_op_HA(op_id)
        return _id

    # Set DB _filter for querying any related process state
    def _get_waitfor_filter_HA(self, db_lcmop, topic, op_type, op_id):
        _filter = {}
        # Special operation 'ANY', for SDN account associated to a VIM account: op_id as '_id'
        # In this special case, the timestamp is ignored
        if op_type == "ANY":
            _filter = {"operationState": "PROCESSING"}
        # Otherwise, get 'startTime' timestamp for this operation
        else:
            # NS/NSI
            if self._is_service_type_HA(topic):
                now = time()
                starttime_this_op = db_lcmop.get("startTime")
                instance_id_label = self.topic2instid_dict.get(topic)
                instance_id = db_lcmop.get(instance_id_label)
                _filter = {
                    instance_id_label: instance_id,
                    "operationState": "PROCESSING",
                    "startTime.lt": starttime_this_op,
                    "_admin.modified.gt": now
                    - 2 * 3600,  # ignore if tow hours of inactivity
                }
            # VIM/WIM/SDN/K8scluster
            elif self._is_account_type_HA(topic):
                _, op_index = self._get_account_and_op_HA(op_id)
                _ops = db_lcmop["_admin"]["operations"]
                _this_op = _ops[int(op_index)]
                starttime_this_op = _this_op.get("startTime", None)
                _filter = {
                    "operationState": "PROCESSING",
                    "startTime.lt": starttime_this_op,
                }
        return _filter

    # Get DB params for any topic and operation
    def _get_dbparams_for_lock_HA(self, topic, op_type, op_id):
        q_filter = {}
        update_dict = {}
        # NS/NSI
        if self._is_service_type_HA(topic):
            q_filter = {"_id": op_id, "_admin.worker": None}
            update_dict = {"_admin.worker": self.worker_id}
        # VIM/WIM/SDN
        elif self._is_account_type_HA(topic):
            account_id, op_index = self._get_account_and_op_HA(op_id)
            if not account_id:
                return None, None
            if op_type == "create":
                # Creating a VIM/WIM/SDN account implies setting '_admin.current_operation' = 0
                op_index = 0
            q_filter = {
                "_id": account_id,
                "_admin.operations.{}.worker".format(op_index): None,
            }
            update_dict = {
                "_admin.operations.{}.worker".format(op_index): self.worker_id,
                "_admin.current_operation": op_index,
            }
        return q_filter, update_dict

    def lock_HA(self, topic, op_type, op_id):
        """
        Lock a task, if possible, to indicate to the HA system that
        the task will be executed in this LCM instance.
        :param topic: Can be "ns", "nsi", "vim", "wim", or "sdn"
        :param op_type: Operation type, can be "nslcmops", "nsilcmops", "create", "edit", "delete"
        :param op_id: NS, NSI: Operation ID  VIM,WIM,SDN: Account ID + ':' + Operation Index
        :return:
        True=lock was successful => execute the task (not registered by any other LCM instance)
        False=lock failed => do NOT execute the task (already registered by another LCM instance)

        HA tasks and backward compatibility:
        If topic is "account type" (VIM/WIM/SDN) and op_id is None, 'op_id' was not provided by NBI.
        This means that the running NBI instance does not support HA.
        In such a case this method should always return True, to always execute
        the task in this instance of LCM, without querying the DB.
        """

        # Backward compatibility for VIM/WIM/SDN/k8scluster without op_id
        self.logger.info("Lock_HA")
        if self._is_account_type_HA(topic) and op_id is None:
            return True

        # Try to lock this task
        db_table_name = self.topic2dbtable_dict[topic]
        q_filter, update_dict = self._get_dbparams_for_lock_HA(topic, op_type, op_id)
        self.logger.info(
            "db table name: {} update dict: {}".format(db_table_name, update_dict)
        )
        db_lock_task = self.db.set_one(
            db_table_name,
            q_filter=q_filter,
            update_dict=update_dict,
            fail_on_empty=False,
        )
        if db_lock_task is None:
            self.logger.debug(
                "Task {} operation={} already locked by another worker".format(
                    topic, op_id
                )
            )
            return False
        else:
            # Set 'detailed-status' to 'In progress' for VIM/WIM/SDN operations
            if self._is_account_type_HA(topic):
                detailed_status = "In progress"
                account_id, op_index = self._get_account_and_op_HA(op_id)
                q_filter = {"_id": account_id}
                update_dict = {
                    "_admin.operations.{}.detailed-status".format(
                        op_index
                    ): detailed_status
                }
                self.db.set_one(
                    db_table_name,
                    q_filter=q_filter,
                    update_dict=update_dict,
                    fail_on_empty=False,
                )
            return True

    def unlock_HA(self, topic, op_type, op_id, operationState, detailed_status):
        """
        Register a task, done when finished a VIM/WIM/SDN 'create' operation.
        :param topic: Can be "vim", "wim", or "sdn"
        :param op_type: Operation type, can be "create", "edit", "delete"
        :param op_id: Account ID + ':' + Operation Index
        :return: nothing
        """
        self.logger.info("Unlock HA")
        # Backward compatibility
        if not self._is_account_type_HA(topic) or not op_id:
            return

        # Get Account ID and Operation Index
        account_id, op_index = self._get_account_and_op_HA(op_id)
        db_table_name = self.topic2dbtable_dict[topic]
        self.logger.info("db_table_name: {}".format(db_table_name))
        # If this is a 'delete' operation, the account may have been deleted (SUCCESS) or may still exist (FAILED)
        # If the account exist, register the HA task.
        # Update DB for HA tasks
        q_filter = {"_id": account_id}
        update_dict = {
            "_admin.operations.{}.operationState".format(op_index): operationState,
            "_admin.operations.{}.detailed-status".format(op_index): detailed_status,
            "_admin.operations.{}.worker".format(op_index): None,
            "_admin.current_operation": None,
        }
        self.logger.info("Update dict: {}".format(update_dict))
        self.db.set_one(
            db_table_name,
            q_filter=q_filter,
            update_dict=update_dict,
            fail_on_empty=False,
        )
        return

    async def waitfor_related_HA(self, topic, op_type, op_id=None):
        """
        Wait for any pending related HA tasks
        """

        # Backward compatibility
        if not (
            self._is_service_type_HA(topic) or self._is_account_type_HA(topic)
        ) and (op_id is None):
            return

        # Get DB table name
        db_table_name = self.topic2dbtable_dict.get(topic)

        # Get instance ID
        _id = self._get_instance_id_HA(topic, op_type, op_id)
        _filter = {"_id": _id}
        db_lcmop = self.db.get_one(db_table_name, _filter, fail_on_empty=False)
        if not db_lcmop:
            return

        # Set DB _filter for querying any related process state
        _filter = self._get_waitfor_filter_HA(db_lcmop, topic, op_type, op_id)

        # For HA, get list of tasks from DB instead of from dictionary (in-memory) variable.
        timeout_wait_for_task = (
            3600  # Max time (seconds) to wait for a related task to finish
        )
        # interval_wait_for_task = 30    #  A too long polling interval slows things down considerably
        interval_wait_for_task = 10  # Interval in seconds for polling related tasks
        time_left = timeout_wait_for_task
        old_num_related_tasks = 0
        while True:
            # Get related tasks (operations within the same instance as this) which are
            # still running (operationState='PROCESSING') and which were started before this task.
            # In the case of op_type='ANY', get any related tasks with operationState='PROCESSING', ignore timestamps.
            db_waitfor_related_task = self.db.get_list(db_table_name, q_filter=_filter)
            new_num_related_tasks = len(db_waitfor_related_task)
            # If there are no related tasks, there is nothing to wait for, so return.
            if not new_num_related_tasks:
                return
            # If number of pending related tasks have changed,
            # update the 'detailed-status' field and log the change.
            # Do NOT update the 'detailed-status' for SDNC-associated-to-VIM operations ('ANY').
            if (op_type != "ANY") and (new_num_related_tasks != old_num_related_tasks):
                step = "Waiting for {} related tasks to be completed.".format(
                    new_num_related_tasks
                )
                self.logger.info("{}".format(step))
                update_dict = {}
                q_filter = {"_id": _id}
                # NS/NSI
                if self._is_service_type_HA(topic):
                    update_dict = {
                        "detailed-status": step,
                        "queuePosition": new_num_related_tasks,
                    }
                # VIM/WIM/SDN
                elif self._is_account_type_HA(topic):
                    _, op_index = self._get_account_and_op_HA(op_id)
                    update_dict = {
                        "_admin.operations.{}.detailed-status".format(op_index): step
                    }
                self.logger.debug("Task {} operation={} {}".format(topic, _id, step))
                self.db.set_one(
                    db_table_name,
                    q_filter=q_filter,
                    update_dict=update_dict,
                    fail_on_empty=False,
                )
                old_num_related_tasks = new_num_related_tasks
            time_left -= interval_wait_for_task
            if time_left < 0:
                raise LcmException(
                    "Timeout ({}) when waiting for related tasks to be completed".format(
                        timeout_wait_for_task
                    )
                )
            await asyncio.sleep(interval_wait_for_task)

        return
