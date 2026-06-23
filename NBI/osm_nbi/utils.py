# -*- coding: utf-8 -*-

# Copyright 2020 Whitestack, LLC
# *************************************************************
#
# This file is part of OSM NBI module
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
# contact: fbravo@whitestack.com or agarcia@whitestack.com
##
from cefevent import CEFEvent
from osm_nbi import version


def find_in_list(the_list, condition_lambda):
    for item in the_list:
        if condition_lambda(item):
            return item
    else:
        return None


def filter_in_list(the_list, condition_lambda):
    ret = []
    for item in the_list:
        if condition_lambda(item):
            ret.append(item)
    return ret


def find_index_in_list(the_list, condition_lambda):
    for index, item in enumerate(the_list):
        if condition_lambda(item):
            return index
    else:
        return -1


def deep_update_dict(data, updated_data):
    if isinstance(data, list):
        processed_items_data = []
        for index, item in enumerate(data):
            processed_items_data.append(deep_update_dict(item, updated_data[index]))
        return processed_items_data

    if isinstance(data, dict):
        for key in data.keys():
            if key in updated_data:
                if not isinstance(data[key], dict) and not isinstance(data[key], list):
                    data[key] = updated_data[key]
                else:
                    data[key] = deep_update_dict(data[key], updated_data[key])
        return data

    return data


def cef_event(cef_logger, cef_fields):
    for key, value in cef_fields.items():
        cef_logger.set_field(key, value)


def cef_event_builder(config):
    cef_logger = CEFEvent()
    cef_fields = {
        "version": config["version"],
        "deviceVendor": config["deviceVendor"],
        "deviceProduct": config["deviceProduct"],
        "deviceVersion": get_version(),
        "message": "CEF Logger",
        "sourceUserName": "admin",
        "severity": 1,
    }
    cef_event(cef_logger, cef_fields)
    cef_logger.build_cef()
    return cef_logger


def get_version():
    osm_version = version.split("+")
    return osm_version[0]
