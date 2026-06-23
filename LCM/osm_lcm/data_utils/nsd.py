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

from osm_lcm.data_utils.list_utils import find_in_list


def get_vnf_profiles(nsd):
    return nsd.get("df")[0].get("vnf-profile", ())


def get_vnf_profile(nsd, vnf_profile_id):
    return find_in_list(
        get_vnf_profiles(nsd),
        lambda vnf_profile: vnf_profile["id"] == vnf_profile_id,
    )


def get_virtual_link_profiles(nsd):
    return nsd.get("df")[0].get("virtual-link-profile", ())


def get_ns_configuration(nsd):
    return nsd.get("ns-configuration", {})


def get_ns_configuration_relation_list(nsd):
    return get_ns_configuration(nsd).get("relation", [])
