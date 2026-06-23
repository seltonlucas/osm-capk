# -*- coding: utf-8 -*-

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

# import logging
import json
from uuid import uuid4
from http import HTTPStatus
from time import time
from copy import copy, deepcopy
from osm_nbi.validation import (
    validate_input,
    ValidationError,
    ns_instantiate,
    ns_terminate,
    ns_action,
    ns_scale,
    ns_update,
    ns_heal,
    nsi_instantiate,
    ns_migrate,
    nslcmop_cancel,
)
from osm_nbi.base_topic import (
    BaseTopic,
    EngineException,
    get_iterable,
    deep_get,
    increment_ip_mac,
    update_descriptor_usage_state,
)
from yaml import safe_dump
from osm_common.dbbase import DbException
from osm_common.msgbase import MsgException
from osm_common.fsbase import FsException
from osm_nbi import utils
from re import (
    match,
)  # For checking that additional parameter names are valid Jinja2 identifiers

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"


class NsrTopic(BaseTopic):
    topic = "nsrs"
    topic_msg = "ns"
    quota_name = "ns_instances"
    schema_new = ns_instantiate

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["_admin"]["nsState"] = "NOT_INSTANTIATED"
        return None

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that NSR is not instantiated
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: nsr internal id
        :param db_content: The database content of the nsr
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return
        nsr = db_content
        if nsr["_admin"].get("nsState") == "INSTANTIATED":
            raise EngineException(
                "nsr '{}' cannot be deleted because it is in 'INSTANTIATED' state. "
                "Launch 'terminate' operation first; or force deletion".format(_id),
                http_code=HTTPStatus.CONFLICT,
            )

    def delete_extra(self, session, _id, db_content, not_send_msg=None):
        """
        Deletes associated nslcmops and vnfrs from database. Deletes associated filesystem.
         Set usageState of pdu, vnfd, nsd
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param db_content: The database content of the descriptor
        :param not_send_msg: To not send message (False) or store content (list) instead
        :return: None if ok or raises EngineException with the problem
        """
        self.fs.file_delete(_id, ignore_non_exist=True)
        self.db.del_list("nslcmops", {"nsInstanceId": _id})
        self.db.del_list("vnfrs", {"nsr-id-ref": _id})

        # set all used pdus as free
        self.db.set_list(
            "pdus",
            {"_admin.usage.nsr_id": _id},
            {"_admin.usageState": "NOT_IN_USE", "_admin.usage": None},
        )

        # Set NSD usageState
        nsr = db_content
        used_nsd_id = nsr.get("nsd-id")
        if used_nsd_id:
            # check if used by another NSR
            nsrs_list = self.db.get_one(
                "nsrs", {"nsd-id": used_nsd_id}, fail_on_empty=False, fail_on_more=False
            )
            if not nsrs_list:
                self.db.set_one(
                    "nsds", {"_id": used_nsd_id}, {"_admin.usageState": "NOT_IN_USE"}
                )

        # Set NS CONFIG TEMPLATE usageState
        if nsr.get("instantiate_params", {}).get("nsConfigTemplateId"):
            nsconfigtemplate_id = nsr.get("instantiate_params", {}).get(
                "nsConfigTemplateId"
            )
            nsconfigtemplate_list = self.db.get_one(
                "nsrs",
                {"instantiate_params.nsConfigTemplateId": nsconfigtemplate_id},
                fail_on_empty=False,
                fail_on_more=False,
            )
            if not nsconfigtemplate_list:
                self.db.set_one(
                    "ns_config_template",
                    {"_id": nsconfigtemplate_id},
                    {"_admin.usageState": "NOT_IN_USE"},
                )

        # Set VNFD usageState
        used_vnfd_id_list = nsr.get("vnfd-id")
        if used_vnfd_id_list:
            for used_vnfd_id in used_vnfd_id_list:
                # check if used by another NSR
                nsrs_list = self.db.get_one(
                    "nsrs",
                    {"vnfd-id": used_vnfd_id},
                    fail_on_empty=False,
                    fail_on_more=False,
                )
                if not nsrs_list:
                    self.db.set_one(
                        "vnfds",
                        {"_id": used_vnfd_id},
                        {"_admin.usageState": "NOT_IN_USE"},
                    )

        # delete extra ro_nsrs used for internal RO module
        self.db.del_one("ro_nsrs", q_filter={"_id": _id}, fail_on_empty=False)

    @staticmethod
    def _format_ns_request(ns_request):
        formated_request = copy(ns_request)
        formated_request.pop("additionalParamsForNs", None)
        formated_request.pop("additionalParamsForVnf", None)
        return formated_request

    @staticmethod
    def _format_additional_params(
        ns_request, member_vnf_index=None, vdu_id=None, kdu_name=None, descriptor=None
    ):
        """
        Get and format user additional params for NS or VNF.
        The vdu_id and kdu_name params are mutually exclusive! If none of them are given, then the method will
        exclusively search for the VNF/NS LCM additional params.

        :param ns_request: User instantiation additional parameters
        :param member_vnf_index: None for extract NS params, or member_vnf_index to extract VNF params
        :vdu_id: VDU's ID against which we want to format the additional params
        :kdu_name: KDU's name against which we want to format the additional params
        :param descriptor: If not None it check that needed parameters of descriptor are supplied
        :return: tuple with a formatted copy of additional params or None if not supplied, plus other parameters
        """
        additional_params = None
        other_params = None
        if not member_vnf_index:
            additional_params = copy(ns_request.get("additionalParamsForNs"))
            where_ = "additionalParamsForNs"
        elif ns_request.get("additionalParamsForVnf"):
            where_ = "additionalParamsForVnf[member-vnf-index={}]".format(
                member_vnf_index
            )
            item = next(
                (
                    x
                    for x in ns_request["additionalParamsForVnf"]
                    if x["member-vnf-index"] == member_vnf_index
                ),
                None,
            )
            if item:
                if not vdu_id and not kdu_name:
                    other_params = item
                additional_params = copy(item.get("additionalParams")) or {}
                if vdu_id and item.get("additionalParamsForVdu"):
                    item_vdu = next(
                        (
                            x
                            for x in item["additionalParamsForVdu"]
                            if x["vdu_id"] == vdu_id
                        ),
                        None,
                    )
                    other_params = item_vdu
                    if item_vdu and item_vdu.get("additionalParams"):
                        where_ += ".additionalParamsForVdu[vdu_id={}]".format(vdu_id)
                        additional_params = item_vdu["additionalParams"]
                if kdu_name:
                    additional_params = {}
                    if item.get("additionalParamsForKdu"):
                        item_kdu = next(
                            (
                                x
                                for x in item["additionalParamsForKdu"]
                                if x["kdu_name"] == kdu_name
                            ),
                            None,
                        )
                        other_params = item_kdu
                        if item_kdu and item_kdu.get("additionalParams"):
                            where_ += ".additionalParamsForKdu[kdu_name={}]".format(
                                kdu_name
                            )
                            additional_params = item_kdu["additionalParams"]

        if additional_params:
            for k, v in additional_params.items():
                # BEGIN Check that additional parameter names are valid Jinja2 identifiers if target is not Kdu
                if not kdu_name and not match("^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                    raise EngineException(
                        "Invalid param name at {}:{}. Must contain only alphanumeric characters "
                        "and underscores, and cannot start with a digit".format(
                            where_, k
                        )
                    )
                # END Check that additional parameter names are valid Jinja2 identifiers
                if not isinstance(k, str):
                    raise EngineException(
                        "Invalid param at {}:{}. Only string keys are allowed".format(
                            where_, k
                        )
                    )
                if "$" in k:
                    raise EngineException(
                        "Invalid param at {}:{}. Keys must not contain $ symbol".format(
                            where_, k
                        )
                    )
                if isinstance(v, (dict, tuple, list)):
                    additional_params[k] = "!!yaml " + safe_dump(v)
            if kdu_name:
                additional_params = json.dumps(additional_params)

        # Select the VDU ID, KDU name or NS/VNF ID, depending on the method's call intent
        selector = vdu_id if vdu_id else kdu_name if kdu_name else descriptor.get("id")

        if descriptor:
            for df in descriptor.get("df", []):
                # check that enough parameters are supplied for the initial-config-primitive
                # TODO: check for cloud-init
                if member_vnf_index:
                    initial_primitives = []
                    if (
                        "lcm-operations-configuration" in df
                        and "operate-vnf-op-config"
                        in df["lcm-operations-configuration"]
                    ):
                        for config in df["lcm-operations-configuration"][
                            "operate-vnf-op-config"
                        ].get("day1-2", []):
                            # Verify the target object (VNF|NS|VDU|KDU) where we need to populate
                            # the params with the additional ones given by the user
                            if config.get("id") == selector:
                                for primitive in get_iterable(
                                    config.get("initial-config-primitive")
                                ):
                                    initial_primitives.append(primitive)
                else:
                    initial_primitives = deep_get(
                        descriptor, ("ns-configuration", "initial-config-primitive")
                    )

                for initial_primitive in get_iterable(initial_primitives):
                    for param in get_iterable(initial_primitive.get("parameter")):
                        if param["value"].startswith("<") and param["value"].endswith(
                            ">"
                        ):
                            if param["value"] in (
                                "<rw_mgmt_ip>",
                                "<VDU_SCALE_INFO>",
                                "<ns_config_info>",
                                "<OSM>",
                            ):
                                continue
                            if (
                                not additional_params
                                or param["value"][1:-1] not in additional_params
                            ):
                                raise EngineException(
                                    "Parameter '{}' needed for vnfd[id={}]:day1-2 configuration:"
                                    "initial-config-primitive[name={}] not supplied".format(
                                        param["value"],
                                        descriptor["id"],
                                        initial_primitive["name"],
                                    )
                                )

        return additional_params or None, other_params or None

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates a new nsr into database. It also creates needed vnfrs
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the nsr
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: the _id of nsr descriptor created at database. Or an exception of type
            EngineException, ValidationError, DbException, FsException, MsgException.
            Note: Exceptions are not captured on purpose. They should be captured at called
        """
        step = "checking quotas"  # first step must be defined outside try
        try:
            self.check_quota(session)

            step = "validating input parameters"
            ns_request = self._remove_envelop(indata)
            self._update_input_with_kwargs(ns_request, kwargs)
            ns_request = self._validate_input_new(ns_request, session["force"])

            step = "getting nsd id='{}' from database".format(ns_request.get("nsdId"))
            nsd = self._get_nsd_from_db(ns_request["nsdId"], session)
            ns_k8s_namespace = self._get_ns_k8s_namespace(nsd, ns_request, session)

            # Uploading the instantiation parameters to ns_request from ns config template
            if ns_request.get("nsConfigTemplateId"):
                step = "getting ns_config_template is='{}' from database".format(
                    ns_request.get("nsConfigTemplateId")
                )
                ns_config_template_db = self._get_nsConfigTemplate_from_db(
                    ns_request.get("nsConfigTemplateId"), session
                )
                ns_config_params = ns_config_template_db.get("config")
                for key, value in ns_config_params.items():
                    if key == "vnf":
                        ns_request["vnf"] = ns_config_params.get("vnf")
                    elif key == "additionalParamsForVnf":
                        ns_request["additionalParamsForVnf"] = ns_config_params.get(
                            "additionalParamsForVnf"
                        )
                    elif key == "additionalParamsForNs":
                        ns_request["additionalParamsForNs"] = ns_config_params.get(
                            "additionalParamsForNs"
                        )
                    elif key == "vld":
                        ns_request["vld"] = ns_config_params.get("vld")
                step = "checking ns_config_templateOperationalState"
                self._check_ns_config_template_operational_state(
                    ns_config_template_db, ns_request
                )

                step = "Updating NSCONFIG TEMPLATE usageState"
                update_descriptor_usage_state(
                    ns_config_template_db, "ns_config_template", self.db
                )

            elif ns_request.get("vnf"):
                vnf_data = ns_request.get("vnf")
                for vnf in vnf_data:
                    for vdu in vnf.get("vdu", []):
                        if vdu.get("vim-flavor-name") and vdu.get("vim-flavor-id"):
                            raise EngineException(
                                "Instantiation parameters vim-flavor-name and vim-flavor-id are mutually exclusive"
                            )

            step = "checking nsdOperationalState"
            self._check_nsd_operational_state(nsd, ns_request)

            step = "filling nsr from input data"
            nsr_id = str(uuid4())
            nsr_descriptor = self._create_nsr_descriptor_from_nsd(
                nsd, ns_request, nsr_id, session
            )

            # Create VNFRs
            needed_vnfds = {}
            # TODO: Change for multiple df support
            vnf_profiles = nsd.get("df", [{}])[0].get("vnf-profile", ())
            for vnfp in vnf_profiles:
                vnfd_id = vnfp.get("vnfd-id")
                vnf_index = vnfp.get("id")
                step = (
                    "getting vnfd id='{}' constituent-vnfd='{}' from database".format(
                        vnfd_id, vnf_index
                    )
                )
                if vnfd_id not in needed_vnfds:
                    vnfd = self._get_vnfd_from_db(vnfd_id, session)
                    if "revision" in vnfd["_admin"]:
                        vnfd["revision"] = vnfd["_admin"]["revision"]
                    vnfd.pop("_admin")
                    needed_vnfds[vnfd_id] = vnfd
                    nsr_descriptor["vnfd-id"].append(vnfd["_id"])
                else:
                    vnfd = needed_vnfds[vnfd_id]

                step = "filling vnfr  vnfd-id='{}' constituent-vnfd='{}'".format(
                    vnfd_id, vnf_index
                )
                vnfr_descriptor = self._create_vnfr_descriptor_from_vnfd(
                    nsd,
                    vnfd,
                    vnfd_id,
                    vnf_index,
                    nsr_descriptor,
                    ns_request,
                    ns_k8s_namespace,
                )

                step = "creating vnfr vnfd-id='{}' constituent-vnfd='{}' at database".format(
                    vnfd_id, vnf_index
                )
                self._add_vnfr_to_db(vnfr_descriptor, rollback, session)
                nsr_descriptor["constituent-vnfr-ref"].append(vnfr_descriptor["id"])
                step = "Updating VNFD usageState"
                update_descriptor_usage_state(vnfd, "vnfds", self.db)

            step = "creating nsr at database"
            self._add_nsr_to_db(nsr_descriptor, rollback, session)
            step = "Updating NSD usageState"
            update_descriptor_usage_state(nsd, "nsds", self.db)

            step = "creating nsr temporal folder"
            self.fs.mkdir(nsr_id)

            return nsr_id, None
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _get_nsd_from_db(self, nsd_id, session):
        _filter = self._get_project_filter(session)
        _filter["_id"] = nsd_id
        return self.db.get_one("nsds", _filter)

    def _get_nsConfigTemplate_from_db(self, nsConfigTemplate_id, session):
        _filter = self._get_project_filter(session)
        _filter["_id"] = nsConfigTemplate_id
        ns_config_template_db = self.db.get_one(
            "ns_config_template", _filter, fail_on_empty=False
        )
        return ns_config_template_db

    def _get_vnfd_from_db(self, vnfd_id, session):
        _filter = self._get_project_filter(session)
        _filter["id"] = vnfd_id
        vnfd = self.db.get_one("vnfds", _filter, fail_on_empty=True, fail_on_more=True)
        return vnfd

    def _add_nsr_to_db(self, nsr_descriptor, rollback, session):
        self.format_on_new(
            nsr_descriptor, session["project_id"], make_public=session["public"]
        )
        self.db.create("nsrs", nsr_descriptor)
        rollback.append({"topic": "nsrs", "_id": nsr_descriptor["id"]})

    def _add_vnfr_to_db(self, vnfr_descriptor, rollback, session):
        self.format_on_new(
            vnfr_descriptor, session["project_id"], make_public=session["public"]
        )
        self.db.create("vnfrs", vnfr_descriptor)
        rollback.append({"topic": "vnfrs", "_id": vnfr_descriptor["id"]})

    def _check_nsd_operational_state(self, nsd, ns_request):
        if nsd["_admin"]["operationalState"] == "DISABLED":
            raise EngineException(
                "nsd with id '{}' is DISABLED, and thus cannot be used to create "
                "a network service".format(ns_request["nsdId"]),
                http_code=HTTPStatus.CONFLICT,
            )

    def _check_ns_config_template_operational_state(
        self, ns_config_template_db, ns_request
    ):
        if ns_config_template_db["_admin"]["operationalState"] == "DISABLED":
            raise EngineException(
                "ns_config_template with id '{}' is DISABLED, and thus cannot be used to create "
                "a network service".format(ns_request["nsConfigTemplateId"]),
                http_code=HTTPStatus.CONFLICT,
            )

    def _get_ns_k8s_namespace(self, nsd, ns_request, session):
        additional_params, _ = self._format_additional_params(
            ns_request, descriptor=nsd
        )
        # use for k8s-namespace from ns_request or additionalParamsForNs. By default, the project_id
        ns_k8s_namespace = session["project_id"][0] if session["project_id"] else None
        if ns_request and ns_request.get("k8s-namespace"):
            ns_k8s_namespace = ns_request["k8s-namespace"]
        if additional_params and additional_params.get("k8s-namespace"):
            ns_k8s_namespace = additional_params["k8s-namespace"]

        return ns_k8s_namespace

    def _add_shared_volumes_to_nsr(
        self, vdu, vnfd, nsr_descriptor, member_vnf_index, revision=None
    ):
        svsd = []
        for vsd in vnfd.get("virtual-storage-desc", ()):
            if vsd.get("vdu-storage-requirements"):
                if (
                    vsd.get("vdu-storage-requirements")[0].get("key") == "multiattach"
                    and vsd.get("vdu-storage-requirements")[0].get("value") == "True"
                ):
                    # Avoid setting the volume name multiple times
                    if not match(f"shared-.*-{vnfd['id']}", vsd["id"]):
                        vsd["id"] = f"shared-{vsd['id']}-{vnfd['id']}"
                    svsd.append(vsd)
        if svsd:
            nsr_descriptor["shared-volumes"] = svsd

    def _add_flavor_to_nsr(
        self, vdu, vnfd, nsr_descriptor, member_vnf_index, revision=None
    ):
        flavor_data = {}
        guest_epa = {}
        # Find this vdu compute and storage descriptors
        vdu_virtual_compute = {}
        vdu_virtual_storage = {}
        for vcd in vnfd.get("virtual-compute-desc", ()):
            if vcd.get("id") == vdu.get("virtual-compute-desc"):
                vdu_virtual_compute = vcd
        for vsd in vnfd.get("virtual-storage-desc", ()):
            if vsd.get("id") == vdu.get("virtual-storage-desc", [[]])[0]:
                vdu_virtual_storage = vsd
        # Get this vdu vcpus, memory and storage info for flavor_data
        if vdu_virtual_compute.get("virtual-cpu", {}).get("num-virtual-cpu"):
            flavor_data["vcpu-count"] = vdu_virtual_compute["virtual-cpu"][
                "num-virtual-cpu"
            ]
        if vdu_virtual_compute.get("virtual-memory", {}).get("size"):
            flavor_data["memory-mb"] = (
                float(vdu_virtual_compute["virtual-memory"]["size"]) * 1024.0
            )
        if vdu_virtual_storage.get("size-of-storage"):
            flavor_data["storage-gb"] = vdu_virtual_storage["size-of-storage"]
        # Get this vdu EPA info for guest_epa
        if vdu_virtual_compute.get("virtual-cpu", {}).get("cpu-quota"):
            guest_epa["cpu-quota"] = vdu_virtual_compute["virtual-cpu"]["cpu-quota"]
        if vdu_virtual_compute.get("virtual-cpu", {}).get("pinning"):
            vcpu_pinning = vdu_virtual_compute["virtual-cpu"]["pinning"]
            if vcpu_pinning.get("thread-policy"):
                guest_epa["cpu-thread-pinning-policy"] = vcpu_pinning["thread-policy"]
            if vcpu_pinning.get("policy"):
                cpu_policy = (
                    "SHARED" if vcpu_pinning["policy"] == "dynamic" else "DEDICATED"
                )
                guest_epa["cpu-pinning-policy"] = cpu_policy
        if vdu_virtual_compute.get("virtual-memory", {}).get("mem-quota"):
            guest_epa["mem-quota"] = vdu_virtual_compute["virtual-memory"]["mem-quota"]
        if vdu_virtual_compute.get("virtual-memory", {}).get("mempage-size"):
            guest_epa["mempage-size"] = vdu_virtual_compute["virtual-memory"][
                "mempage-size"
            ]
        if vdu_virtual_compute.get("virtual-memory", {}).get("numa-node-policy"):
            guest_epa["numa-node-policy"] = vdu_virtual_compute["virtual-memory"][
                "numa-node-policy"
            ]
        if vdu_virtual_storage.get("disk-io-quota"):
            guest_epa["disk-io-quota"] = vdu_virtual_storage["disk-io-quota"]

        if guest_epa:
            flavor_data["guest-epa"] = guest_epa

        revision = revision if revision is not None else 1
        flavor_data["name"] = (
            vdu["id"][:56] + "-" + member_vnf_index + "-" + str(revision) + "-flv"
        )
        flavor_data["id"] = str(len(nsr_descriptor["flavor"]))
        nsr_descriptor["flavor"].append(flavor_data)

    def _create_nsr_descriptor_from_nsd(self, nsd, ns_request, nsr_id, session):
        now = time()
        additional_params, _ = self._format_additional_params(
            ns_request, descriptor=nsd
        )

        nsr_descriptor = {
            "name": ns_request["nsName"],
            "name-ref": ns_request["nsName"],
            "short-name": ns_request["nsName"],
            "admin-status": "ENABLED",
            "nsState": "NOT_INSTANTIATED",
            "currentOperation": "IDLE",
            "currentOperationID": None,
            "errorDescription": None,
            "errorDetail": None,
            "deploymentStatus": None,
            "configurationStatus": None,
            "vcaStatus": None,
            "nsd": {k: v for k, v in nsd.items()},
            "datacenter": ns_request["vimAccountId"],
            "resource-orchestrator": "osmopenmano",
            "description": ns_request.get("nsDescription", ""),
            "constituent-vnfr-ref": [],
            "operational-status": "init",  # typedef ns-operational-
            "config-status": "init",  # typedef config-states
            "detailed-status": "scheduled",
            "orchestration-progress": {},
            "create-time": now,
            "nsd-name-ref": nsd["name"],
            "operational-events": [],  # "id", "timestamp", "description", "event",
            "nsd-ref": nsd["id"],
            "nsd-id": nsd["_id"],
            "vnfd-id": [],
            "instantiate_params": self._format_ns_request(ns_request),
            "additionalParamsForNs": additional_params,
            "ns-instance-config-ref": nsr_id,
            "id": nsr_id,
            "_id": nsr_id,
            "ssh-authorized-key": ns_request.get("ssh_keys"),  # TODO remove
            "flavor": [],
            "image": [],
            "affinity-or-anti-affinity-group": [],
            "shared-volumes": [],
            "vnffgd": [],
        }
        if "revision" in nsd["_admin"]:
            nsr_descriptor["revision"] = nsd["_admin"]["revision"]

        ns_request["nsr_id"] = nsr_id
        if ns_request and ns_request.get("config-units"):
            nsr_descriptor["config-units"] = ns_request["config-units"]
        # Create vld
        if nsd.get("virtual-link-desc"):
            nsr_vld = deepcopy(nsd.get("virtual-link-desc", []))
            # Fill each vld with vnfd-connection-point-ref data
            # TODO: Change for multiple df support
            all_vld_connection_point_data = {vld.get("id"): [] for vld in nsr_vld}
            vnf_profiles = nsd.get("df", [[]])[0].get("vnf-profile", ())
            for vnf_profile in vnf_profiles:
                for vlc in vnf_profile.get("virtual-link-connectivity", ()):
                    for cpd in vlc.get("constituent-cpd-id", ()):
                        all_vld_connection_point_data[
                            vlc.get("virtual-link-profile-id")
                        ].append(
                            {
                                "member-vnf-index-ref": cpd.get(
                                    "constituent-base-element-id"
                                ),
                                "vnfd-connection-point-ref": cpd.get(
                                    "constituent-cpd-id"
                                ),
                                "vnfd-id-ref": vnf_profile.get("vnfd-id"),
                            }
                        )

                vnfd = self._get_vnfd_from_db(vnf_profile.get("vnfd-id"), session)
                vnfd.pop("_admin")

                for vdu in vnfd.get("vdu", ()):
                    member_vnf_index = vnf_profile.get("id")
                    self._add_flavor_to_nsr(vdu, vnfd, nsr_descriptor, member_vnf_index)
                    self._add_shared_volumes_to_nsr(
                        vdu, vnfd, nsr_descriptor, member_vnf_index
                    )
                    sw_image_id = vdu.get("sw-image-desc")
                    if sw_image_id:
                        image_data = self._get_image_data_from_vnfd(vnfd, sw_image_id)
                        self._add_image_to_nsr(nsr_descriptor, image_data)

                    # also add alternative images to the list of images
                    for alt_image in vdu.get("alternative-sw-image-desc", ()):
                        image_data = self._get_image_data_from_vnfd(vnfd, alt_image)
                        self._add_image_to_nsr(nsr_descriptor, image_data)

                # Add Affinity or Anti-affinity group information to NSR
                vdu_profiles = vnfd.get("df", [[]])[0].get("vdu-profile", ())
                affinity_group_prefix_name = "{}-{}".format(
                    nsr_descriptor["name"][:16], vnf_profile.get("id")[:16]
                )

                for vdu_profile in vdu_profiles:
                    affinity_group_data = {}
                    for affinity_group in vdu_profile.get(
                        "affinity-or-anti-affinity-group", ()
                    ):
                        affinity_group_data = (
                            self._get_affinity_or_anti_affinity_group_data_from_vnfd(
                                vnfd, affinity_group["id"]
                            )
                        )
                        affinity_group_data["member-vnf-index"] = vnf_profile.get("id")
                        self._add_affinity_or_anti_affinity_group_to_nsr(
                            nsr_descriptor,
                            affinity_group_data,
                            affinity_group_prefix_name,
                        )

            for vld in nsr_vld:
                vld["vnfd-connection-point-ref"] = all_vld_connection_point_data.get(
                    vld.get("id"), []
                )
                vld["name"] = vld["id"]
            nsr_descriptor["vld"] = nsr_vld
        if nsd.get("vnffgd"):
            vnffgd = nsd.get("vnffgd")
            for vnffg in vnffgd:
                info = {}
                for k, v in vnffg.items():
                    if k == "id":
                        info.update({k: v})
                    if k == "nfpd":
                        info.update({k: v})
                nsr_descriptor["vnffgd"].append(info)

        return nsr_descriptor

    def _get_affinity_or_anti_affinity_group_data_from_vnfd(
        self, vnfd, affinity_group_id
    ):
        """
        Gets affinity-or-anti-affinity-group info from df and returns the desired affinity group
        """
        affinity_group = utils.find_in_list(
            vnfd.get("df", [[]])[0].get("affinity-or-anti-affinity-group", ()),
            lambda ag: ag["id"] == affinity_group_id,
        )
        affinity_group_data = {}
        if affinity_group:
            if affinity_group.get("id"):
                affinity_group_data["ag-id"] = affinity_group["id"]
            if affinity_group.get("type"):
                affinity_group_data["type"] = affinity_group["type"]
            if affinity_group.get("scope"):
                affinity_group_data["scope"] = affinity_group["scope"]
        return affinity_group_data

    def _add_affinity_or_anti_affinity_group_to_nsr(
        self, nsr_descriptor, affinity_group_data, affinity_group_prefix_name
    ):
        """
        Adds affinity-or-anti-affinity-group to nsr checking first it is not already added
        """
        affinity_group = next(
            (
                f
                for f in nsr_descriptor["affinity-or-anti-affinity-group"]
                if all(f.get(k) == affinity_group_data[k] for k in affinity_group_data)
            ),
            None,
        )
        if not affinity_group:
            affinity_group_data["id"] = str(
                len(nsr_descriptor["affinity-or-anti-affinity-group"])
            )
            affinity_group_data["name"] = "{}-{}".format(
                affinity_group_prefix_name, affinity_group_data["ag-id"][:32]
            )
            nsr_descriptor["affinity-or-anti-affinity-group"].append(
                affinity_group_data
            )

    def _get_image_data_from_vnfd(self, vnfd, sw_image_id):
        sw_image_desc = utils.find_in_list(
            vnfd.get("sw-image-desc", ()), lambda sw: sw["id"] == sw_image_id
        )
        image_data = {}
        if sw_image_desc.get("image"):
            image_data["image"] = sw_image_desc["image"]
        if sw_image_desc.get("checksum"):
            image_data["image_checksum"] = sw_image_desc["checksum"]["hash"]
        if sw_image_desc.get("vim-type"):
            image_data["vim-type"] = sw_image_desc["vim-type"]
        return image_data

    def _add_image_to_nsr(self, nsr_descriptor, image_data):
        """
        Adds image to nsr checking first it is not already added
        """
        img = next(
            (
                f
                for f in nsr_descriptor["image"]
                if all(f.get(k) == image_data[k] for k in image_data)
            ),
            None,
        )
        if not img:
            image_data["id"] = str(len(nsr_descriptor["image"]))
            nsr_descriptor["image"].append(image_data)

    def _create_vnfr_descriptor_from_vnfd(
        self,
        nsd,
        vnfd,
        vnfd_id,
        vnf_index,
        nsr_descriptor,
        ns_request,
        ns_k8s_namespace,
        revision=None,
    ):
        vnfr_id = str(uuid4())
        nsr_id = nsr_descriptor["id"]
        now = time()
        additional_params, vnf_params = self._format_additional_params(
            ns_request, vnf_index, descriptor=vnfd
        )

        vnfr_descriptor = {
            "id": vnfr_id,
            "_id": vnfr_id,
            "nsr-id-ref": nsr_id,
            "member-vnf-index-ref": vnf_index,
            "additionalParamsForVnf": additional_params,
            "created-time": now,
            # "vnfd": vnfd,        # at OSM model.but removed to avoid data duplication TODO: revise
            "vnfd-ref": vnfd_id,
            "vnfd-id": vnfd["_id"],  # not at OSM model, but useful
            "vim-account-id": None,
            "vca-id": None,
            "vdur": [],
            "connection-point": [],
            "ip-address": None,  # mgmt-interface filled by LCM
        }

        # Revision backwards compatility.  Only specify the revision in the record if
        # the original VNFD has a revision.
        if "revision" in vnfd:
            vnfr_descriptor["revision"] = vnfd["revision"]

        vnf_k8s_namespace = ns_k8s_namespace
        if vnf_params:
            if vnf_params.get("k8s-namespace"):
                vnf_k8s_namespace = vnf_params["k8s-namespace"]
            if vnf_params.get("config-units"):
                vnfr_descriptor["config-units"] = vnf_params["config-units"]

        # Create vld
        if vnfd.get("int-virtual-link-desc"):
            vnfr_descriptor["vld"] = []
            for vnfd_vld in vnfd.get("int-virtual-link-desc"):
                vnfr_descriptor["vld"].append({key: vnfd_vld[key] for key in vnfd_vld})

        for cp in vnfd.get("ext-cpd", ()):
            vnf_cp = {
                "name": cp.get("id"),
                "connection-point-id": cp.get("int-cpd", {}).get("cpd"),
                "connection-point-vdu-id": cp.get("int-cpd", {}).get("vdu-id"),
                "id": cp.get("id"),
                # "ip-address", "mac-address" # filled by LCM
                # vim-id  # TODO it would be nice having a vim port id
            }
            vnfr_descriptor["connection-point"].append(vnf_cp)

        # Create k8s-cluster information
        # TODO: Validate if a k8s-cluster net can have more than one ext-cpd ?
        if vnfd.get("k8s-cluster"):
            vnfr_descriptor["k8s-cluster"] = vnfd["k8s-cluster"]
            all_k8s_cluster_nets_cpds = {}
            for cpd in get_iterable(vnfd.get("ext-cpd")):
                if cpd.get("k8s-cluster-net"):
                    all_k8s_cluster_nets_cpds[cpd.get("k8s-cluster-net")] = cpd.get(
                        "id"
                    )
            for net in get_iterable(vnfr_descriptor["k8s-cluster"].get("nets")):
                if net.get("id") in all_k8s_cluster_nets_cpds:
                    net["external-connection-point-ref"] = all_k8s_cluster_nets_cpds[
                        net.get("id")
                    ]

        # update kdus
        for kdu in get_iterable(vnfd.get("kdu")):
            additional_params, kdu_params = self._format_additional_params(
                ns_request, vnf_index, kdu_name=kdu["name"], descriptor=vnfd
            )
            kdu_k8s_namespace = vnf_k8s_namespace
            kdu_model = kdu_params.get("kdu_model") if kdu_params else None
            if kdu_params and kdu_params.get("k8s-namespace"):
                kdu_k8s_namespace = kdu_params["k8s-namespace"]

            kdu_deployment_name = ""
            if kdu_params and kdu_params.get("kdu-deployment-name"):
                kdu_deployment_name = kdu_params.get("kdu-deployment-name")

            kdur = {
                "additionalParams": additional_params,
                "k8s-namespace": kdu_k8s_namespace,
                "kdu-deployment-name": kdu_deployment_name,
                "kdu-name": kdu["name"],
                # TODO      "name": ""     Name of the VDU in the VIM
                "ip-address": None,  # mgmt-interface filled by LCM
                "k8s-cluster": {},
            }
            if kdu_params and kdu_params.get("config-units"):
                kdur["config-units"] = kdu_params["config-units"]
            if kdu.get("helm-version"):
                kdur["helm-version"] = kdu["helm-version"]
            for k8s_type in ("helm-chart", "juju-bundle"):
                if kdu.get(k8s_type):
                    kdur[k8s_type] = kdu_model or kdu[k8s_type]
            if not vnfr_descriptor.get("kdur"):
                vnfr_descriptor["kdur"] = []
            vnfr_descriptor["kdur"].append(kdur)

        vnfd_mgmt_cp = vnfd.get("mgmt-cp")

        for vdu in vnfd.get("vdu", ()):
            vdu_mgmt_cp = []
            try:
                configs = vnfd.get("df")[0]["lcm-operations-configuration"][
                    "operate-vnf-op-config"
                ]["day1-2"]
                vdu_config = utils.find_in_list(
                    configs, lambda config: config["id"] == vdu["id"]
                )
            except Exception:
                vdu_config = None

            try:
                vdu_instantiation_level = utils.find_in_list(
                    vnfd.get("df")[0]["instantiation-level"][0]["vdu-level"],
                    lambda a_vdu_profile: a_vdu_profile["vdu-id"] == vdu["id"],
                )
            except Exception:
                vdu_instantiation_level = None

            if vdu_config:
                external_connection_ee = utils.filter_in_list(
                    vdu_config.get("execution-environment-list", []),
                    lambda ee: "external-connection-point-ref" in ee,
                )
                for ee in external_connection_ee:
                    vdu_mgmt_cp.append(ee["external-connection-point-ref"])

            additional_params, vdu_params = self._format_additional_params(
                ns_request, vnf_index, vdu_id=vdu["id"], descriptor=vnfd
            )

            try:
                vdu_virtual_storage_descriptors = utils.filter_in_list(
                    vnfd.get("virtual-storage-desc", []),
                    lambda stg_desc: stg_desc["id"] in vdu["virtual-storage-desc"],
                )
            except Exception:
                vdu_virtual_storage_descriptors = []
            vdur = {
                "vdu-id-ref": vdu["id"],
                # TODO      "name": ""     Name of the VDU in the VIM
                "ip-address": None,  # mgmt-interface filled by LCM
                # "vim-id", "flavor-id", "image-id", "management-ip" # filled by LCM
                "internal-connection-point": [],
                "interfaces": [],
                "additionalParams": additional_params,
                "vdu-name": vdu["name"],
                "virtual-storages": vdu_virtual_storage_descriptors,
            }
            if vdu_params and vdu_params.get("config-units"):
                vdur["config-units"] = vdu_params["config-units"]
            if deep_get(vdu, ("supplemental-boot-data", "boot-data-drive")):
                vdur["boot-data-drive"] = vdu["supplemental-boot-data"][
                    "boot-data-drive"
                ]
            if vdu.get("pdu-type"):
                vdur["pdu-type"] = vdu["pdu-type"]
                vdur["name"] = vdu["pdu-type"]
            # TODO volumes: name, volume-id
            for icp in vdu.get("int-cpd", ()):
                vdu_icp = {
                    "id": icp["id"],
                    "connection-point-id": icp["id"],
                    "name": icp.get("id"),
                }

                vdur["internal-connection-point"].append(vdu_icp)

                for iface in icp.get("virtual-network-interface-requirement", ()):
                    # Name, mac-address and interface position is taken from VNFD
                    # and included into VNFR. By this way RO can process this information
                    # while creating the VDU.
                    iface_fields = ("name", "mac-address", "position", "ip-address")
                    vdu_iface = {
                        x: iface[x] for x in iface_fields if iface.get(x) is not None
                    }

                    vdu_iface["internal-connection-point-ref"] = vdu_icp["id"]
                    if "port-security-enabled" in icp:
                        vdu_iface["port-security-enabled"] = icp[
                            "port-security-enabled"
                        ]

                    if "port-security-disable-strategy" in icp:
                        vdu_iface["port-security-disable-strategy"] = icp[
                            "port-security-disable-strategy"
                        ]

                    for ext_cp in vnfd.get("ext-cpd", ()):
                        if not ext_cp.get("int-cpd"):
                            continue
                        if ext_cp["int-cpd"].get("vdu-id") != vdu["id"]:
                            continue
                        if icp["id"] == ext_cp["int-cpd"].get("cpd"):
                            vdu_iface["external-connection-point-ref"] = ext_cp.get(
                                "id"
                            )

                            if "port-security-enabled" in ext_cp:
                                vdu_iface["port-security-enabled"] = ext_cp[
                                    "port-security-enabled"
                                ]

                            if "port-security-disable-strategy" in ext_cp:
                                vdu_iface["port-security-disable-strategy"] = ext_cp[
                                    "port-security-disable-strategy"
                                ]

                            break

                    if (
                        vnfd_mgmt_cp
                        and vdu_iface.get("external-connection-point-ref")
                        == vnfd_mgmt_cp
                    ):
                        vdu_iface["mgmt-vnf"] = True
                        vdu_iface["mgmt-interface"] = True

                    for ecp in vdu_mgmt_cp:
                        if vdu_iface.get("external-connection-point-ref") == ecp:
                            vdu_iface["mgmt-interface"] = True

                    if iface.get("virtual-interface"):
                        vdu_iface.update(deepcopy(iface["virtual-interface"]))

                    # look for network where this interface is connected
                    iface_ext_cp = vdu_iface.get("external-connection-point-ref")
                    if iface_ext_cp:
                        # TODO: Change for multiple df support
                        for df in get_iterable(nsd.get("df")):
                            for vnf_profile in get_iterable(df.get("vnf-profile")):
                                for vlc_index, vlc in enumerate(
                                    get_iterable(
                                        vnf_profile.get("virtual-link-connectivity")
                                    )
                                ):
                                    for cpd in get_iterable(
                                        vlc.get("constituent-cpd-id")
                                    ):
                                        if (
                                            cpd.get("constituent-cpd-id")
                                            == iface_ext_cp
                                        ) and vnf_profile.get("id") == vnf_index:
                                            vdu_iface["ns-vld-id"] = vlc.get(
                                                "virtual-link-profile-id"
                                            )
                                            # if iface type is SRIOV or PASSTHROUGH, set pci-interfaces flag to True
                                            if vdu_iface.get("type") in (
                                                "SR-IOV",
                                                "PCI-PASSTHROUGH",
                                            ):
                                                nsr_descriptor["vld"][vlc_index][
                                                    "pci-interfaces"
                                                ] = True
                                            break
                    elif vdu_iface.get("internal-connection-point-ref"):
                        vdu_iface["vnf-vld-id"] = icp.get("int-virtual-link-desc")
                        # TODO: store fixed IP address in the record (if it exists in the ICP)
                        # if iface type is SRIOV or PASSTHROUGH, set pci-interfaces flag to True
                        if vdu_iface.get("type") in ("SR-IOV", "PCI-PASSTHROUGH"):
                            ivld_index = utils.find_index_in_list(
                                vnfd.get("int-virtual-link-desc", ()),
                                lambda ivld: ivld["id"]
                                == icp.get("int-virtual-link-desc"),
                            )
                            vnfr_descriptor["vld"][ivld_index]["pci-interfaces"] = True

                    vdur["interfaces"].append(vdu_iface)

            if vdu.get("sw-image-desc"):
                sw_image = utils.find_in_list(
                    vnfd.get("sw-image-desc", ()),
                    lambda image: image["id"] == vdu.get("sw-image-desc"),
                )
                nsr_sw_image_data = utils.find_in_list(
                    nsr_descriptor["image"],
                    lambda nsr_image: (nsr_image.get("image") == sw_image.get("image")),
                )
                vdur["ns-image-id"] = nsr_sw_image_data["id"]

            if vdu.get("alternative-sw-image-desc"):
                alt_image_ids = []
                for alt_image_id in vdu.get("alternative-sw-image-desc", ()):
                    sw_image = utils.find_in_list(
                        vnfd.get("sw-image-desc", ()),
                        lambda image: image["id"] == alt_image_id,
                    )
                    nsr_sw_image_data = utils.find_in_list(
                        nsr_descriptor["image"],
                        lambda nsr_image: (
                            nsr_image.get("image") == sw_image.get("image")
                        ),
                    )
                    alt_image_ids.append(nsr_sw_image_data["id"])
                vdur["alt-image-ids"] = alt_image_ids

            revision = revision if revision is not None else 1
            flavor_data_name = (
                vdu["id"][:56] + "-" + vnf_index + "-" + str(revision) + "-flv"
            )
            nsr_flavor_desc = utils.find_in_list(
                nsr_descriptor["flavor"],
                lambda flavor: flavor["name"] == flavor_data_name,
            )

            if nsr_flavor_desc:
                vdur["ns-flavor-id"] = nsr_flavor_desc["id"]

            # Adding Shared Volume information to vdur
            if vdur.get("virtual-storages"):
                nsr_sv = []
                for vsd in vdur["virtual-storages"]:
                    if vsd.get("vdu-storage-requirements"):
                        if (
                            vsd["vdu-storage-requirements"][0].get("key")
                            == "multiattach"
                            and vsd["vdu-storage-requirements"][0].get("value")
                            == "True"
                        ):
                            nsr_sv.append(vsd["id"])
                if nsr_sv:
                    vdur["shared-volumes-id"] = nsr_sv

            # Adding Affinity groups information to vdur
            try:
                vdu_profile_affinity_group = utils.find_in_list(
                    vnfd.get("df")[0]["vdu-profile"],
                    lambda a_vdu: a_vdu["id"] == vdu["id"],
                )
            except Exception:
                vdu_profile_affinity_group = None

            if vdu_profile_affinity_group:
                affinity_group_ids = []
                for affinity_group in vdu_profile_affinity_group.get(
                    "affinity-or-anti-affinity-group", ()
                ):
                    vdu_affinity_group = utils.find_in_list(
                        vdu_profile_affinity_group.get(
                            "affinity-or-anti-affinity-group", ()
                        ),
                        lambda ag_fp: ag_fp["id"] == affinity_group["id"],
                    )
                    nsr_affinity_group = utils.find_in_list(
                        nsr_descriptor["affinity-or-anti-affinity-group"],
                        lambda nsr_ag: (
                            nsr_ag.get("ag-id") == vdu_affinity_group.get("id")
                            and nsr_ag.get("member-vnf-index")
                            == vnfr_descriptor.get("member-vnf-index-ref")
                        ),
                    )
                    # Update Affinity Group VIM name if VDU instantiation parameter is present
                    if vnf_params and vnf_params.get("affinity-or-anti-affinity-group"):
                        vnf_params_affinity_group = utils.find_in_list(
                            vnf_params["affinity-or-anti-affinity-group"],
                            lambda vnfp_ag: (
                                vnfp_ag.get("id") == vdu_affinity_group.get("id")
                            ),
                        )
                        if vnf_params_affinity_group.get("vim-affinity-group-id"):
                            nsr_affinity_group[
                                "vim-affinity-group-id"
                            ] = vnf_params_affinity_group["vim-affinity-group-id"]
                    affinity_group_ids.append(nsr_affinity_group["id"])
                vdur["affinity-or-anti-affinity-group-id"] = affinity_group_ids

            if vdu_instantiation_level:
                count = vdu_instantiation_level.get("number-of-instances")
            else:
                count = 1

            for index in range(0, count):
                vdur = deepcopy(vdur)
                for iface in vdur["interfaces"]:
                    if iface.get("ip-address") and index != 0:
                        iface["ip-address"] = increment_ip_mac(iface["ip-address"])
                    if iface.get("mac-address") and index != 0:
                        iface["mac-address"] = increment_ip_mac(iface["mac-address"])

                vdur["_id"] = str(uuid4())
                vdur["id"] = vdur["_id"]
                vdur["count-index"] = index
                vnfr_descriptor["vdur"].append(vdur)
        return vnfr_descriptor

    def vca_status_refresh(self, session, ns_instance_content, filter_q):
        """
        vcaStatus in ns_instance_content maybe stale, check if it is stale and create lcm op
        to refresh vca status by sending message to LCM when it is stale. Ignore otherwise.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param ns_instance_content:  ns instance content
        :param filter_q: dict: query parameter containing vcaStatus-refresh as true or false
        :return: None
        """
        time_now, time_delta = (
            time(),
            time() - ns_instance_content["_admin"]["modified"],
        )
        force_refresh = (
            isinstance(filter_q, dict) and filter_q.get("vcaStatusRefresh") == "true"
        )
        threshold_reached = time_delta > 120
        if force_refresh or threshold_reached:
            operation, _id = "vca_status_refresh", ns_instance_content["_id"]
            ns_instance_content["_admin"]["modified"] = time_now
            self.db.set_one(self.topic, {"_id": _id}, ns_instance_content)
            nslcmop_desc = NsLcmOpTopic._create_nslcmop(_id, operation, None)
            self.format_on_new(
                nslcmop_desc, session["project_id"], make_public=session["public"]
            )
            nslcmop_desc["_admin"].pop("nsState")
            self.msg.write("ns", operation, nslcmop_desc)
        return

    def show(self, session, _id, filter_q=None, api_req=False):
        """
        Get complete information on an ns instance.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: string, ns instance id
        :param filter_q: dict: query parameter containing vcaStatusRefresh as true or false
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: dictionary, raise exception if not found.
        """
        ns_instance_content = super().show(session, _id, api_req)
        self.vca_status_refresh(session, ns_instance_content, filter_q)
        return ns_instance_content

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method edit called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )


class VnfrTopic(BaseTopic):
    topic = "vnfrs"
    topic_msg = None

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        raise EngineException(
            "Method delete called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method edit called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        # Not used because vnfrs are created and deleted by NsrTopic class directly
        raise EngineException(
            "Method new called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )


class NsLcmOpTopic(BaseTopic):
    topic = "nslcmops"
    topic_msg = "ns"
    operation_schema = {  # mapping between operation and jsonschema to validate
        "instantiate": ns_instantiate,
        "action": ns_action,
        "update": ns_update,
        "scale": ns_scale,
        "heal": ns_heal,
        "terminate": ns_terminate,
        "migrate": ns_migrate,
        "cancel": nslcmop_cancel,
    }

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)
        self.nsrtopic = NsrTopic(db, fs, msg, auth)

    def _check_ns_operation(self, session, nsr, operation, indata):
        """
        Check that user has enter right parameters for the operation
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param operation: it can be: instantiate, terminate, action, update, heal
        :param indata: descriptor with the parameters of the operation
        :return: None
        """
        if operation == "action":
            self._check_action_ns_operation(indata, nsr)
        elif operation == "scale":
            self._check_scale_ns_operation(indata, nsr)
        elif operation == "update":
            self._check_update_ns_operation(indata, nsr)
        elif operation == "heal":
            self._check_heal_ns_operation(indata, nsr)
        elif operation == "instantiate":
            self._check_instantiate_ns_operation(indata, nsr, session)

    def _check_action_ns_operation(self, indata, nsr):
        nsd = nsr["nsd"]
        # check vnf_member_index
        if indata.get("vnf_member_index"):
            indata["member_vnf_index"] = indata.pop(
                "vnf_member_index"
            )  # for backward compatibility
        if indata.get("member_vnf_index"):
            vnfd = self._get_vnfd_from_vnf_member_index(
                indata["member_vnf_index"], nsr["_id"]
            )
            try:
                configs = vnfd.get("df")[0]["lcm-operations-configuration"][
                    "operate-vnf-op-config"
                ]["day1-2"]
            except Exception:
                configs = []

            if indata.get("vdu_id"):
                self._check_valid_vdu(vnfd, indata["vdu_id"])
                descriptor_configuration = utils.find_in_list(
                    configs, lambda config: config["id"] == indata["vdu_id"]
                )
            elif indata.get("kdu_name"):
                self._check_valid_kdu(vnfd, indata["kdu_name"])
                descriptor_configuration = utils.find_in_list(
                    configs, lambda config: config["id"] == indata.get("kdu_name")
                )
            else:
                descriptor_configuration = utils.find_in_list(
                    configs, lambda config: config["id"] == vnfd["id"]
                )
            if descriptor_configuration is not None:
                descriptor_configuration = descriptor_configuration.get(
                    "config-primitive"
                )
        else:  # use a NSD
            descriptor_configuration = nsd.get("ns-configuration", {}).get(
                "config-primitive"
            )

        # For k8s allows default primitives without validating the parameters
        if indata.get("kdu_name") and indata["primitive"] in (
            "upgrade",
            "rollback",
            "status",
            "inspect",
            "readme",
        ):
            # TODO should be checked that rollback only can contains revsision_numbe????
            if not indata.get("member_vnf_index"):
                raise EngineException(
                    "Missing action parameter 'member_vnf_index' for default KDU primitive '{}'".format(
                        indata["primitive"]
                    )
                )
            return
        # if not, check primitive
        for config_primitive in get_iterable(descriptor_configuration):
            if indata["primitive"] == config_primitive["name"]:
                # check needed primitive_params are provided
                if indata.get("primitive_params"):
                    in_primitive_params_copy = copy(indata["primitive_params"])
                else:
                    in_primitive_params_copy = {}
                for paramd in get_iterable(config_primitive.get("parameter")):
                    if paramd["name"] in in_primitive_params_copy:
                        del in_primitive_params_copy[paramd["name"]]
                    elif not paramd.get("default-value"):
                        raise EngineException(
                            "Needed parameter {} not provided for primitive '{}'".format(
                                paramd["name"], indata["primitive"]
                            )
                        )
                # check no extra primitive params are provided
                if in_primitive_params_copy:
                    raise EngineException(
                        "parameter/s '{}' not present at vnfd /nsd for primitive '{}'".format(
                            list(in_primitive_params_copy.keys()), indata["primitive"]
                        )
                    )
                break
        else:
            raise EngineException(
                "Invalid primitive '{}' is not present at vnfd/nsd".format(
                    indata["primitive"]
                )
            )

    def _check_update_ns_operation(self, indata, nsr) -> None:
        """Validates the ns-update request according to updateType

        If updateType is CHANGE_VNFPKG:
        - it checks the vnfInstanceId, whether it's available under ns instance
        - it checks the vnfdId whether it matches with the vnfd-id in the vnf-record of specified VNF.
        Otherwise exception will be raised.
        If updateType is REMOVE_VNF:
        - it checks if the vnfInstanceId is available in the ns instance
        - Otherwise exception will be raised.
        If updateType is OPERATE_VNF
        - it checks if the vdu-id is persent in the descriptor or not
        - it checks if the changeStateTo is either start, stop or rebuild
        If updateType is VERTICAL_SCALE
        - it checks if the vdu-id is persent in the descriptor or not

        Args:
            indata: includes updateType such as CHANGE_VNFPKG,
            nsr: network service record

        Raises:
           EngineException:
                a meaningful error if given update parameters are not proper such as
                "Error in validating ns-update request: <ID> does not match
                with the vnfd-id of vnfinstance
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY"

        """
        try:
            if indata["updateType"] == "CHANGE_VNFPKG":
                # vnfInstanceId, nsInstanceId, vnfdId are mandatory
                vnf_instance_id = indata["changeVnfPackageData"]["vnfInstanceId"]
                ns_instance_id = indata["nsInstanceId"]
                vnfd_id_2update = indata["changeVnfPackageData"]["vnfdId"]

                if vnf_instance_id not in nsr["constituent-vnfr-ref"]:
                    raise EngineException(
                        f"Error in validating ns-update request: vnf {vnf_instance_id} does not "
                        f"belong to NS {ns_instance_id}",
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

                # Getting vnfrs through the ns_instance_id
                vnfrs = self.db.get_list("vnfrs", {"nsr-id-ref": ns_instance_id})
                constituent_vnfd_id = next(
                    (
                        vnfr["vnfd-id"]
                        for vnfr in vnfrs
                        if vnfr["id"] == vnf_instance_id
                    ),
                    None,
                )

                # Check the given vnfd-id belongs to given vnf instance
                if constituent_vnfd_id and (vnfd_id_2update != constituent_vnfd_id):
                    raise EngineException(
                        f"Error in validating ns-update request: vnfd-id {vnfd_id_2update} does not "
                        f"match with the vnfd-id: {constituent_vnfd_id} of VNF instance: {vnf_instance_id}",
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

                # Validating the ns update timeout
                if (
                    indata.get("timeout_ns_update")
                    and indata["timeout_ns_update"] < 300
                ):
                    raise EngineException(
                        "Error in validating ns-update request: {} second is not enough "
                        "to upgrade the VNF instance: {}".format(
                            indata["timeout_ns_update"], vnf_instance_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
            elif indata["updateType"] == "REMOVE_VNF":
                vnf_instance_id = indata["removeVnfInstanceId"]
                ns_instance_id = indata["nsInstanceId"]
                if vnf_instance_id not in nsr["constituent-vnfr-ref"]:
                    raise EngineException(
                        "Invalid VNF Instance Id. '{}' is not "
                        "present in the NS '{}'".format(vnf_instance_id, ns_instance_id)
                    )
            elif indata["updateType"] == "OPERATE_VNF":
                if indata.get("operateVnfData"):
                    if indata["operateVnfData"]["changeStateTo"] not in (
                        "start",
                        "stop",
                        "rebuild",
                        "console",
                    ):
                        raise EngineException(
                            f"The operate type should be either start, stop, console or rebuild not {indata['operateVnfData']['changeStateTo']}",
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )
                    if indata["operateVnfData"].get("additionalParam"):
                        vdu_id = indata["operateVnfData"]["additionalParam"]["vdu_id"]
                        vnfinstance_id = indata["operateVnfData"]["vnfInstanceId"]
                        vnf = self.db.get_one("vnfrs", {"_id": vnfinstance_id})
                        vnfd_member_vnf_index = vnf.get("member-vnf-index-ref")
                        vnfd = self._get_vnfd_from_vnf_member_index(
                            vnfd_member_vnf_index, nsr["_id"]
                        )
                        self._check_valid_vdu(vnfd, vdu_id)
            elif indata["updateType"] == "VERTICAL_SCALE":
                if indata.get("verticalScaleVnf"):
                    vdu_id = indata["verticalScaleVnf"]["vduId"]
                    vnfinstance_id = indata["verticalScaleVnf"]["vnfInstanceId"]
                    vnf = self.db.get_one("vnfrs", {"_id": vnfinstance_id})
                    vnfd_member_vnf_index = vnf.get("member-vnf-index-ref")
                    vnfd = self._get_vnfd_from_vnf_member_index(
                        vnfd_member_vnf_index, nsr["_id"]
                    )
                    self._check_valid_vdu(vnfd, vdu_id)

        except (
            DbException,
            AttributeError,
            IndexError,
            KeyError,
            ValueError,
        ) as e:
            raise type(e)(
                "Ns update request could not be processed with error: {}.".format(e)
            )

    def _check_scale_ns_operation(self, indata, nsr):
        vnfd = self._get_vnfd_from_vnf_member_index(
            indata["scaleVnfData"]["scaleByStepData"]["member-vnf-index"], nsr["_id"]
        )
        for scaling_aspect in get_iterable(vnfd.get("df", ())[0]["scaling-aspect"]):
            if (
                indata["scaleVnfData"]["scaleByStepData"]["scaling-group-descriptor"]
                == scaling_aspect["id"]
            ):
                break
        else:
            raise EngineException(
                "Invalid scaleVnfData:scaleByStepData:scaling-group-descriptor '{}' is not "
                "present at vnfd:scaling-aspect".format(
                    indata["scaleVnfData"]["scaleByStepData"][
                        "scaling-group-descriptor"
                    ]
                )
            )

    def _check_heal_ns_operation(self, indata, nsr):
        try:
            for data in indata.get("healVnfData"):
                vnf_id = data.get("vnfInstanceId")
                vnf = self.db.get_one("vnfrs", {"_id": vnf_id})
                vnfd_member_vnf_index = vnf.get("member-vnf-index-ref")
                vnfd = self._get_vnfd_from_vnf_member_index(
                    vnfd_member_vnf_index, nsr["_id"]
                )
                if data.get("additionalParams"):
                    vdu_id = data["additionalParams"].get("vdu")
                    if vdu_id:
                        for index in range(len(vdu_id)):
                            vdu = vdu_id[index].get("vdu-id")
                            self._check_valid_vdu(vnfd, vdu)
        except (DbException, AttributeError, IndexError, KeyError, ValueError) as e:
            raise type(e)(
                "Ns healing request could not be processed with error: {}.".format(e)
            )

    def _check_instantiate_ns_operation(self, indata, nsr, session):
        vnf_member_index_to_vnfd = {}  # map between vnf_member_index to vnf descriptor.
        vim_accounts = []
        wim_accounts = []
        nsd = nsr["nsd"]
        self._check_valid_vim_account(indata["vimAccountId"], vim_accounts, session)
        self._check_valid_wim_account(indata.get("wimAccountId"), wim_accounts, session)
        for in_vnf in get_iterable(indata.get("vnf")):
            member_vnf_index = in_vnf["member-vnf-index"]
            if vnf_member_index_to_vnfd.get(member_vnf_index):
                vnfd = vnf_member_index_to_vnfd[member_vnf_index]
            else:
                vnfd = self._get_vnfd_from_vnf_member_index(
                    member_vnf_index, nsr["_id"]
                )
                vnf_member_index_to_vnfd[
                    member_vnf_index
                ] = vnfd  # add to cache, avoiding a later look for
            self._check_vnf_instantiation_params(in_vnf, vnfd)
            if in_vnf.get("vimAccountId"):
                self._check_valid_vim_account(
                    in_vnf["vimAccountId"], vim_accounts, session
                )

        for in_vld in get_iterable(indata.get("vld")):
            self._check_valid_wim_account(
                in_vld.get("wimAccountId"), wim_accounts, session
            )
            for vldd in get_iterable(nsd.get("virtual-link-desc")):
                if in_vld["name"] == vldd["id"]:
                    break
            else:
                raise EngineException(
                    "Invalid parameter vld:name='{}' is not present at nsd:vld".format(
                        in_vld["name"]
                    )
                )

    def _get_vnfd_from_vnf_member_index(self, member_vnf_index, nsr_id):
        # Obtain vnf descriptor. The vnfr is used to get the vnfd._id used for this member_vnf_index
        vnfr = self.db.get_one(
            "vnfrs",
            {"nsr-id-ref": nsr_id, "member-vnf-index-ref": member_vnf_index},
            fail_on_empty=False,
        )
        if not vnfr:
            raise EngineException(
                "Invalid parameter member_vnf_index='{}' is not one of the "
                "nsd:constituent-vnfd".format(member_vnf_index)
            )

        # Backwards compatibility: if there is no revision, get it from the one and only VNFD entry
        if "revision" in vnfr:
            vnfd_revision = vnfr["vnfd-id"] + ":" + str(vnfr["revision"])
            vnfd = self.db.get_one(
                "vnfds_revisions", {"_id": vnfd_revision}, fail_on_empty=False
            )
        else:
            vnfd = self.db.get_one(
                "vnfds", {"_id": vnfr["vnfd-id"]}, fail_on_empty=False
            )

        if not vnfd:
            raise EngineException(
                "vnfd id={} has been deleted!. Operation cannot be performed".format(
                    vnfr["vnfd-id"]
                )
            )
        return vnfd

    def _check_valid_vdu(self, vnfd, vdu_id):
        for vdud in get_iterable(vnfd.get("vdu")):
            if vdud["id"] == vdu_id:
                return vdud
        else:
            raise EngineException(
                "Invalid parameter vdu_id='{}' not present at vnfd:vdu:id".format(
                    vdu_id
                )
            )

    def _check_valid_kdu(self, vnfd, kdu_name):
        for kdud in get_iterable(vnfd.get("kdu")):
            if kdud["name"] == kdu_name:
                return kdud
        else:
            raise EngineException(
                "Invalid parameter kdu_name='{}' not present at vnfd:kdu:name".format(
                    kdu_name
                )
            )

    def _check_vnf_instantiation_params(self, in_vnf, vnfd):
        for in_vdu in get_iterable(in_vnf.get("vdu")):
            for vdu in get_iterable(vnfd.get("vdu")):
                if in_vdu["id"] == vdu["id"]:
                    for volume in get_iterable(in_vdu.get("volume")):
                        for volumed in get_iterable(vdu.get("virtual-storage-desc")):
                            if volumed == volume["name"]:
                                break
                        else:
                            raise EngineException(
                                "Invalid parameter vnf[member-vnf-index='{}']:vdu[id='{}']:"
                                "volume:name='{}' is not present at "
                                "vnfd:vdu:virtual-storage-desc list".format(
                                    in_vnf["member-vnf-index"],
                                    in_vdu["id"],
                                    volume["id"],
                                )
                            )

                    vdu_if_names = set()
                    for cpd in get_iterable(vdu.get("int-cpd")):
                        for iface in get_iterable(
                            cpd.get("virtual-network-interface-requirement")
                        ):
                            vdu_if_names.add(iface.get("name"))

                    for in_iface in get_iterable(in_vdu.get("interface")):
                        if in_iface["name"] in vdu_if_names:
                            break
                        else:
                            raise EngineException(
                                "Invalid parameter vnf[member-vnf-index='{}']:vdu[id='{}']:"
                                "int-cpd[id='{}'] is not present at vnfd:vdu:int-cpd".format(
                                    in_vnf["member-vnf-index"],
                                    in_vdu["id"],
                                    in_iface["name"],
                                )
                            )
                    break

            else:
                raise EngineException(
                    "Invalid parameter vnf[member-vnf-index='{}']:vdu[id='{}'] is not present "
                    "at vnfd:vdu".format(in_vnf["member-vnf-index"], in_vdu["id"])
                )

        vnfd_ivlds_cpds = {
            ivld.get("id"): set()
            for ivld in get_iterable(vnfd.get("int-virtual-link-desc"))
        }
        for vdu in vnfd.get("vdu", {}):
            for cpd in vdu.get("int-cpd", {}):
                if cpd.get("int-virtual-link-desc"):
                    vnfd_ivlds_cpds[cpd.get("int-virtual-link-desc")] = cpd.get("id")

        for in_ivld in get_iterable(in_vnf.get("internal-vld")):
            if in_ivld.get("name") in vnfd_ivlds_cpds:
                for in_icp in get_iterable(in_ivld.get("internal-connection-point")):
                    if in_icp["id-ref"] in vnfd_ivlds_cpds[in_ivld.get("name")]:
                        break
                    else:
                        raise EngineException(
                            "Invalid parameter vnf[member-vnf-index='{}']:internal-vld[name"
                            "='{}']:internal-connection-point[id-ref:'{}'] is not present at "
                            "vnfd:internal-vld:name/id:internal-connection-point".format(
                                in_vnf["member-vnf-index"],
                                in_ivld["name"],
                                in_icp["id-ref"],
                            )
                        )
            else:
                raise EngineException(
                    "Invalid parameter vnf[member-vnf-index='{}']:internal-vld:name='{}'"
                    " is not present at vnfd '{}'".format(
                        in_vnf["member-vnf-index"], in_ivld["name"], vnfd["id"]
                    )
                )

    def _check_valid_vim_account(self, vim_account, vim_accounts, session):
        if vim_account in vim_accounts:
            return
        try:
            db_filter = self._get_project_filter(session)
            db_filter["_id"] = vim_account
            self.db.get_one("vim_accounts", db_filter)
        except Exception:
            raise EngineException(
                "Invalid vimAccountId='{}' not present for the project".format(
                    vim_account
                )
            )
        vim_accounts.append(vim_account)

    def _get_vim_account(self, vim_id: str, session):
        try:
            db_filter = self._get_project_filter(session)
            db_filter["_id"] = vim_id
            return self.db.get_one("vim_accounts", db_filter)
        except Exception:
            raise EngineException(
                "Invalid vimAccountId='{}' not present for the project".format(vim_id)
            )

    def _check_valid_wim_account(self, wim_account, wim_accounts, session):
        if not isinstance(wim_account, str):
            return
        if wim_account in wim_accounts:
            return
        try:
            db_filter = self._get_project_filter(session)
            db_filter["_id"] = wim_account
            self.db.get_one("wim_accounts", db_filter)
        except Exception:
            raise EngineException(
                "Invalid wimAccountId='{}' not present for the project".format(
                    wim_account
                )
            )
        wim_accounts.append(wim_account)

    def _look_for_pdu(
        self, session, rollback, vnfr, vim_account, vnfr_update, vnfr_update_rollback
    ):
        """
        Look for a free PDU in the catalog matching vdur type and interfaces. Fills vnfr.vdur with the interface
        (ip_address, ...) information.
        Modifies PDU _admin.usageState to 'IN_USE'
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param rollback: list with the database modifications to rollback if needed
        :param vnfr: vnfr to be updated. It is modified with pdu interface info if pdu is found
        :param vim_account: vim_account where this vnfr should be deployed
        :param vnfr_update: dictionary filled by this method with changes to be done at database vnfr
        :param vnfr_update_rollback: dictionary filled by this method with original content of vnfr in case a rollback
                                     of the changed vnfr is needed

        :return: List of PDU interfaces that are connected to an existing VIM network. Each item contains:
                 "vim-network-name": used at VIM
                  "name": interface name
                  "vnf-vld-id": internal VNFD vld where this interface is connected, or
                  "ns-vld-id": NSD vld where this interface is connected.
                  NOTE: One, and only one between 'vnf-vld-id' and 'ns-vld-id' contains a value. The other will be None
        """

        ifaces_forcing_vim_network = []
        for vdur_index, vdur in enumerate(get_iterable(vnfr.get("vdur"))):
            if not vdur.get("pdu-type"):
                continue
            pdu_type = vdur.get("pdu-type")
            pdu_filter = self._get_project_filter(session)
            pdu_filter["vim_accounts"] = vim_account
            pdu_filter["type"] = pdu_type
            pdu_filter["_admin.operationalState"] = "ENABLED"
            pdu_filter["_admin.usageState"] = "NOT_IN_USE"
            # TODO feature 1417: "shared": True,

            available_pdus = self.db.get_list("pdus", pdu_filter)
            for pdu in available_pdus:
                # step 1 check if this pdu contains needed interfaces:
                match_interfaces = True
                for vdur_interface in vdur["interfaces"]:
                    for pdu_interface in pdu["interfaces"]:
                        if pdu_interface["name"] == vdur_interface["name"]:
                            # TODO feature 1417: match per mgmt type
                            break
                    else:  # no interface found for name
                        match_interfaces = False
                        break
                if match_interfaces:
                    break
            else:
                raise EngineException(
                    "No PDU of type={} at vim_account={} found for member_vnf_index={}, vdu={} matching interface "
                    "names".format(
                        pdu_type,
                        vim_account,
                        vnfr["member-vnf-index-ref"],
                        vdur["vdu-id-ref"],
                    )
                )

            # step 2. Update pdu
            rollback_pdu = {
                "_admin.usageState": pdu["_admin"]["usageState"],
                "_admin.usage.vnfr_id": None,
                "_admin.usage.nsr_id": None,
                "_admin.usage.vdur": None,
            }
            self.db.set_one(
                "pdus",
                {"_id": pdu["_id"]},
                {
                    "_admin.usageState": "IN_USE",
                    "_admin.usage": {
                        "vnfr_id": vnfr["_id"],
                        "nsr_id": vnfr["nsr-id-ref"],
                        "vdur": vdur["vdu-id-ref"],
                    },
                },
            )
            rollback.append(
                {
                    "topic": "pdus",
                    "_id": pdu["_id"],
                    "operation": "set",
                    "content": rollback_pdu,
                }
            )

            # step 3. Fill vnfr info by filling vdur
            vdu_text = "vdur.{}".format(vdur_index)
            vnfr_update_rollback[vdu_text + ".pdu-id"] = None
            vnfr_update[vdu_text + ".pdu-id"] = pdu["_id"]
            for iface_index, vdur_interface in enumerate(vdur["interfaces"]):
                for pdu_interface in pdu["interfaces"]:
                    if pdu_interface["name"] == vdur_interface["name"]:
                        iface_text = vdu_text + ".interfaces.{}".format(iface_index)
                        for k, v in pdu_interface.items():
                            if k in (
                                "ip-address",
                                "mac-address",
                            ):  # TODO: switch-xxxxx must be inserted
                                vnfr_update[iface_text + ".{}".format(k)] = v
                                vnfr_update_rollback[
                                    iface_text + ".{}".format(k)
                                ] = vdur_interface.get(v)
                        if pdu_interface.get("ip-address"):
                            if vdur_interface.get(
                                "mgmt-interface"
                            ) or vdur_interface.get("mgmt-vnf"):
                                vnfr_update_rollback[
                                    vdu_text + ".ip-address"
                                ] = vdur.get("ip-address")
                                vnfr_update[vdu_text + ".ip-address"] = pdu_interface[
                                    "ip-address"
                                ]
                            if vdur_interface.get("mgmt-vnf"):
                                vnfr_update_rollback["ip-address"] = vnfr.get(
                                    "ip-address"
                                )
                                vnfr_update["ip-address"] = pdu_interface["ip-address"]
                                vnfr_update[vdu_text + ".ip-address"] = pdu_interface[
                                    "ip-address"
                                ]
                        if pdu_interface.get("vim-network-name") or pdu_interface.get(
                            "vim-network-id"
                        ):
                            ifaces_forcing_vim_network.append(
                                {
                                    "name": vdur_interface.get("vnf-vld-id")
                                    or vdur_interface.get("ns-vld-id"),
                                    "vnf-vld-id": vdur_interface.get("vnf-vld-id"),
                                    "ns-vld-id": vdur_interface.get("ns-vld-id"),
                                }
                            )
                            if pdu_interface.get("vim-network-id"):
                                ifaces_forcing_vim_network[-1][
                                    "vim-network-id"
                                ] = pdu_interface["vim-network-id"]
                            if pdu_interface.get("vim-network-name"):
                                ifaces_forcing_vim_network[-1][
                                    "vim-network-name"
                                ] = pdu_interface["vim-network-name"]
                        break

        return ifaces_forcing_vim_network

    def _look_for_k8scluster(
        self, session, rollback, vnfr, vim_account, vnfr_update, vnfr_update_rollback
    ):
        """
        Look for an available k8scluster for all the kuds in the vnfd matching version and cni requirements.
        Fills vnfr.kdur with the selected k8scluster

        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param rollback: list with the database modifications to rollback if needed
        :param vnfr: vnfr to be updated. It is modified with pdu interface info if pdu is found
        :param vim_account: vim_account where this vnfr should be deployed
        :param vnfr_update: dictionary filled by this method with changes to be done at database vnfr
        :param vnfr_update_rollback: dictionary filled by this method with original content of vnfr in case a rollback
                                     of the changed vnfr is needed

        :return: List of KDU interfaces that are connected to an existing VIM network. Each item contains:
                 "vim-network-name": used at VIM
                  "name": interface name
                  "vnf-vld-id": internal VNFD vld where this interface is connected, or
                  "ns-vld-id": NSD vld where this interface is connected.
                  NOTE: One, and only one between 'vnf-vld-id' and 'ns-vld-id' contains a value. The other will be None
        """

        ifaces_forcing_vim_network = []
        if not vnfr.get("kdur"):
            return ifaces_forcing_vim_network

        kdu_filter = self._get_project_filter(session)
        kdu_filter["vim_account"] = vim_account
        # TODO kdu_filter["_admin.operationalState"] = "ENABLED"
        available_k8sclusters = self.db.get_list("k8sclusters", kdu_filter)

        k8s_requirements = {}  # just for logging
        for k8scluster in available_k8sclusters:
            if not vnfr.get("k8s-cluster"):
                break
            # restrict by cni
            if vnfr["k8s-cluster"].get("cni"):
                k8s_requirements["cni"] = vnfr["k8s-cluster"]["cni"]
                if not set(vnfr["k8s-cluster"]["cni"]).intersection(
                    k8scluster.get("cni", ())
                ):
                    continue
            # restrict by version
            if vnfr["k8s-cluster"].get("version"):
                k8s_requirements["version"] = vnfr["k8s-cluster"]["version"]
                if k8scluster.get("k8s_version") not in vnfr["k8s-cluster"]["version"]:
                    continue
            # restrict by number of networks
            if vnfr["k8s-cluster"].get("nets"):
                k8s_requirements["networks"] = len(vnfr["k8s-cluster"]["nets"])
                if not k8scluster.get("nets") or len(k8scluster["nets"]) < len(
                    vnfr["k8s-cluster"]["nets"]
                ):
                    continue
            break
        else:
            raise EngineException(
                "No k8scluster with requirements='{}' at vim_account={} found for member_vnf_index={}".format(
                    k8s_requirements, vim_account, vnfr["member-vnf-index-ref"]
                )
            )

        for kdur_index, kdur in enumerate(get_iterable(vnfr.get("kdur"))):
            # step 3. Fill vnfr info by filling kdur
            kdu_text = "kdur.{}.".format(kdur_index)
            vnfr_update_rollback[kdu_text + "k8s-cluster.id"] = None
            vnfr_update[kdu_text + "k8s-cluster.id"] = k8scluster["_id"]

        # step 4. Check VIM networks that forces the selected k8s_cluster
        if vnfr.get("k8s-cluster") and vnfr["k8s-cluster"].get("nets"):
            k8scluster_net_list = list(k8scluster.get("nets").keys())
            for net_index, kdur_net in enumerate(vnfr["k8s-cluster"]["nets"]):
                # get a network from k8s_cluster nets. If name matches use this, if not use other
                if kdur_net["id"] in k8scluster_net_list:  # name matches
                    vim_net = k8scluster["nets"][kdur_net["id"]]
                    k8scluster_net_list.remove(kdur_net["id"])
                else:
                    vim_net = k8scluster["nets"][k8scluster_net_list[0]]
                    k8scluster_net_list.pop(0)
                vnfr_update_rollback[
                    "k8s-cluster.nets.{}.vim_net".format(net_index)
                ] = None
                vnfr_update["k8s-cluster.nets.{}.vim_net".format(net_index)] = vim_net
                if vim_net and (
                    kdur_net.get("vnf-vld-id") or kdur_net.get("ns-vld-id")
                ):
                    ifaces_forcing_vim_network.append(
                        {
                            "name": kdur_net.get("vnf-vld-id")
                            or kdur_net.get("ns-vld-id"),
                            "vnf-vld-id": kdur_net.get("vnf-vld-id"),
                            "ns-vld-id": kdur_net.get("ns-vld-id"),
                            "vim-network-name": vim_net,  # TODO can it be vim-network-id ???
                        }
                    )
            # TODO check that this forcing is not incompatible with other forcing
        return ifaces_forcing_vim_network

    def _update_vnfrs_from_nsd(self, nsr):
        step = "Getting vnf_profiles from nsd"  # first step must be defined outside try
        try:
            nsr_id = nsr["_id"]
            nsd = nsr["nsd"]

            vnf_profiles = nsd.get("df", [{}])[0].get("vnf-profile", ())
            vld_fixed_ip_connection_point_data = {}

            step = "Getting ip-address info from vnf_profile if it exists"
            for vnfp in vnf_profiles:
                # Checking ip-address info from nsd.vnf_profile and storing
                for vlc in vnfp.get("virtual-link-connectivity", ()):
                    for cpd in vlc.get("constituent-cpd-id", ()):
                        if cpd.get("ip-address"):
                            step = "Storing ip-address info"
                            vld_fixed_ip_connection_point_data.update(
                                {
                                    vlc.get("virtual-link-profile-id")
                                    + "."
                                    + cpd.get("constituent-base-element-id"): {
                                        "vnfd-connection-point-ref": cpd.get(
                                            "constituent-cpd-id"
                                        ),
                                        "ip-address": cpd.get("ip-address"),
                                    }
                                }
                            )

            # Inserting ip address to vnfr
            if len(vld_fixed_ip_connection_point_data) > 0:
                step = "Getting vnfrs"
                vnfrs = self.db.get_list("vnfrs", {"nsr-id-ref": nsr_id})
                for item in vld_fixed_ip_connection_point_data.keys():
                    step = "Filtering vnfrs"
                    vnfr = next(
                        filter(
                            lambda vnfr: vnfr["member-vnf-index-ref"]
                            == item.split(".")[1],
                            vnfrs,
                        ),
                        None,
                    )
                    if vnfr:
                        vnfr_update = {}
                        for vdur_index, vdur in enumerate(vnfr["vdur"]):
                            for iface_index, iface in enumerate(vdur["interfaces"]):
                                step = "Looking for matched interface"
                                if (
                                    iface.get("external-connection-point-ref")
                                    == vld_fixed_ip_connection_point_data[item].get(
                                        "vnfd-connection-point-ref"
                                    )
                                    and iface.get("ns-vld-id") == item.split(".")[0]
                                ):
                                    vnfr_update_text = "vdur.{}.interfaces.{}".format(
                                        vdur_index, iface_index
                                    )
                                    step = "Storing info in order to update vnfr"
                                    vnfr_update[
                                        vnfr_update_text + ".ip-address"
                                    ] = increment_ip_mac(
                                        vld_fixed_ip_connection_point_data[item].get(
                                            "ip-address"
                                        ),
                                        vdur.get("count-index", 0),
                                    )
                                    vnfr_update[vnfr_update_text + ".fixed-ip"] = True

                        step = "updating vnfr at database"
                        self.db.set_one("vnfrs", {"_id": vnfr["_id"]}, vnfr_update)
        except (
            ValidationError,
            EngineException,
            DbException,
            MsgException,
            FsException,
        ) as e:
            raise type(e)("{} while '{}'".format(e, step), http_code=e.http_code)

    def _update_vnfrs(self, session, rollback, nsr, indata):
        # get vnfr
        nsr_id = nsr["_id"]
        vnfrs = self.db.get_list("vnfrs", {"nsr-id-ref": nsr_id})

        for vnfr in vnfrs:
            vnfr_update = {}
            vnfr_update_rollback = {}
            member_vnf_index = vnfr["member-vnf-index-ref"]
            # update vim-account-id

            vim_account = indata["vimAccountId"]
            vca_id = self._get_vim_account(vim_account, session).get("vca")
            # check instantiate parameters
            for vnf_inst_params in get_iterable(indata.get("vnf")):
                if vnf_inst_params["member-vnf-index"] != member_vnf_index:
                    continue
                if vnf_inst_params.get("vimAccountId"):
                    vim_account = vnf_inst_params.get("vimAccountId")
                    vca_id = self._get_vim_account(vim_account, session).get("vca")

                # get vnf.vdu.interface instantiation params to update vnfr.vdur.interfaces ip, mac
                for vdu_inst_param in get_iterable(vnf_inst_params.get("vdu")):
                    for vdur_index, vdur in enumerate(vnfr["vdur"]):
                        if vdu_inst_param["id"] != vdur["vdu-id-ref"]:
                            continue
                        for iface_inst_param in get_iterable(
                            vdu_inst_param.get("interface")
                        ):
                            iface_index, _ = next(
                                i
                                for i in enumerate(vdur["interfaces"])
                                if i[1]["name"] == iface_inst_param["name"]
                            )
                            vnfr_update_text = "vdur.{}.interfaces.{}".format(
                                vdur_index, iface_index
                            )
                            if iface_inst_param.get("ip-address"):
                                vnfr_update[
                                    vnfr_update_text + ".ip-address"
                                ] = increment_ip_mac(
                                    iface_inst_param.get("ip-address"),
                                    vdur.get("count-index", 0),
                                )
                                vnfr_update[vnfr_update_text + ".fixed-ip"] = True
                            if iface_inst_param.get("mac-address"):
                                vnfr_update[
                                    vnfr_update_text + ".mac-address"
                                ] = increment_ip_mac(
                                    iface_inst_param.get("mac-address"),
                                    vdur.get("count-index", 0),
                                )
                                vnfr_update[vnfr_update_text + ".fixed-mac"] = True
                            if iface_inst_param.get("floating-ip-required"):
                                vnfr_update[
                                    vnfr_update_text + ".floating-ip-required"
                                ] = True
                # get vnf.internal-vld.internal-conection-point instantiation params to update vnfr.vdur.interfaces
                # TODO update vld with the ip-profile
                for ivld_inst_param in get_iterable(
                    vnf_inst_params.get("internal-vld")
                ):
                    for icp_inst_param in get_iterable(
                        ivld_inst_param.get("internal-connection-point")
                    ):
                        # look for iface
                        for vdur_index, vdur in enumerate(vnfr["vdur"]):
                            for iface_index, iface in enumerate(vdur["interfaces"]):
                                if (
                                    iface.get("internal-connection-point-ref")
                                    == icp_inst_param["id-ref"]
                                ):
                                    vnfr_update_text = "vdur.{}.interfaces.{}".format(
                                        vdur_index, iface_index
                                    )
                                    if icp_inst_param.get("ip-address"):
                                        vnfr_update[
                                            vnfr_update_text + ".ip-address"
                                        ] = increment_ip_mac(
                                            icp_inst_param.get("ip-address"),
                                            vdur.get("count-index", 0),
                                        )
                                        vnfr_update[
                                            vnfr_update_text + ".fixed-ip"
                                        ] = True
                                    if icp_inst_param.get("mac-address"):
                                        vnfr_update[
                                            vnfr_update_text + ".mac-address"
                                        ] = increment_ip_mac(
                                            icp_inst_param.get("mac-address"),
                                            vdur.get("count-index", 0),
                                        )
                                        vnfr_update[
                                            vnfr_update_text + ".fixed-mac"
                                        ] = True
                                    break
            # get ip address from instantiation parameters.vld.vnfd-connection-point-ref
            for vld_inst_param in get_iterable(indata.get("vld")):
                for vnfcp_inst_param in get_iterable(
                    vld_inst_param.get("vnfd-connection-point-ref")
                ):
                    if vnfcp_inst_param["member-vnf-index-ref"] != member_vnf_index:
                        continue
                    # look for iface
                    for vdur_index, vdur in enumerate(vnfr["vdur"]):
                        for iface_index, iface in enumerate(vdur["interfaces"]):
                            if (
                                iface.get("external-connection-point-ref")
                                == vnfcp_inst_param["vnfd-connection-point-ref"]
                            ):
                                vnfr_update_text = "vdur.{}.interfaces.{}".format(
                                    vdur_index, iface_index
                                )
                                if vnfcp_inst_param.get("ip-address"):
                                    vnfr_update[
                                        vnfr_update_text + ".ip-address"
                                    ] = increment_ip_mac(
                                        vnfcp_inst_param.get("ip-address"),
                                        vdur.get("count-index", 0),
                                    )
                                    vnfr_update[vnfr_update_text + ".fixed-ip"] = True
                                if vnfcp_inst_param.get("mac-address"):
                                    vnfr_update[
                                        vnfr_update_text + ".mac-address"
                                    ] = increment_ip_mac(
                                        vnfcp_inst_param.get("mac-address"),
                                        vdur.get("count-index", 0),
                                    )
                                    vnfr_update[vnfr_update_text + ".fixed-mac"] = True
                                break

            vnfr_update["vim-account-id"] = vim_account
            vnfr_update_rollback["vim-account-id"] = vnfr.get("vim-account-id")

            if vca_id:
                vnfr_update["vca-id"] = vca_id
                vnfr_update_rollback["vca-id"] = vnfr.get("vca-id")

            # get pdu
            ifaces_forcing_vim_network = self._look_for_pdu(
                session, rollback, vnfr, vim_account, vnfr_update, vnfr_update_rollback
            )

            # get kdus
            ifaces_forcing_vim_network += self._look_for_k8scluster(
                session, rollback, vnfr, vim_account, vnfr_update, vnfr_update_rollback
            )
            # update database vnfr
            self.db.set_one("vnfrs", {"_id": vnfr["_id"]}, vnfr_update)
            rollback.append(
                {
                    "topic": "vnfrs",
                    "_id": vnfr["_id"],
                    "operation": "set",
                    "content": vnfr_update_rollback,
                }
            )

            # Update indada in case pdu forces to use a concrete vim-network-name
            # TODO check if user has already insert a vim-network-name and raises an error
            if not ifaces_forcing_vim_network:
                continue
            for iface_info in ifaces_forcing_vim_network:
                if iface_info.get("ns-vld-id"):
                    if "vld" not in indata:
                        indata["vld"] = []
                    indata["vld"].append(
                        {
                            key: iface_info[key]
                            for key in ("name", "vim-network-name", "vim-network-id")
                            if iface_info.get(key)
                        }
                    )

                elif iface_info.get("vnf-vld-id"):
                    if "vnf" not in indata:
                        indata["vnf"] = []
                    indata["vnf"].append(
                        {
                            "member-vnf-index": member_vnf_index,
                            "internal-vld": [
                                {
                                    key: iface_info[key]
                                    for key in (
                                        "name",
                                        "vim-network-name",
                                        "vim-network-id",
                                    )
                                    if iface_info.get(key)
                                }
                            ],
                        }
                    )

    @staticmethod
    def _create_nslcmop(nsr_id, operation, params):
        """
        Creates a ns-lcm-opp content to be stored at database.
        :param nsr_id: internal id of the instance
        :param operation: instantiate, terminate, scale, action, update ...
        :param params: user parameters for the operation
        :return: dictionary following SOL005 format
        """
        now = time()
        _id = str(uuid4())
        nslcmop = {
            "id": _id,
            "_id": _id,
            "operationState": "PROCESSING",  # COMPLETED,PARTIALLY_COMPLETED,FAILED_TEMP,FAILED,ROLLING_BACK,ROLLED_BACK
            "queuePosition": None,
            "stage": None,
            "errorMessage": None,
            "detailedStatus": None,
            "statusEnteredTime": now,
            "nsInstanceId": nsr_id,
            "lcmOperationType": operation,
            "startTime": now,
            "isAutomaticInvocation": False,
            "operationParams": params,
            "isCancelPending": False,
            "links": {
                "self": "/osm/nslcm/v1/ns_lcm_op_occs/" + _id,
                "nsInstance": "/osm/nslcm/v1/ns_instances/" + nsr_id,
            },
        }
        return nslcmop

    def _get_enabled_vims(self, session):
        """
        Retrieve and return VIM accounts that are accessible by current user and has state ENABLE
        :param session: current session with user information
        """
        db_filter = self._get_project_filter(session)
        db_filter["_admin.operationalState"] = "ENABLED"
        vims = self.db.get_list("vim_accounts", db_filter)
        vimAccounts = []
        for vim in vims:
            vimAccounts.append(vim["_id"])
        return vimAccounts

    def new(
        self,
        rollback,
        session,
        indata=None,
        kwargs=None,
        headers=None,
        slice_object=False,
    ):
        """
        Performs a new operation over a ns
        :param rollback: list to append created items at database in case a rollback must to be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: descriptor with the parameters of the operation. It must contains among others
            nsInstanceId: _id of the nsr to perform the operation
            operation: it can be: instantiate, terminate, action, update TODO: heal
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: id of the nslcmops
        """

        def check_if_nsr_is_not_slice_member(session, nsr_id):
            nsis = None
            db_filter = self._get_project_filter(session)
            db_filter["_admin.nsrs-detailed-list.ANYINDEX.nsrId"] = nsr_id
            nsis = self.db.get_one(
                "nsis", db_filter, fail_on_empty=False, fail_on_more=False
            )
            if nsis:
                raise EngineException(
                    "The NS instance {} cannot be terminated because is used by the slice {}".format(
                        nsr_id, nsis["_id"]
                    ),
                    http_code=HTTPStatus.CONFLICT,
                )

        try:
            # Override descriptor with query string kwargs
            self._update_input_with_kwargs(indata, kwargs, yaml_format=True)
            operation = indata["lcmOperationType"]
            nsInstanceId = indata["nsInstanceId"]

            validate_input(indata, self.operation_schema[operation])
            # get ns from nsr_id
            _filter = BaseTopic._get_project_filter(session)
            _filter["_id"] = nsInstanceId
            nsr = self.db.get_one("nsrs", _filter)

            # initial checking
            if operation == "terminate" and slice_object is False:
                check_if_nsr_is_not_slice_member(session, nsr["_id"])
            if (
                not nsr["_admin"].get("nsState")
                or nsr["_admin"]["nsState"] == "NOT_INSTANTIATED"
            ):
                if operation == "terminate" and indata.get("autoremove"):
                    # NSR must be deleted
                    return (
                        None,
                        None,
                        None,
                    )  # a none in this case is used to indicate not instantiated. It can be removed
                if operation != "instantiate":
                    raise EngineException(
                        "ns_instance '{}' cannot be '{}' because it is not instantiated".format(
                            nsInstanceId, operation
                        ),
                        HTTPStatus.CONFLICT,
                    )
            else:
                if operation == "instantiate" and not session["force"]:
                    raise EngineException(
                        "ns_instance '{}' cannot be '{}' because it is already instantiated".format(
                            nsInstanceId, operation
                        ),
                        HTTPStatus.CONFLICT,
                    )
            self._check_ns_operation(session, nsr, operation, indata)
            if indata.get("primitive_params"):
                indata["primitive_params"] = json.dumps(indata["primitive_params"])
            elif indata.get("additionalParamsForVnf"):
                indata["additionalParamsForVnf"] = json.dumps(
                    indata["additionalParamsForVnf"]
                )

            if operation == "instantiate":
                self._update_vnfrs_from_nsd(nsr)
                self._update_vnfrs(session, rollback, nsr, indata)
            if (operation == "update") and (indata["updateType"] == "CHANGE_VNFPKG"):
                nsr_update = {}
                vnfd_id = indata["changeVnfPackageData"]["vnfdId"]
                vnfd = self.db.get_one("vnfds", {"_id": vnfd_id})
                nsd = self.db.get_one("nsds", {"_id": nsr["nsd-id"]})
                ns_request = nsr["instantiate_params"]
                vnfr = self.db.get_one(
                    "vnfrs", {"_id": indata["changeVnfPackageData"]["vnfInstanceId"]}
                )
                latest_vnfd_revision = vnfd["_admin"].get("revision", 1)
                vnfr_vnfd_revision = vnfr.get("revision", 1)
                if latest_vnfd_revision != vnfr_vnfd_revision:
                    old_vnfd_id = vnfd_id + ":" + str(vnfr_vnfd_revision)
                    old_db_vnfd = self.db.get_one(
                        "vnfds_revisions", {"_id": old_vnfd_id}
                    )
                    old_sw_version = old_db_vnfd.get("software-version", "1.0")
                    new_sw_version = vnfd.get("software-version", "1.0")
                    if new_sw_version != old_sw_version:
                        vnf_index = vnfr["member-vnf-index-ref"]
                        for vdu in vnfd.get("vdu", []):
                            self.nsrtopic._add_shared_volumes_to_nsr(
                                vdu, vnfd, nsr, vnf_index, latest_vnfd_revision
                            )
                            self.nsrtopic._add_flavor_to_nsr(
                                vdu, vnfd, nsr, vnf_index, latest_vnfd_revision
                            )
                            sw_image_id = vdu.get("sw-image-desc")
                            if sw_image_id:
                                image_data = self.nsrtopic._get_image_data_from_vnfd(
                                    vnfd, sw_image_id
                                )
                                self.nsrtopic._add_image_to_nsr(nsr, image_data)
                            for alt_image in vdu.get("alternative-sw-image-desc", ()):
                                image_data = self.nsrtopic._get_image_data_from_vnfd(
                                    vnfd, alt_image
                                )
                                self.nsrtopic._add_image_to_nsr(nsr, image_data)
                        nsr_update["image"] = nsr["image"]
                        nsr_update["flavor"] = nsr["flavor"]
                        nsr_update["shared-volumes"] = nsr["shared-volumes"]
                        self.db.set_one("nsrs", {"_id": nsr["_id"]}, nsr_update)
                        ns_k8s_namespace = self.nsrtopic._get_ns_k8s_namespace(
                            nsd, ns_request, session
                        )
                        vnfr_descriptor = (
                            self.nsrtopic._create_vnfr_descriptor_from_vnfd(
                                nsd,
                                vnfd,
                                vnfd_id,
                                vnf_index,
                                nsr,
                                ns_request,
                                ns_k8s_namespace,
                                latest_vnfd_revision,
                            )
                        )
                        self._update_vnfrs_from_nsd(nsr)
                        vnfr_new = self.db.get_one(
                            "vnfrs",
                            {"_id": indata["changeVnfPackageData"]["vnfInstanceId"]},
                        )
                        fixed_ip_dict = {}
                        for vdu_record in vnfr_new.get("vdur"):
                            if vdu_record.get("count-index") == 0:
                                for interface in vdu_record.get("interfaces"):
                                    if (
                                        interface.get("external-connection-point-ref")
                                        and interface.get("fixed-ip") is True
                                    ):
                                        fixed_ip_dict[
                                            vdu_record.get("vdu-id-ref")
                                        ] = interface.get("ip-address")
                        for new_vdu in vnfr_descriptor.get("vdur"):
                            if fixed_ip_dict.get(new_vdu.get("vdu-id-ref")):
                                for new_interface in new_vdu.get("interfaces"):
                                    if new_interface.get(
                                        "external-connection-point-ref"
                                    ):
                                        new_interface["ip-address"] = fixed_ip_dict.get(
                                            new_vdu.get("vdu-id-ref")
                                        )
                                        new_interface["fixed-ip"] = True
                        indata["newVdur"] = vnfr_descriptor["vdur"]
            nslcmop_desc = self._create_nslcmop(nsInstanceId, operation, indata)
            _id = nslcmop_desc["_id"]
            nsName = nsr.get("name")
            self.format_on_new(
                nslcmop_desc, session["project_id"], make_public=session["public"]
            )
            if indata.get("placement-engine"):
                # Save valid vim accounts in lcm operation descriptor
                nslcmop_desc["operationParams"][
                    "validVimAccounts"
                ] = self._get_enabled_vims(session)
            self.db.create("nslcmops", nslcmop_desc)
            rollback.append({"topic": "nslcmops", "_id": _id})
            if not slice_object:
                self.msg.write("ns", operation, nslcmop_desc)
            return _id, nsName, None
        except ValidationError as e:  # TODO remove try Except, it is captured at nbi.py
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)
        # except DbException as e:
        #     raise EngineException("Cannot get ns_instance '{}': {}".format(e), HTTPStatus.NOT_FOUND)

    def cancel(self, rollback, session, indata=None, kwargs=None, headers=None):
        validate_input(indata, self.operation_schema["cancel"])
        # Override descriptor with query string kwargs
        self._update_input_with_kwargs(indata, kwargs, yaml_format=True)
        nsLcmOpOccId = indata["nsLcmOpOccId"]
        cancelMode = indata["cancelMode"]
        # get nslcmop from nsLcmOpOccId
        _filter = BaseTopic._get_project_filter(session)
        _filter["_id"] = nsLcmOpOccId
        nslcmop = self.db.get_one("nslcmops", _filter)
        # Fail is this is not an ongoing nslcmop
        if nslcmop.get("operationState") not in [
            "STARTING",
            "PROCESSING",
            "ROLLING_BACK",
        ]:
            raise EngineException(
                "Operation is not in STARTING, PROCESSING or ROLLING_BACK state",
                http_code=HTTPStatus.CONFLICT,
            )
        nsInstanceId = nslcmop["nsInstanceId"]
        update_dict = {
            "isCancelPending": True,
            "cancelMode": cancelMode,
        }
        self.db.set_one(
            "nslcmops", q_filter=_filter, update_dict=update_dict, fail_on_empty=False
        )
        data = {
            "_id": nsLcmOpOccId,
            "nsInstanceId": nsInstanceId,
            "cancelMode": cancelMode,
        }
        self.msg.write("nslcmops", "cancel", data)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        raise EngineException(
            "Method delete called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method edit called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )


class NsiTopic(BaseTopic):
    topic = "nsis"
    topic_msg = "nsi"
    quota_name = "slice_instances"

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)
        self.nsrTopic = NsrTopic(db, fs, msg, auth)

    @staticmethod
    def _format_ns_request(ns_request):
        formated_request = copy(ns_request)
        # TODO: Add request params
        return formated_request

    @staticmethod
    def _format_addional_params(slice_request):
        """
        Get and format user additional params for NS or VNF
        :param slice_request: User instantiation additional parameters
        :return: a formatted copy of additional params or None if not supplied
        """
        additional_params = copy(slice_request.get("additionalParamsForNsi"))
        if additional_params:
            for k, v in additional_params.items():
                if not isinstance(k, str):
                    raise EngineException(
                        "Invalid param at additionalParamsForNsi:{}. Only string keys are allowed".format(
                            k
                        )
                    )
                if "." in k or "$" in k:
                    raise EngineException(
                        "Invalid param at additionalParamsForNsi:{}. Keys must not contain dots or $".format(
                            k
                        )
                    )
                if isinstance(v, (dict, tuple, list)):
                    additional_params[k] = "!!yaml " + safe_dump(v)
        return additional_params

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that NSI is not instantiated
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: nsi internal id
        :param db_content: The database content of the _id
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return
        nsi = db_content
        if nsi["_admin"].get("nsiState") == "INSTANTIATED":
            raise EngineException(
                "nsi '{}' cannot be deleted because it is in 'INSTANTIATED' state. "
                "Launch 'terminate' operation first; or force deletion".format(_id),
                http_code=HTTPStatus.CONFLICT,
            )

    def delete_extra(self, session, _id, db_content, not_send_msg=None):
        """
        Deletes associated nsilcmops from database. Deletes associated filesystem.
         Set usageState of nst
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param db_content: The database content of the descriptor
        :param not_send_msg: To not send message (False) or store content (list) instead
        :return: None if ok or raises EngineException with the problem
        """

        # Deleting the nsrs belonging to nsir
        nsir = db_content
        for nsrs_detailed_item in nsir["_admin"]["nsrs-detailed-list"]:
            nsr_id = nsrs_detailed_item["nsrId"]
            if nsrs_detailed_item.get("shared"):
                _filter = {
                    "_admin.nsrs-detailed-list.ANYINDEX.shared": True,
                    "_admin.nsrs-detailed-list.ANYINDEX.nsrId": nsr_id,
                    "_id.ne": nsir["_id"],
                }
                nsi = self.db.get_one(
                    "nsis", _filter, fail_on_empty=False, fail_on_more=False
                )
                if nsi:  # last one using nsr
                    continue
            try:
                self.nsrTopic.delete(
                    session, nsr_id, dry_run=False, not_send_msg=not_send_msg
                )
            except (DbException, EngineException) as e:
                if e.http_code == HTTPStatus.NOT_FOUND:
                    pass
                else:
                    raise

        # delete related nsilcmops database entries
        self.db.del_list("nsilcmops", {"netsliceInstanceId": _id})

        # Check and set used NST usage state
        nsir_admin = nsir.get("_admin")
        if nsir_admin and nsir_admin.get("nst-id"):
            # check if used by another NSI
            nsis_list = self.db.get_one(
                "nsis",
                {"nst-id": nsir_admin["nst-id"]},
                fail_on_empty=False,
                fail_on_more=False,
            )
            if not nsis_list:
                self.db.set_one(
                    "nsts",
                    {"_id": nsir_admin["nst-id"]},
                    {"_admin.usageState": "NOT_IN_USE"},
                )

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates a new netslice instance record into database. It also creates needed nsrs and vnfrs
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the nsir
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: the _id of nsi descriptor created at database
        """

        step = "checking quotas"  # first step must be defined outside try
        try:
            self.check_quota(session)

            step = ""
            slice_request = self._remove_envelop(indata)
            # Override descriptor with query string kwargs
            self._update_input_with_kwargs(slice_request, kwargs)
            slice_request = self._validate_input_new(slice_request, session["force"])

            # look for nstd
            step = "getting nstd id='{}' from database".format(
                slice_request.get("nstId")
            )
            _filter = self._get_project_filter(session)
            _filter["_id"] = slice_request["nstId"]
            nstd = self.db.get_one("nsts", _filter)
            # check NST is not disabled
            step = "checking NST operationalState"
            if nstd["_admin"]["operationalState"] == "DISABLED":
                raise EngineException(
                    "nst with id '{}' is DISABLED, and thus cannot be used to create a netslice "
                    "instance".format(slice_request["nstId"]),
                    http_code=HTTPStatus.CONFLICT,
                )
            del _filter["_id"]

            # check NSD is not disabled
            step = "checking operationalState"
            if nstd["_admin"]["operationalState"] == "DISABLED":
                raise EngineException(
                    "nst with id '{}' is DISABLED, and thus cannot be used to create "
                    "a network slice".format(slice_request["nstId"]),
                    http_code=HTTPStatus.CONFLICT,
                )

            nstd.pop("_admin", None)
            nstd_id = nstd.pop("_id", None)
            nsi_id = str(uuid4())
            step = "filling nsi_descriptor with input data"

            # Creating the NSIR
            nsi_descriptor = {
                "id": nsi_id,
                "name": slice_request["nsiName"],
                "description": slice_request.get("nsiDescription", ""),
                "datacenter": slice_request["vimAccountId"],
                "nst-ref": nstd["id"],
                "instantiation_parameters": slice_request,
                "network-slice-template": nstd,
                "nsr-ref-list": [],
                "vlr-list": [],
                "_id": nsi_id,
                "additionalParamsForNsi": self._format_addional_params(slice_request),
            }

            step = "creating nsi at database"
            self.format_on_new(
                nsi_descriptor, session["project_id"], make_public=session["public"]
            )
            nsi_descriptor["_admin"]["nsiState"] = "NOT_INSTANTIATED"
            nsi_descriptor["_admin"]["netslice-subnet"] = None
            nsi_descriptor["_admin"]["deployed"] = {}
            nsi_descriptor["_admin"]["deployed"]["RO"] = []
            nsi_descriptor["_admin"]["nst-id"] = nstd_id

            # Creating netslice-vld for the RO.
            step = "creating netslice-vld at database"

            # Building the vlds list to be deployed
            # From netslice descriptors, creating the initial list
            nsi_vlds = []

            for netslice_vlds in get_iterable(nstd.get("netslice-vld")):
                # Getting template Instantiation parameters from NST
                nsi_vld = deepcopy(netslice_vlds)
                nsi_vld["shared-nsrs-list"] = []
                nsi_vld["vimAccountId"] = slice_request["vimAccountId"]
                nsi_vlds.append(nsi_vld)

            nsi_descriptor["_admin"]["netslice-vld"] = nsi_vlds
            # Creating netslice-subnet_record.
            needed_nsds = {}
            services = []

            # Updating the nstd with the nsd["_id"] associated to the nss -> services list
            for member_ns in nstd["netslice-subnet"]:
                nsd_id = member_ns["nsd-ref"]
                step = "getting nstd id='{}' constituent-nsd='{}' from database".format(
                    member_ns["nsd-ref"], member_ns["id"]
                )
                if nsd_id not in needed_nsds:
                    # Obtain nsd
                    _filter["id"] = nsd_id
                    nsd = self.db.get_one(
                        "nsds", _filter, fail_on_empty=True, fail_on_more=True
                    )
                    del _filter["id"]
                    nsd.pop("_admin")
                    needed_nsds[nsd_id] = nsd
                else:
                    nsd = needed_nsds[nsd_id]
                member_ns["_id"] = needed_nsds[nsd_id].get("_id")
                services.append(member_ns)

                step = "filling nsir nsd-id='{}' constituent-nsd='{}' from database".format(
                    member_ns["nsd-ref"], member_ns["id"]
                )

            # creates Network Services records (NSRs)
            step = "creating nsrs at database using NsrTopic.new()"
            ns_params = slice_request.get("netslice-subnet")
            nsrs_list = []
            nsi_netslice_subnet = []
            for service in services:
                # Check if the netslice-subnet is shared and if it is share if the nss exists
                _id_nsr = None
                indata_ns = {}
                # Is the nss shared and instantiated?
                _filter["_admin.nsrs-detailed-list.ANYINDEX.shared"] = True
                _filter["_admin.nsrs-detailed-list.ANYINDEX.nsd-id"] = service[
                    "nsd-ref"
                ]
                _filter["_admin.nsrs-detailed-list.ANYINDEX.nss-id"] = service["id"]
                nsi = self.db.get_one(
                    "nsis", _filter, fail_on_empty=False, fail_on_more=False
                )
                if nsi and service.get("is-shared-nss"):
                    nsrs_detailed_list = nsi["_admin"]["nsrs-detailed-list"]
                    for nsrs_detailed_item in nsrs_detailed_list:
                        if nsrs_detailed_item["nsd-id"] == service["nsd-ref"]:
                            if nsrs_detailed_item["nss-id"] == service["id"]:
                                _id_nsr = nsrs_detailed_item["nsrId"]
                                break
                    for netslice_subnet in nsi["_admin"]["netslice-subnet"]:
                        if netslice_subnet["nss-id"] == service["id"]:
                            indata_ns = netslice_subnet
                            break
                else:
                    indata_ns = {}
                    if service.get("instantiation-parameters"):
                        indata_ns = deepcopy(service["instantiation-parameters"])
                        # del service["instantiation-parameters"]

                    indata_ns["nsdId"] = service["_id"]
                    indata_ns["nsName"] = (
                        slice_request.get("nsiName") + "." + service["id"]
                    )
                    indata_ns["vimAccountId"] = slice_request.get("vimAccountId")
                    indata_ns["nsDescription"] = service["description"]
                    if slice_request.get("ssh_keys"):
                        indata_ns["ssh_keys"] = slice_request.get("ssh_keys")

                    if ns_params:
                        for ns_param in ns_params:
                            if ns_param.get("id") == service["id"]:
                                copy_ns_param = deepcopy(ns_param)
                                del copy_ns_param["id"]
                                indata_ns.update(copy_ns_param)
                                break

                    # Creates Nsr objects
                    _id_nsr, _ = self.nsrTopic.new(
                        rollback, session, indata_ns, kwargs, headers
                    )
                nsrs_item = {
                    "nsrId": _id_nsr,
                    "shared": service.get("is-shared-nss"),
                    "nsd-id": service["nsd-ref"],
                    "nss-id": service["id"],
                    "nslcmop_instantiate": None,
                }
                indata_ns["nss-id"] = service["id"]
                nsrs_list.append(nsrs_item)
                nsi_netslice_subnet.append(indata_ns)
                nsr_ref = {"nsr-ref": _id_nsr}
                nsi_descriptor["nsr-ref-list"].append(nsr_ref)

            # Adding the nsrs list to the nsi
            nsi_descriptor["_admin"]["nsrs-detailed-list"] = nsrs_list
            nsi_descriptor["_admin"]["netslice-subnet"] = nsi_netslice_subnet
            self.db.set_one(
                "nsts", {"_id": slice_request["nstId"]}, {"_admin.usageState": "IN_USE"}
            )

            # Creating the entry in the database
            self.db.create("nsis", nsi_descriptor)
            rollback.append({"topic": "nsis", "_id": nsi_id})
            return nsi_id, None
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)
        except Exception as e:  # TODO remove try Except, it is captured at nbi.py
            # self.logger.exception(
            #    "Exception {} at NsiTopic.new()".format(e), exc_info=True
            # )
            raise EngineException("Error {}: {}".format(step, e))

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method edit called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )


class NsiLcmOpTopic(BaseTopic):
    topic = "nsilcmops"
    topic_msg = "nsi"
    operation_schema = {  # mapping between operation and jsonschema to validate
        "instantiate": nsi_instantiate,
        "terminate": None,
    }

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)
        self.nsi_NsLcmOpTopic = NsLcmOpTopic(self.db, self.fs, self.msg, self.auth)

    def _check_nsi_operation(self, session, nsir, operation, indata):
        """
        Check that user has enter right parameters for the operation
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param operation: it can be: instantiate, terminate, action, TODO: update, heal
        :param indata: descriptor with the parameters of the operation
        :return: None
        """
        nsds = {}
        nstd = nsir["network-slice-template"]

        def check_valid_netslice_subnet_id(nstId):
            # TODO change to vnfR (??)
            for netslice_subnet in nstd["netslice-subnet"]:
                if nstId == netslice_subnet["id"]:
                    nsd_id = netslice_subnet["nsd-ref"]
                    if nsd_id not in nsds:
                        _filter = self._get_project_filter(session)
                        _filter["id"] = nsd_id
                        nsds[nsd_id] = self.db.get_one("nsds", _filter)
                    return nsds[nsd_id]
            else:
                raise EngineException(
                    "Invalid parameter nstId='{}' is not one of the "
                    "nst:netslice-subnet".format(nstId)
                )

        if operation == "instantiate":
            # check the existance of netslice-subnet items
            for in_nst in get_iterable(indata.get("netslice-subnet")):
                check_valid_netslice_subnet_id(in_nst["id"])

    def _create_nsilcmop(self, session, netsliceInstanceId, operation, params):
        now = time()
        _id = str(uuid4())
        nsilcmop = {
            "id": _id,
            "_id": _id,
            "operationState": "PROCESSING",  # COMPLETED,PARTIALLY_COMPLETED,FAILED_TEMP,FAILED,ROLLING_BACK,ROLLED_BACK
            "statusEnteredTime": now,
            "netsliceInstanceId": netsliceInstanceId,
            "lcmOperationType": operation,
            "startTime": now,
            "isAutomaticInvocation": False,
            "operationParams": params,
            "isCancelPending": False,
            "links": {
                "self": "/osm/nsilcm/v1/nsi_lcm_op_occs/" + _id,
                "netsliceInstanceId": "/osm/nsilcm/v1/netslice_instances/"
                + netsliceInstanceId,
            },
        }
        return nsilcmop

    def add_shared_nsr_2vld(self, nsir, nsr_item):
        for nst_sb_item in nsir["network-slice-template"].get("netslice-subnet"):
            if nst_sb_item.get("is-shared-nss"):
                for admin_subnet_item in nsir["_admin"].get("netslice-subnet"):
                    if admin_subnet_item["nss-id"] == nst_sb_item["id"]:
                        for admin_vld_item in nsir["_admin"].get("netslice-vld"):
                            for admin_vld_nss_cp_ref_item in admin_vld_item[
                                "nss-connection-point-ref"
                            ]:
                                if (
                                    admin_subnet_item["nss-id"]
                                    == admin_vld_nss_cp_ref_item["nss-ref"]
                                ):
                                    if (
                                        not nsr_item["nsrId"]
                                        in admin_vld_item["shared-nsrs-list"]
                                    ):
                                        admin_vld_item["shared-nsrs-list"].append(
                                            nsr_item["nsrId"]
                                        )
                                    break
        # self.db.set_one("nsis", {"_id": nsir["_id"]}, nsir)
        self.db.set_one(
            "nsis",
            {"_id": nsir["_id"]},
            {"_admin.netslice-vld": nsir["_admin"].get("netslice-vld")},
        )

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Performs a new operation over a ns
        :param rollback: list to append created items at database in case a rollback must to be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: descriptor with the parameters of the operation. It must contains among others
            netsliceInstanceId: _id of the nsir to perform the operation
            operation: it can be: instantiate, terminate, action, TODO: update, heal
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: id of the nslcmops
        """
        try:
            # Override descriptor with query string kwargs
            self._update_input_with_kwargs(indata, kwargs)
            operation = indata["lcmOperationType"]
            netsliceInstanceId = indata["netsliceInstanceId"]
            validate_input(indata, self.operation_schema[operation])

            # get nsi from netsliceInstanceId
            _filter = self._get_project_filter(session)
            _filter["_id"] = netsliceInstanceId
            nsir = self.db.get_one("nsis", _filter)
            # logging_prefix = "nsi={} {} ".format(netsliceInstanceId, operation)
            del _filter["_id"]

            # initial checking
            if (
                not nsir["_admin"].get("nsiState")
                or nsir["_admin"]["nsiState"] == "NOT_INSTANTIATED"
            ):
                if operation == "terminate" and indata.get("autoremove"):
                    # NSIR must be deleted
                    return (
                        None,
                        None,
                    )  # a none in this case is used to indicate not instantiated. It can be removed
                if operation != "instantiate":
                    raise EngineException(
                        "netslice_instance '{}' cannot be '{}' because it is not instantiated".format(
                            netsliceInstanceId, operation
                        ),
                        HTTPStatus.CONFLICT,
                    )
            else:
                if operation == "instantiate" and not session["force"]:
                    raise EngineException(
                        "netslice_instance '{}' cannot be '{}' because it is already instantiated".format(
                            netsliceInstanceId, operation
                        ),
                        HTTPStatus.CONFLICT,
                    )

            # Creating all the NS_operation (nslcmop)
            # Get service list from db
            nsrs_list = nsir["_admin"]["nsrs-detailed-list"]
            nslcmops = []
            # nslcmops_item = None
            for index, nsr_item in enumerate(nsrs_list):
                nsr_id = nsr_item["nsrId"]
                if nsr_item.get("shared"):
                    _filter["_admin.nsrs-detailed-list.ANYINDEX.shared"] = True
                    _filter["_admin.nsrs-detailed-list.ANYINDEX.nsrId"] = nsr_id
                    _filter[
                        "_admin.nsrs-detailed-list.ANYINDEX.nslcmop_instantiate.ne"
                    ] = None
                    _filter["_id.ne"] = netsliceInstanceId
                    nsi = self.db.get_one(
                        "nsis", _filter, fail_on_empty=False, fail_on_more=False
                    )
                    if operation == "terminate":
                        _update = {
                            "_admin.nsrs-detailed-list.{}.nslcmop_instantiate".format(
                                index
                            ): None
                        }
                        self.db.set_one("nsis", {"_id": nsir["_id"]}, _update)
                        if (
                            nsi
                        ):  # other nsi is using this nsr and it needs this nsr instantiated
                            continue  # do not create nsilcmop
                    else:  # instantiate
                        # looks the first nsi fulfilling the conditions but not being the current NSIR
                        if nsi:
                            nsi_nsr_item = next(
                                n
                                for n in nsi["_admin"]["nsrs-detailed-list"]
                                if n["nsrId"] == nsr_id
                                and n["shared"]
                                and n["nslcmop_instantiate"]
                            )
                            self.add_shared_nsr_2vld(nsir, nsr_item)
                            nslcmops.append(nsi_nsr_item["nslcmop_instantiate"])
                            _update = {
                                "_admin.nsrs-detailed-list.{}".format(
                                    index
                                ): nsi_nsr_item
                            }
                            self.db.set_one("nsis", {"_id": nsir["_id"]}, _update)
                            # continue to not create nslcmop since nsrs is shared and nsrs was created
                            continue
                        else:
                            self.add_shared_nsr_2vld(nsir, nsr_item)

                # create operation
                try:
                    indata_ns = {
                        "lcmOperationType": operation,
                        "nsInstanceId": nsr_id,
                        # Including netslice_id in the ns instantiate Operation
                        "netsliceInstanceId": netsliceInstanceId,
                    }
                    if operation == "instantiate":
                        service = self.db.get_one("nsrs", {"_id": nsr_id})
                        indata_ns.update(service["instantiate_params"])

                    # Creating NS_LCM_OP with the flag slice_object=True to not trigger the service instantiation
                    # message via kafka bus
                    nslcmop, _, _ = self.nsi_NsLcmOpTopic.new(
                        rollback, session, indata_ns, None, headers, slice_object=True
                    )
                    nslcmops.append(nslcmop)
                    if operation == "instantiate":
                        _update = {
                            "_admin.nsrs-detailed-list.{}.nslcmop_instantiate".format(
                                index
                            ): nslcmop
                        }
                        self.db.set_one("nsis", {"_id": nsir["_id"]}, _update)
                except (DbException, EngineException) as e:
                    if e.http_code == HTTPStatus.NOT_FOUND:
                        pass
                    else:
                        raise

            # Creates nsilcmop
            indata["nslcmops_ids"] = nslcmops
            self._check_nsi_operation(session, nsir, operation, indata)

            nsilcmop_desc = self._create_nsilcmop(
                session, netsliceInstanceId, operation, indata
            )
            self.format_on_new(
                nsilcmop_desc, session["project_id"], make_public=session["public"]
            )
            _id = self.db.create("nsilcmops", nsilcmop_desc)
            rollback.append({"topic": "nsilcmops", "_id": _id})
            self.msg.write("nsi", operation, nsilcmop_desc)
            return _id, None
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        raise EngineException(
            "Method delete called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method edit called directly", HTTPStatus.INTERNAL_SERVER_ERROR
        )
