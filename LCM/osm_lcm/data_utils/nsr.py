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

from osm_lcm.data_utils import list_utils
from osm_lcm.lcm_utils import get_iterable


def get_deployed_kdu(nsr_deployed, kdu_name, member_vnf_index):
    deployed_kdu = None
    index = None
    for index, deployed_kdu in enumerate(get_iterable(nsr_deployed, "K8s")):
        if (
            kdu_name == deployed_kdu["kdu-name"]
            and deployed_kdu["member-vnf-index"] == member_vnf_index
        ):
            break
    return deployed_kdu, index


def get_nsd(nsr):
    return nsr.get("nsd", {})


def get_deployed_vca_list(nsr):
    return nsr.get("_admin", ()).get("deployed", ()).get("VCA", [])


def get_deployed_vca(nsr, filter):
    return list_utils.find_in_list(
        get_deployed_vca_list(nsr),
        lambda vca: all(vca[key] == value for key, value in filter.items()),
    )
