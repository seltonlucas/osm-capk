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

from osm_lcm.lcm_utils import get_iterable


def get_osm_params(db_vnfr, vdu_id=None, vdu_count_index=0):
    osm_params = {
        x.replace("-", "_"): db_vnfr[x]
        for x in ("ip-address", "vim-account-id", "vnfd-id", "vnfd-ref")
        if db_vnfr.get(x) is not None
    }
    osm_params["ns_id"] = db_vnfr["nsr-id-ref"]
    osm_params["vnf_id"] = db_vnfr["_id"]
    osm_params["member_vnf_index"] = db_vnfr["member-vnf-index-ref"]
    if db_vnfr.get("vdur"):
        osm_params["vdu"] = {}
        for vdur in db_vnfr["vdur"]:
            vdu = {
                "count_index": vdur["count-index"],
                "vdu_id": vdur["vdu-id-ref"],
                "interfaces": {},
            }
            if vdur.get("ip-address"):
                vdu["ip_address"] = vdur["ip-address"]
            for iface in vdur["interfaces"]:
                vdu["interfaces"][iface["name"]] = {
                    x.replace("-", "_"): iface[x]
                    for x in ("mac-address", "ip-address", "name")
                    if iface.get(x) is not None
                }
            vdu_id_index = "{}-{}".format(vdur["vdu-id-ref"], vdur["count-index"])
            osm_params["vdu"][vdu_id_index] = vdu
        if vdu_id:
            osm_params["vdu_id"] = vdu_id
            osm_params["count_index"] = vdu_count_index
    return osm_params


def get_vdur_index(db_vnfr, vdu_delta):
    vdur_list = get_iterable(db_vnfr, "vdur")
    if vdur_list:
        return len([x for x in vdur_list if x.get("vdu-id-ref") == vdu_delta["id"]])
    else:
        return 0


def get_kdur(db_vnfr, kdu_name):
    kdur_list = get_iterable(db_vnfr, "kdur")
    if kdur_list:
        return next(x for x in kdur_list if x.get("kdu-name") == kdu_name)
    else:
        return None


def get_volumes_from_instantiation_params(
    vdu_instantiation_params: dict, vdud: dict
) -> list:
    """Get the VDU volumes from instantiation parameters

    Args:
        vdu_instantiation_params:   VDU instantiation parameters
        vdud:   VDU description as a dictionary extracted from VNFD
    Returns:
        vdu_volume_list:(list)

    """
    vdu_volume_list = []
    if vdu_instantiation_params.get("volume"):
        for volume in vdu_instantiation_params["volume"]:
            if volume.get("vim-volume-id") and volume.get("name") in vdud.get(
                "virtual-storage-desc"
            ):
                vdu_volume = {
                    "name": volume["name"],
                    "vim-volume-id": volume["vim-volume-id"],
                }
                vdu_volume_list.append(vdu_volume)

    return vdu_volume_list
