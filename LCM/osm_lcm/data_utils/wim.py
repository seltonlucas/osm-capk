# -*- coding: utf-8 -*-

# This file is part of OSM Life-Cycle Management module
#
# Copyright 2022 ETSI
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


from osm_lcm.data_utils.database.vim_account import VimAccountDB
from osm_lcm.data_utils.database.wim_account import WimAccountDB
from osm_lcm.data_utils.vim import get_vims_to_connect
from osm_lcm.lcm_utils import LcmException

__author__ = (
    "Lluis Gifre <lluis.gifre@cttc.es>, Ricard Vilalta <ricard.vilalta@cttc.es>"
)


def get_candidate_wims(vims_to_connect):
    all_wim_accounts = WimAccountDB.get_all_wim_accounts()
    candidate_wims = {}
    for wim_id, db_wim in all_wim_accounts.items():
        wim_port_mapping = db_wim.get("config", {}).get("wim_port_mapping", [])
        wim_dc_ids = {
            m.get("datacenter_id") for m in wim_port_mapping if m.get("datacenter_id")
        }
        not_reachable_vims = vims_to_connect.difference(wim_dc_ids)
        if len(not_reachable_vims) > 0:
            continue
        # TODO: consider adding other filtering fields such as supported layer(s) [L2, L3, ...]
        candidate_wims[wim_id] = db_wim
    return candidate_wims


def select_feasible_wim_account(db_nsr, db_vnfrs, target_vld, vld_params, logger):
    logger.info("Checking if WIM is needed for VLD({:s})...".format(str(target_vld)))
    if target_vld.get("mgmt-network", False):
        logger.info(
            "WIM not needed, VLD({:s}) is a management network".format(str(target_vld))
        )
        return None, None  # assume mgmt networks do not use a WIM

    # check if WIM account is explicitly False
    wim_account_id = vld_params.get("wimAccountId")
    if wim_account_id is not None and not wim_account_id:
        logger.info(
            "VLD({:s}) explicitly specifies not to use a WIM".format(str(target_vld))
        )
        return None, None  # WIM account explicitly set to False, do not use a WIM

    # find VIMs to be connected by VLD
    vims_to_connect = get_vims_to_connect(db_nsr, db_vnfrs, target_vld, logger)
    # check if we need a WIM to interconnect the VNFs in different VIMs
    if len(vims_to_connect) < 2:
        logger.info(
            "WIM not needed, VLD({:s}) does not involve multiple VIMs".format(
                str(target_vld)
            )
        )
        return None, None
    # if more than one VIM needs to be connected...
    logger.info(
        "WIM is needed, multiple VIMs to interconnect: {:s}".format(
            str(vims_to_connect)
        )
    )
    # find a WIM having these VIMs on its wim_port_mapping setting
    candidate_wims = get_candidate_wims(vims_to_connect)
    logger.info("Candidate WIMs: {:s}".format(str(candidate_wims)))

    # check if there are no WIM candidates
    if len(candidate_wims) == 0:
        logger.info("No WIM accounts found")
        return None, None

    # check if a desired wim_account_id is specified in vld_params
    wim_account_id = vld_params.get("wimAccountId")
    if wim_account_id:
        # check if the desired WIM account is feasible
        # implicitly checks if it exists in the DB
        db_wim = candidate_wims.get(wim_account_id)
        if db_wim:
            return wim_account_id, db_wim
        msg = (
            "WimAccountId specified in VldParams({:s}) cannot be used "
            "to connect the required VIMs({:s}). Candidate WIMs are: {:s}"
        )
        raise LcmException(
            msg.format(str(vld_params), str(vims_to_connect), str(candidate_wims))
        )

    # if multiple candidate WIMs: report error message
    if len(candidate_wims) > 1:
        msg = (
            "Multiple candidate WIMs found ({:s}) and wim_account not specified. "
            "Please, specify the WIM account to be used."
        )
        raise LcmException(msg.format(str(candidate_wims.keys())))

    # a single candidate WIM has been found, retrieve it
    return candidate_wims.popitem()  # returns tuple (wim_account_id, db_wim)


def get_target_wim_attrs(nsr_id, target_vld, vld_params):
    target_vims = [
        "vim:{:s}".format(vim_id) for vim_id in vld_params["vim-network-name"]
    ]
    wim_vld = "nsrs:{}:vld.{}".format(nsr_id, target_vld["id"])
    vld_type = target_vld.get("type")
    if vld_type is None:
        vld_type = "ELAN" if len(target_vims) > 2 else "ELINE"
    target_wim_attrs = {
        "sdn": True,
        "target_vims": target_vims,
        "vlds": [wim_vld],
        "type": vld_type,
    }
    return target_wim_attrs


def get_sdn_ports(vld_params, db_wim):
    if vld_params.get("provider-network"):
        # if SDN ports are specified in VLD params, use them
        return vld_params["provider-network"].get("sdn-ports")

    # otherwise, compose SDN ports required
    wim_port_mapping = db_wim.get("config", {}).get("wim_port_mapping", [])
    sdn_ports = []
    for vim_id in vld_params["vim-network-name"]:
        db_vim = VimAccountDB.get_vim_account_with_id(vim_id)
        vim_name = db_vim["name"]
        mapping = next(
            (m for m in wim_port_mapping if m["datacenter_id"] == vim_name),
            None,
        )
        if mapping is None:
            msg = "WIM({:s},{:s}) does not specify a mapping for VIM({:s},{:s})"
            raise LcmException(
                msg.format(
                    db_wim["name"],
                    db_wim["_id"],
                    db_vim["name"],
                    db_vim["_id"],
                )
            )
        sdn_port = {
            "device_id": vim_name,
            "switch_id": mapping.get("device_id"),
            "switch_port": mapping.get("device_interface_id"),
            "service_endpoint_id": mapping.get("service_endpoint_id"),
        }
        service_mapping_info = mapping.get("service_mapping_info", {})
        encapsulation = service_mapping_info.get("encapsulation", {})
        if encapsulation.get("type"):
            sdn_port["service_endpoint_encapsulation_type"] = encapsulation["type"]
        if encapsulation.get("vlan"):
            sdn_port["vlan"] = encapsulation["vlan"]
        sdn_ports.append(sdn_port)
    return sdn_ports
