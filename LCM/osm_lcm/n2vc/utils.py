# Copyright 2020 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import base64
import re
import binascii
import yaml
import string
import secrets
from enum import Enum
from juju.machine import Machine
from juju.application import Application
from juju.action import Action
from juju.unit import Unit
from osm_lcm.n2vc.exceptions import N2VCInvalidCertificate
from typing import Tuple


def base64_to_cacert(b64string):
    """Convert the base64-encoded string containing the VCA CACERT.

    The input string....

    """
    try:
        cacert = base64.b64decode(b64string).decode("utf-8")

        cacert = re.sub(
            r"\\n",
            r"\n",
            cacert,
        )
    except binascii.Error as e:
        raise N2VCInvalidCertificate(message="Invalid CA Certificate: {}".format(e))

    return cacert


class N2VCDeploymentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Dict(dict):
    """
    Dict class that allows to access the keys like attributes
    """

    def __getattribute__(self, name):
        if name in self:
            return self[name]


class EntityType(Enum):
    MACHINE = Machine
    APPLICATION = Application
    ACTION = Action
    UNIT = Unit

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_  # pylint: disable=E1101

    @classmethod
    def get_entity(cls, value):
        return (
            cls._value2member_map_[value]  # pylint: disable=E1101
            if value in cls._value2member_map_  # pylint: disable=E1101
            else None  # pylint: disable=E1101
        )

    @classmethod
    def get_entity_from_delta(cls, delta_entity: str):
        """
        Get Value from delta entity

        :param: delta_entity: Possible values are "machine", "application", "unit", "action"
        """
        for v in cls._value2member_map_:  # pylint: disable=E1101
            if v.__name__.lower() == delta_entity:
                return cls.get_entity(v)


JujuStatusToOSM = {
    "machine": {
        "pending": N2VCDeploymentStatus.PENDING,
        "started": N2VCDeploymentStatus.COMPLETED,
    },
    "application": {
        "waiting": N2VCDeploymentStatus.RUNNING,
        "maintenance": N2VCDeploymentStatus.RUNNING,
        "blocked": N2VCDeploymentStatus.RUNNING,
        "error": N2VCDeploymentStatus.FAILED,
        "active": N2VCDeploymentStatus.COMPLETED,
    },
    "action": {
        "pending": N2VCDeploymentStatus.PENDING,
        "running": N2VCDeploymentStatus.RUNNING,
        "completed": N2VCDeploymentStatus.COMPLETED,
    },
    "unit": {
        "waiting": N2VCDeploymentStatus.RUNNING,
        "maintenance": N2VCDeploymentStatus.RUNNING,
        "blocked": N2VCDeploymentStatus.RUNNING,
        "error": N2VCDeploymentStatus.FAILED,
        "active": N2VCDeploymentStatus.COMPLETED,
    },
}


def obj_to_yaml(obj: object) -> str:
    """
    Converts object to yaml format
    :return: yaml data
    """
    # dump to yaml
    dump_text = yaml.dump(obj, default_flow_style=False, indent=2)
    # split lines
    lines = dump_text.splitlines()
    # remove !!python/object tags
    yaml_text = ""
    for line in lines:
        index = line.find("!!python/object")
        if index >= 0:
            line = line[:index]
        yaml_text += line + "\n"
    return yaml_text


def obj_to_dict(obj: object) -> dict:
    """
    Converts object to dictionary format
    :return: dict data
    """
    # convert obj to yaml
    yaml_text = obj_to_yaml(obj)
    # parse to dict
    return yaml.load(yaml_text, Loader=yaml.SafeLoader)


def get_ee_id_components(ee_id: str) -> Tuple[str, str, str]:
    """
    Get model, application and machine components from an execution environment id
    :param ee_id:
    :return: model_name, application_name, machine_id
    """
    parts = ee_id.split(".")
    if len(parts) != 3:
        raise Exception("invalid ee id.")
    model_name = parts[0]
    application_name = parts[1]
    machine_id = parts[2]
    return model_name, application_name, machine_id


def generate_random_alfanum_string(size: int) -> str:
    """
    Generate random alfa-numeric string with a size given by argument
    :param size:
    :return: random generated string
    """

    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for i in range(size)
    )
