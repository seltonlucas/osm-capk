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


def get_vdu_list(vnfd):
    return vnfd.get("vdu", ())


def get_kdu_list(vnfd):
    return vnfd.get("kdu", ())


def get_kdu(vnfd, kdu_name):
    return list_utils.find_in_list(
        get_kdu_list(vnfd), lambda kdu: kdu["name"] == kdu_name
    )


def get_kdu_services(kdu):
    return kdu.get("service", [])


def get_ee_sorted_initial_config_primitive_list(
    primitive_list, vca_deployed, ee_descriptor_id
):
    """
    Generates a list of initial-config-primitive based on the list provided by the descriptor. It includes internal
    primitives as verify-ssh-credentials, or config when needed
    :param primitive_list: information of the descriptor
    :param vca_deployed: information of the deployed, needed for known if it is related to an NS, VNF, VDU and if
        this element contains a ssh public key
    :param ee_descriptor_id: execution environment descriptor id. It is the value of
        XXX_configuration.execution-environment-list.INDEX.id; it can be None
    :return: The modified list. Can ba an empty list, but always a list
    """
    primitive_list = primitive_list or []
    primitive_list = [
        p
        for p in primitive_list
        if p.get("execution-environment-ref", ee_descriptor_id) == ee_descriptor_id
    ]
    if primitive_list:
        primitive_list.sort(key=lambda val: int(val["seq"]))

    # look for primitive config, and get the position. None if not present
    config_position = None
    for index, primitive in enumerate(primitive_list):
        if primitive["name"] == "config":
            config_position = index
            break

    # for NS, add always a config primitive if not present (bug 874)
    if not vca_deployed["member-vnf-index"] and config_position is None:
        primitive_list.insert(0, {"name": "config", "parameter": []})
        config_position = 0
    # TODO revise if needed: for VNF/VDU add verify-ssh-credentials after config
    if (
        vca_deployed["member-vnf-index"]
        and config_position is not None
        and vca_deployed.get("ssh-public-key")
    ):
        primitive_list.insert(
            config_position + 1, {"name": "verify-ssh-credentials", "parameter": []}
        )
    return primitive_list


def get_ee_sorted_terminate_config_primitive_list(primitive_list, ee_descriptor_id):
    primitive_list = primitive_list or []
    primitive_list = [
        p
        for p in primitive_list
        if p.get("execution-environment-ref", ee_descriptor_id) == ee_descriptor_id
    ]
    if primitive_list:
        primitive_list.sort(key=lambda val: int(val["seq"]))
    return primitive_list


def get_vdu_profile(vnfd, vdu_profile_id):
    return list_utils.find_in_list(
        vnfd.get("df", ())[0]["vdu-profile"],
        lambda vdu_profile: vdu_profile["id"] == vdu_profile_id,
    )


def get_kdu_resource_profile(vnfd, kdu_profile_id):
    return list_utils.find_in_list(
        vnfd.get("df", ())[0]["kdu-resource-profile"],
        lambda kdu_profile: kdu_profile["id"] == kdu_profile_id,
    )


def get_configuration(vnfd, entity_id):
    lcm_ops_config = vnfd.get("df")[0].get("lcm-operations-configuration")
    if not lcm_ops_config:
        return None
    ops_vnf = lcm_ops_config.get("operate-vnf-op-config")
    if not ops_vnf:
        return None
    day12ops = ops_vnf.get("day1-2", [])
    return list_utils.find_in_list(
        day12ops, lambda configuration: configuration["id"] == entity_id
    )


def get_relation_list(vnfd, entity_id):
    return (get_configuration(vnfd, entity_id) or {}).get("relation", [])


def get_virtual_link_profiles(vnfd):
    return vnfd.get("df")[0].get("virtual-link-profile", ())


def get_vdu(vnfd, vdu_id):
    return list_utils.find_in_list(vnfd.get("vdu", ()), lambda vdu: vdu["id"] == vdu_id)


def get_vdu_index(vnfd, vdu_id):
    target_vdu = list_utils.find_in_list(
        vnfd.get("vdu", ()), lambda vdu: vdu["id"] == vdu_id
    )
    if target_vdu:
        return vnfd.get("vdu", ()).index(target_vdu)
    else:
        return -1


def get_scaling_aspect(vnfd):
    return vnfd.get("df", ())[0].get("scaling-aspect", ())


def get_number_of_instances(vnfd, vdu_id):
    return list_utils.find_in_list(
        vnfd.get("df", ())[0].get("instantiation-level", ())[0].get("vdu-level", ()),
        lambda a_vdu: a_vdu["vdu-id"] == vdu_id,
    ).get("number-of-instances", 1)


def get_juju_ee_ref(vnfd, entity_id):
    return list_utils.find_in_list(
        get_configuration(vnfd, entity_id).get("execution-environment-list", []),
        lambda ee: "juju" in ee,
    )


def get_helm_ee_ref(vnfd, entity_id):
    return list_utils.find_in_list(
        get_configuration(vnfd, entity_id).get("execution-environment-list", []),
        lambda ee: "helm-chart" in ee,
    )


def find_software_version(vnfd: dict) -> str:
    """Find the sotware version in the VNFD descriptors

    Args:
        vnfd (dict): Descriptor as a dictionary

    Returns:
        software-version (str)
    """

    default_sw_version = "1.0"

    if vnfd.get("vnfd"):
        vnfd = vnfd["vnfd"]

    if vnfd.get("software-version"):
        return vnfd["software-version"]

    else:
        return default_sw_version


def check_helm_ee_in_ns(db_vnfds: list) -> bool:
    for vnfd in db_vnfds:
        descriptor_config = get_configuration(vnfd, vnfd["id"])
        if not (
            descriptor_config and "execution-environment-list" in descriptor_config
        ):
            continue
        ee_list = descriptor_config.get("execution-environment-list", [])
        if list_utils.find_in_list(ee_list, lambda ee_item: "helm-chart" in ee_item):
            return True
