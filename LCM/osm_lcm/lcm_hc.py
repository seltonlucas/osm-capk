#!/usr/bin/python3
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

from time import time, sleep
from sys import stderr

from osm_lcm.lcm_utils import LcmException
import yaml

""" This module is used for health check. A file called time_last_ping is used
This contains the last time where something is received from kafka
"""


def get_health_check_file(config_file=None):
    try:
        health_check_file = "/app/storage/time_last_ping"
        if not config_file:
            return health_check_file
        # If config_input is dictionary
        if isinstance(config_file, dict) and config_file.get("storage"):
            health_check_file = config_file["storage"]["path"] + "/time_last_ping"
        # If config_input is file
        elif isinstance(config_file, str):
            with open(config_file) as f:
                # read file as yaml format
                conf = yaml.safe_load(f)
                # Ensure all sections are not empty
                if conf.get("storage"):
                    health_check_file = conf["storage"]["path"] + "/time_last_ping"

        return health_check_file
    except (IOError, FileNotFoundError, TypeError, AttributeError, KeyError) as error:
        raise LcmException(
            f"Error occured while getting the health check file location: {error}"
        )


def health_check(config_file=None, ping_interval_pace=120):
    health_check_file = get_health_check_file(config_file)
    retry = 2
    while retry:
        retry -= 1
        try:
            with open(health_check_file, "r") as f:
                last_received_ping = f.read()

            if (
                time() - float(last_received_ping) < 2 * ping_interval_pace
            ):  # allow one ping not received every two
                exit(0)
        except Exception as e:
            print(e, file=stderr)
        if retry:
            sleep(6)
    exit(1)


if __name__ == "__main__":
    health_check()
