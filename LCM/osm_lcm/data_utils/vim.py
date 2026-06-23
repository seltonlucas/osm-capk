# -*- coding: utf-8 -*-

# Copyright 2020 Whitestack, LLC
# *************************************************************
#
# This file is part of OSM Monitoring module
# All Rights Reserved to Whitestack, LLC
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
# For those usages not covered by the Apache License, Version 2.0 please
# contact: fbravo@whitestack.com
##

from osm_lcm.data_utils.database.vim_account import VimAccountDB

__author__ = (
    "Lluis Gifre <lluis.gifre@cttc.es>, Ricard Vilalta <ricard.vilalta@cttc.es>"
)


def get_vims_to_connect(db_nsr, db_vnfrs, target_vld, logger):
    vims_to_connect = set()
    vld = next(
        (vld for vld in db_nsr["vld"] if vld["id"] == target_vld["id"]),
        None,
    )
    if vld is None:
        return vims_to_connect  # VLD not in NS, means it is an internal VLD within a single VIM

    vim_ids = set()
    if "vnfd-connection-point-ref" in vld:
        # during planning of VNF, use "vnfd-connection-point-ref" since "vim_info" is not available in vld
        # get VNFD connection points (if available)
        # iterate over VNFs and retrieve VIM IDs they are planned to be deployed to
        vnfd_connection_point_ref = vld["vnfd-connection-point-ref"]
        for vld_member_vnf_index_ref in vnfd_connection_point_ref:
            vld_member_vnf_index_ref = vld_member_vnf_index_ref["member-vnf-index-ref"]
            vim_ids.add(db_vnfrs[vld_member_vnf_index_ref]["vim-account-id"])
    elif "vim_info" in vld:
        # after instantiation of VNF, use "vim_info" since "vnfd-connection-point-ref" is not available in vld
        # get VIM info (if available)
        # iterate over VIM info and retrieve VIM IDs they are deployed to
        vim_info = vld["vim_info"]
        for vim_data in vim_info.values():
            vim_ids.add(vim_data["vim_account_id"])
    else:
        # TODO: analyze if this situation is possible
        # unable to retrieve planned/executed mapping of VNFs to VIMs
        # by now, drop a log message for future debugging
        logger.warning(
            " ".join(
                [
                    "Unable to identify VIMs involved in VLD to check if WIM is required.",
                    "Dumping internal variables for further debugging:",
                ]
            )
        )
        logger.warning("db_nsr={:s}".format(str(db_nsr)))
        logger.warning("db_vnfrs={:s}".format(str(db_vnfrs)))
        logger.warning("target_vld={:s}".format(str(target_vld)))
        return vims_to_connect

    for vim_id in vim_ids:
        db_vim = VimAccountDB.get_vim_account_with_id(vim_id)
        if db_vim is None:
            continue
        vims_to_connect.add(db_vim["name"])
    return vims_to_connect
