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

from jsonschema import validate as js_v, exceptions as js_e
from http import HTTPStatus
from copy import deepcopy
from uuid import UUID  # To test for valid UUID

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"
__version__ = "0.1"
version_date = "Mar 2018"

"""
Validator of input data using JSON schemas for those items that not contains an  OSM yang information model
"""

# Basis schemas
patern_name = "^[ -~]+$"
shortname_schema = {
    "type": "string",
    "minLength": 1,
    "maxLength": 60,
    "pattern": "^[^,;()\\.\\$'\"]+$",
}
passwd_schema = {"type": "string", "minLength": 1, "maxLength": 60}
user_passwd_schema = {
    "type": "string",
    "pattern": "^.*(?=.{8,})((?=.*[!@#$%^&*()\\-_=+{};:,<.>]){1})(?=.*\\d)((?=.*[a-z]){1})((?=.*[A-Z]){1}).*$",
}
name_schema = {
    "type": "string",
    "minLength": 1,
    "maxLength": 255,
    "pattern": "^[^,;()'\"]+$",
}
string_schema = {"type": "string", "minLength": 1, "maxLength": 255}
email_schema = {
    "type": "string",
    "minLength": 1,
    "maxLength": 320,
    "pattern": "^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$",
}
xml_text_schema = {
    "type": "string",
    "minLength": 1,
    "maxLength": 1000,
    "pattern": "^[^']+$",
}
description_schema = {
    "type": ["string", "null"],
    "maxLength": 255,
    "pattern": "^[^'\"]+$",
}
long_description_schema = {
    "type": ["string", "null"],
    "maxLength": 3000,
    "pattern": "^[^'\"]+$",
}
id_schema_fake = {"type": "string", "minLength": 2, "maxLength": 36}
bool_schema = {"type": "boolean"}
null_schema = {"type": "null"}
# "pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
id_schema = {
    "type": "string",
    "pattern": "^[a-fA-F0-9]{8}(-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$",
}
time_schema = {
    "type": "string",
    "pattern": "^[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]([0-5]:){2}",
}
pci_schema = {
    "type": "string",
    "pattern": "^[0-9a-fA-F]{4}(:[0-9a-fA-F]{2}){2}\\.[0-9a-fA-F]$",
}
# allows [] for wildcards. For that reason huge length limit is set
pci_extended_schema = {"type": "string", "pattern": "^[0-9a-fA-F.:-\\[\\]]{12,40}$"}
http_schema = {"type": "string", "pattern": "^(https?|http)://[^'\"=]+$"}
bandwidth_schema = {"type": "string", "pattern": "^[0-9]+ *([MG]bps)?$"}
memory_schema = {"type": "string", "pattern": "^[0-9]+ *([MG]i?[Bb])?$"}
integer0_schema = {"type": "integer", "minimum": 0}
integer1_schema = {"type": "integer", "minimum": 1}
path_schema = {"type": "string", "pattern": "^(\\.){0,2}(/[^/\"':{}\\(\\)]+)+$"}
vlan_schema = {"type": "integer", "minimum": 1, "maximum": 4095}
vlan1000_schema = {"type": "integer", "minimum": 1000, "maximum": 4095}
mac_schema = {
    "type": "string",
    "pattern": "^[0-9a-fA-F][02468aceACE](:[0-9a-fA-F]{2}){5}$",
}  # must be unicast: LSB bit of MSB byte ==0
dpid_Schema = {"type": "string", "pattern": "^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){7}$"}
# mac_schema={"type":"string", "pattern":"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$"}
ip_schema = {
    "type": "string",
    "pattern": "^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
}
ipv6_schema = {
    "type": "string",
    "pattern": "(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))",  # noqa: W605
}
ip_prefix_schema = {
    "type": "string",
    "pattern": "^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}"
    "(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)/(30|[12]?[0-9])$",
}
port_schema = {"type": "integer", "minimum": 1, "maximum": 65534}
object_schema = {"type": "object"}
schema_version_2 = {"type": "integer", "minimum": 2, "maximum": 2}
# schema_version_string={"type":"string","enum": ["0.1", "2", "0.2", "3", "0.3"]}
log_level_schema = {
    "type": "string",
    "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
}
checksum_schema = {"type": "string", "pattern": "^[0-9a-fA-F]{32}$"}
size_schema = {"type": "integer", "minimum": 1, "maximum": 100}
array_edition_schema = {
    "type": "object",
    "patternProperties": {"^\\$": {}},
    "additionalProperties": False,
    "minProperties": 1,
}
nameshort_list_schema = {
    "type": "array",
    "minItems": 1,
    "items": shortname_schema,
}

description_list_schema = {
    "type": "array",
    "minItems": 1,
    "items": description_schema,
}

profile_type_schema = {
    "type": "string",
    "enum": [
        "infra_controller_profiles",
        "infra_config_profiles",
        "app_profiles",
        "resource_profiles",
    ],
}

ns_instantiate_vdu = {
    "title": "ns action instantiate input schema for vdu",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "id": name_schema,
        "vim-flavor-id": name_schema,
        "instance_name": name_schema,
        "vim-flavor-name": name_schema,
        "security-group-name": name_schema,
        "volume": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "name": name_schema,
                    "vim-volume-id": name_schema,
                },
                "required": ["name", "vim-volume-id"],
                "additionalProperties": False,
            },
        },
        "interface": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "name": name_schema,
                    "ip-address": {"oneOf": [ip_schema, ipv6_schema]},
                    "mac-address": mac_schema,
                    "floating-ip-required": bool_schema,
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["id"],
    "additionalProperties": False,
}

ip_profile_dns_schema = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "address": {"oneOf": [ip_schema, ipv6_schema]},
        },
        "required": ["address"],
        "additionalProperties": False,
    },
}

ip_profile_dhcp_schema = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean"},
        "count": integer1_schema,
        "start-address": ip_schema,
    },
    "additionalProperties": False,
}

ip_profile_schema = {
    "title": "ip profile validation schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "ip-version": {"enum": ["ipv4", "ipv6"]},
        "subnet-address": {"oneOf": [null_schema, ip_prefix_schema]},
        "gateway-address": {"oneOf": [null_schema, ip_schema]},
        "dns-server": {"oneOf": [null_schema, ip_profile_dns_schema]},
        "dhcp-params": {"oneOf": [null_schema, ip_profile_dhcp_schema]},
    },
    "additionalProperties": False,
}

provider_network_schema = {
    "title": "provider network validation schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "physical-network": name_schema,
        "segmentation-id": name_schema,
        "sdn-ports": {  # external ports to append to the SDN-assist network
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "switch_id": shortname_schema,
                    "switch_port": shortname_schema,
                    "mac_address": mac_schema,
                    "vlan": vlan_schema,
                },
                "additionalProperties": True,
            },
        },
        "network-type": shortname_schema,
    },
    "additionalProperties": True,
}

ns_instantiate_internal_vld = {
    "title": "ns action instantiate input schema for vld",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "vim-network-name": name_schema,
        "vim-network-id": name_schema,
        "ip-profile": ip_profile_schema,
        "provider-network": provider_network_schema,
        "internal-connection-point": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "id-ref": name_schema,
                    "ip-address": ip_schema,
                    # "mac-address": mac_schema,
                },
                "required": ["id-ref"],
                "minProperties": 2,
                "additionalProperties": False,
            },
        },
    },
    "required": ["name"],
    "minProperties": 2,
    "additionalProperties": False,
}

additional_params_for_vnf = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "member-vnf-index": name_schema,
            "additionalParams": object_schema,
            "k8s-namespace": name_schema,
            "config-units": integer1_schema,  # number of configuration units of this vnf, by default 1
            "additionalParamsForVdu": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "vdu_id": name_schema,
                        "additionalParams": object_schema,
                        "config-units": integer1_schema,  # number of configuration units of this vdu, by default 1
                    },
                    "required": ["vdu_id"],
                    "minProperties": 2,
                    "additionalProperties": False,
                },
            },
            "additionalParamsForKdu": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kdu_name": name_schema,
                        "additionalParams": object_schema,
                        "kdu_model": name_schema,
                        "k8s-namespace": name_schema,
                        "config-units": integer1_schema,  # number of configuration units of this knf, by default 1
                        "kdu-deployment-name": name_schema,
                    },
                    "required": ["kdu_name"],
                    "minProperties": 2,
                    "additionalProperties": False,
                },
            },
            "affinity-or-anti-affinity-group": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": name_schema,
                        "vim-affinity-group-id": name_schema,
                    },
                    "required": ["id"],
                    "minProperties": 2,
                    "additionalProperties": False,
                },
            },
        },
        "required": ["member-vnf-index"],
        "minProperties": 2,
        "additionalProperties": False,
    },
}

vnf_schema = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "member-vnf-index": name_schema,
            "vimAccountId": id_schema,
            "vdu": {
                "type": "array",
                "minItems": 1,
                "items": ns_instantiate_vdu,
            },
            "internal-vld": {
                "type": "array",
                "minItems": 1,
                "items": ns_instantiate_internal_vld,
            },
        },
        "required": ["member-vnf-index"],
        "minProperties": 2,
        "additionalProperties": False,
    },
}

vld_schema = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "name": string_schema,
            "vim-network-name": {"oneOf": [string_schema, object_schema]},
            "vim-network-id": {"oneOf": [string_schema, object_schema]},
            "ns-net": object_schema,
            "wimAccountId": {"oneOf": [id_schema, bool_schema, null_schema]},
            "ip-profile": ip_profile_schema,
            "provider-network": provider_network_schema,
            "vnfd-connection-point-ref": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "member-vnf-index-ref": name_schema,
                        "vnfd-connection-point-ref": name_schema,
                        "ip-address": {"oneOf": [ip_schema, ipv6_schema]},
                        # "mac-address": mac_schema,
                    },
                    "required": [
                        "member-vnf-index-ref",
                        "vnfd-connection-point-ref",
                    ],
                    "minProperties": 3,
                    "additionalProperties": False,
                },
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

ns_config_template = {
    "title": " ns config template input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": string_schema,
        "nsdId": id_schema,
        "config": object_schema,
    },
    "required": ["name", "nsdId", "config"],
    "additionalProperties": False,
}

ns_instantiate = {
    "title": "ns action instantiate input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "netsliceInstanceId": id_schema,
        "nsName": name_schema,
        "nsDescription": {"oneOf": [description_schema, null_schema]},
        "nsdId": id_schema,
        "vimAccountId": id_schema,
        "nsConfigTemplateId": id_schema,
        "wimAccountId": {"oneOf": [id_schema, bool_schema, null_schema]},
        "placement-engine": string_schema,
        "placement-constraints": object_schema,
        "additionalParamsForNs": object_schema,
        "additionalParamsForVnf": additional_params_for_vnf,
        "config-units": integer1_schema,  # number of configuration units of this ns, by default 1
        "k8s-namespace": name_schema,
        "ssh_keys": {"type": "array", "items": {"type": "string"}},
        "timeout_ns_deploy": integer1_schema,
        "nsr_id": id_schema,
        "vduImage": name_schema,
        "vnf": vnf_schema,
        "vld": vld_schema,
    },
    "required": ["nsName", "nsdId", "vimAccountId"],
    "additionalProperties": False,
}

ns_terminate = {
    "title": "ns terminate input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "autoremove": bool_schema,
        "timeout_ns_terminate": integer1_schema,
        "skip_terminate_primitives": bool_schema,
        "netsliceInstanceId": id_schema,
    },
    "additionalProperties": False,
}

ns_update = {
    "title": "ns update input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "timeout_ns_update": integer1_schema,
        "updateType": {
            "enum": [
                "CHANGE_VNFPKG",
                "REMOVE_VNF",
                "MODIFY_VNF_INFORMATION",
                "OPERATE_VNF",
                "VERTICAL_SCALE",
            ]
        },
        "modifyVnfInfoData": {
            "type": "object",
            "properties": {
                "vnfInstanceId": id_schema,
                "vnfdId": id_schema,
            },
            "required": ["vnfInstanceId", "vnfdId"],
        },
        "removeVnfInstanceId": id_schema,
        "changeVnfPackageData": {
            "type": "object",
            "properties": {
                "vnfInstanceId": id_schema,
                "vnfdId": id_schema,
            },
            "required": ["vnfInstanceId", "vnfdId"],
        },
        "operateVnfData": {
            "type": "object",
            "properties": {
                "vnfInstanceId": id_schema,
                "changeStateTo": name_schema,
                "additionalParam": {
                    "type": "object",
                    "properties": {
                        "run-day1": bool_schema,
                        "vdu_id": name_schema,
                        "count-index": integer0_schema,
                    },
                    "required": ["vdu_id", "count-index"],
                    "additionalProperties": False,
                },
            },
            "required": ["vnfInstanceId", "changeStateTo"],
        },
        "verticalScaleVnf": {
            "type": "object",
            "properties": {
                "vnfInstanceId": id_schema,
                "vnfdId": id_schema,
                "vduId": name_schema,
                "countIndex": integer0_schema,
            },
            "required": ["vnfInstanceId", "vnfdId", "vduId"],
        },
    },
    "required": ["updateType"],
    "additionalProperties": False,
}

ns_action = {  # TODO for the moment it is only contemplated the vnfd primitive execution
    "title": "ns action input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "member_vnf_index": name_schema,
        "vnf_member_index": name_schema,  # TODO for backward compatibility. To remove in future
        "vdu_id": name_schema,
        "vdu_count_index": integer0_schema,
        "kdu_name": name_schema,
        "primitive": name_schema,
        "timeout_ns_action": integer1_schema,
        "primitive_params": {"type": "object"},
    },
    "required": ["primitive", "primitive_params"],  # TODO add member_vnf_index
    "additionalProperties": False,
}

ns_scale = {  # TODO for the moment it is only VDU-scaling
    "title": "ns scale input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "scaleType": {"enum": ["SCALE_VNF"]},
        "timeout_ns_scale": integer1_schema,
        "scaleVnfData": {
            "type": "object",
            "properties": {
                "vnfInstanceId": name_schema,
                "scaleVnfType": {"enum": ["SCALE_OUT", "SCALE_IN"]},
                "scaleByStepData": {
                    "type": "object",
                    "properties": {
                        "scaling-group-descriptor": name_schema,
                        "member-vnf-index": name_schema,
                        "scaling-policy": name_schema,
                    },
                    "required": ["scaling-group-descriptor", "member-vnf-index"],
                    "additionalProperties": False,
                },
            },
            "required": ["scaleVnfType", "scaleByStepData"],  # vnfInstanceId
            "additionalProperties": False,
        },
        "scaleTime": time_schema,
    },
    "required": ["scaleType", "scaleVnfData"],
    "additionalProperties": False,
}

ns_migrate = {
    "title": "ns migrate input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "vnfInstanceId": id_schema,
        "migrateToHost": string_schema,
        "targetHostK8sLabels": object_schema,
        "vdu": {
            "type": "object",
            "properties": {
                "vduId": name_schema,
                "vduCountIndex": integer0_schema,
            },
            "required": ["vduId"],
            "additionalProperties": False,
        },
    },
    "required": ["vnfInstanceId"],
    "additionalProperties": False,
}

ns_heal = {
    "title": "ns heal input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "nsInstanceId": id_schema,
        "timeout_ns_heal": integer1_schema,
        "healVnfData": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "vnfInstanceId": id_schema,
                    "cause": description_schema,
                    "additionalParams": {
                        "type": "object",
                        "properties": {
                            "run-day1": bool_schema,
                            "vdu": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "run-day1": bool_schema,
                                        "vdu-id": name_schema,
                                        "count-index": integer0_schema,
                                    },
                                    "required": ["vdu-id"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["vnfInstanceId"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["healVnfData"],
    "additionalProperties": False,
}

nslcmop_cancel = {
    "title": "Cancel nslcmop input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "nsLcmOpOccId": id_schema,
        "cancelMode": {
            "enum": [
                "GRACEFUL",
                "FORCEFUL",
            ]
        },
    },
    "required": ["cancelMode"],
    "additionalProperties": False,
}

schema_version = {"type": "string", "enum": ["1.0"]}
schema_type = {"type": "string"}
vim_type = shortname_schema  # {"enum": ["openstack", "openvim", "vmware", "opennebula", "aws", "azure", "fos"]}

vim_account_edit_schema = {
    "title": "vim_account edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "vim": name_schema,
        "datacenter": name_schema,
        "vim_type": vim_type,
        "vim_url": description_schema,
        # "vim_url_admin": description_schema,
        # "vim_tenant": name_schema,
        "vim_tenant_name": name_schema,
        "vim_user": string_schema,
        "vim_password": passwd_schema,
        "vca": id_schema,
        "config": {"type": "object"},
        "prometheus-config": {"type": "object"},
    },
    "additionalProperties": False,
}

vim_account_new_schema = {
    "title": "vim_account creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "schema_version": schema_version,
        "schema_type": schema_type,
        "name": name_schema,
        "description": description_schema,
        "vim": name_schema,
        "datacenter": name_schema,
        "vim_type": vim_type,
        "vim_url": description_schema,
        # "vim_url_admin": description_schema,
        # "vim_tenant": name_schema,
        "vim_tenant_name": name_schema,
        "vim_user": string_schema,
        "vim_password": passwd_schema,
        "vca": id_schema,
        "config": {"type": "object"},
        "prometheus-config": {"type": "object"},
    },
    "required": [
        "name",
        "vim_url",
        "vim_type",
        "vim_user",
        "vim_password",
        "vim_tenant_name",
    ],
    "additionalProperties": False,
}

wim_type = shortname_schema  # {"enum": ["ietfl2vpn", "onos", "odl", "dynpac", "fake"]}

wim_account_edit_schema = {
    "title": "wim_account edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "wim": name_schema,
        "wim_type": wim_type,
        "wim_url": description_schema,
        "user": string_schema,
        "password": passwd_schema,
        "config": {"type": "object"},
    },
    "additionalProperties": False,
}

wim_account_new_schema = {
    "title": "wim_account creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "schema_version": schema_version,
        "schema_type": schema_type,
        "name": name_schema,
        "description": description_schema,
        "wim": name_schema,
        "wim_type": wim_type,
        "wim_url": description_schema,
        "user": string_schema,
        "password": passwd_schema,
        "config": {
            "type": "object",
            "patternProperties": {".": {"not": {"type": "null"}}},
        },
    },
    "required": ["name", "wim_url", "wim_type"],
    "additionalProperties": False,
}

sdn_properties = {
    "name": name_schema,
    "type": {"type": "string"},
    "url": {"type": "string"},
    "user": string_schema,
    "password": passwd_schema,
    "config": {"type": "object"},
    "description": description_schema,
    # The folowing are deprecated. Maintanied for backward compatibility
    "dpid": dpid_Schema,
    "ip": ip_schema,
    "port": port_schema,
    "version": {"type": "string", "minLength": 1, "maxLength": 12},
}
sdn_new_schema = {
    "title": "sdn controller information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": sdn_properties,
    "required": ["name", "type"],
    "additionalProperties": False,
}
sdn_edit_schema = {
    "title": "sdn controller update information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": sdn_properties,
    # "required": ["name", "port", 'ip', 'dpid', 'type'],
    "additionalProperties": False,
}
sdn_port_mapping_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "sdn port mapping information schema",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "compute_node": shortname_schema,
            "ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pci": pci_extended_schema,
                        "switch_port": shortname_schema,
                        "switch_mac": mac_schema,
                    },
                    "required": ["pci"],
                },
            },
        },
        "required": ["compute_node", "ports"],
    },
}
sdn_external_port_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "External port information",
    "type": "object",
    "properties": {
        "port": {"type": "string", "minLength": 1, "maxLength": 60},
        "vlan": vlan_schema,
        "mac": mac_schema,
    },
    "required": ["port"],
}

# K8s Clusters
k8scluster_deploy_method_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "Deployment methods for K8s cluster",
    "type": "object",
    "properties": {
        "juju-bundle": {"type": "boolean"},
        "helm-chart-v3": {"type": "boolean"},
    },
    "additionalProperties": False,
    "minProperties": 2,
}
k8scluster_nets_schema = {
    "title": "k8scluster nets input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "patternProperties": {".": {"oneOf": [name_schema, null_schema]}},
    "minProperties": 1,
    "additionalProperties": False,
}
k8scluster_new_schema = {
    "title": "k8scluster creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "schema_version": schema_version,
        "schema_type": schema_type,
        "name": name_schema,
        "description": description_schema,
        "credentials": object_schema,
        "vim_account": id_schema,
        "vca_id": id_schema,
        "k8s_version": string_schema,
        "nets": k8scluster_nets_schema,
        "deployment_methods": k8scluster_deploy_method_schema,
        "namespace": name_schema,
        "cni": nameshort_list_schema,
    },
    "required": ["name", "credentials", "vim_account", "k8s_version", "nets"],
    "additionalProperties": False,
}
k8scluster_edit_schema = {
    "title": "vim_account edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "credentials": object_schema,
        "vim_account": id_schema,
        "vca_id": id_schema,
        "k8s_version": string_schema,
        "nets": k8scluster_nets_schema,
        "namespace": name_schema,
        "cni": nameshort_list_schema,
    },
    "additionalProperties": False,
}

# VCA
vca_new_schema = {
    "title": "vca creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "schema_version": schema_version,
        "schema_type": schema_type,
        "name": name_schema,
        "description": description_schema,
        "endpoints": description_list_schema,
        "user": string_schema,
        "secret": passwd_schema,
        "cacert": long_description_schema,
        "lxd-cloud": shortname_schema,
        "lxd-credentials": shortname_schema,
        "k8s-cloud": shortname_schema,
        "k8s-credentials": shortname_schema,
        "model-config": object_schema,
    },
    "required": [
        "name",
        "endpoints",
        "user",
        "secret",
        "cacert",
        "lxd-cloud",
        "lxd-credentials",
        "k8s-cloud",
        "k8s-credentials",
    ],
    "additionalProperties": False,
}
vca_edit_schema = {
    "title": "vca creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "endpoints": description_list_schema,
        "port": integer1_schema,
        "user": string_schema,
        "secret": passwd_schema,
        "cacert": long_description_schema,
        "lxd-cloud": shortname_schema,
        "lxd-credentials": shortname_schema,
        "k8s-cloud": shortname_schema,
        "k8s-credentials": shortname_schema,
        "model-config": object_schema,
    },
    "additionalProperties": False,
}

# K8s Repos
k8srepo_types = {"enum": ["helm-chart", "juju-bundle"]}
k8srepo_properties = {
    "name": name_schema,
    "description": description_schema,
    "type": k8srepo_types,
    "url": description_schema,
    "cacert": long_description_schema,
    "user": string_schema,
    "password": passwd_schema,
    "oci": bool_schema,
}
k8srepo_new_schema = {
    "title": "k8scluster creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": k8srepo_properties,
    "required": ["name", "type", "url"],
    "additionalProperties": False,
}
k8srepo_edit_schema = {
    "title": "vim_account edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": k8srepo_properties,
    "additionalProperties": False,
}

# OSM Repos
osmrepo_types = {"enum": ["osm"]}
osmrepo_properties = {
    "name": name_schema,
    "description": description_schema,
    "type": osmrepo_types,
    "url": description_schema,
    # "user": string_schema,
    # "password": passwd_schema
}
osmrepo_new_schema = {
    "title": "osm repo creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": osmrepo_properties,
    "required": ["name", "type", "url"],
    "additionalProperties": False,
}
osmrepo_edit_schema = {
    "title": "osm repo edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": osmrepo_properties,
    "additionalProperties": False,
}

# PDUs
pdu_interface = {
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "mgmt": bool_schema,
        "type": {"enum": ["overlay", "underlay"]},
        "ip-address": {"oneOf": [ip_schema, ipv6_schema]},
        # TODO, add user, password, ssh-key
        "mac-address": mac_schema,
        "vim-network-name": shortname_schema,  # interface is connected to one vim network, or switch port
        "vim-network-id": shortname_schema,
        # # provide this in case SDN assist must deal with this interface
        # "switch-dpid": dpid_Schema,
        # "switch-port": shortname_schema,
        # "switch-mac": shortname_schema,
        # "switch-vlan": vlan_schema,
    },
    "required": ["name", "mgmt", "ip-address"],
    "additionalProperties": False,
}
pdu_new_schema = {
    "title": "pdu creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "type": shortname_schema,
        "description": description_schema,
        "shared": bool_schema,
        "vims": nameshort_list_schema,
        "vim_accounts": nameshort_list_schema,
        "interfaces": {"type": "array", "items": pdu_interface, "minItems": 1},
    },
    "required": ["name", "type", "interfaces"],
    "additionalProperties": False,
}
pdu_edit_schema = {
    "title": "pdu edit input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "type": shortname_schema,
        "description": description_schema,
        "shared": bool_schema,
        "vims": {"oneOf": [array_edition_schema, nameshort_list_schema]},
        "vim_accounts": {"oneOf": [array_edition_schema, nameshort_list_schema]},
        "interfaces": {
            "oneOf": [
                array_edition_schema,
                {"type": "array", "items": pdu_interface, "minItems": 1},
            ]
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

# VNF PKG OPERATIONS
vnfpkgop_new_schema = {
    "title": "VNF PKG operation creation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "vnfPkgId": id_schema,
        "kdu_name": name_schema,
        "primitive": name_schema,
        "primitive_params": {"type": "object"},
    },
    "required": [
        "lcmOperationType",
        "vnfPkgId",
        "kdu_name",
        "primitive",
        "primitive_params",
    ],
    "additionalProperties": False,
}

cluster_creation_new_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "cluster creation operation input schema",
    "type": "object",
    "properties": {
        "name": name_schema,
        "vim_account": string_schema,
        "k8s_version": string_schema,
        "node_size": string_schema,
        "node_count": integer0_schema,
        "description": description_schema,
        "region_name": string_schema,
        "resource_group": string_schema,
        "bootstrap": bool_schema,
        # "vim_type": string_schema,
        "private_subnet": {  # Subnets validation
            "type": "array",
            "items": {  # Each item in the array must be a string (subnet ID)
                "type": "string",
                "pattern": "^subnet-[a-f0-9]+$",  # Optional: Add a regex pattern for basic subnet ID format
            },
            # "minItems": 2, # Minimum 2 subnets
            "uniqueItems": True,  # Subnet IDs must be unique
        },
        "public_subnet": {  # Subnets validation
            "type": "array",
            "items": {  # Each item in the array must be a string (subnet ID)
                "type": "string",
                "pattern": "^subnet-[a-f0-9]+$",  # Optional: Add a regex pattern for basic subnet ID format
            },
            # "minItems": 2, # Minimum 2 subnets
            "uniqueItems": True,  # Subnet IDs must be unique
        },
        "iam_role": {
            "type": "string",
            "pattern": "^arn:aws:iam::\\d{12}:role\\/[A-Za-z0-9]+$",
        },
        # additional cluster configuration parameters
        "config": object_schema,
    },
    "required": ["vim_account", "name", "k8s_version"],
    "additionalProperties": False,
}

cluster_registration_new_schema = {
    "title": "cluster registration input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "schema_version": schema_version,
        "schema_type": schema_type,
        "name": name_schema,
        "description": description_schema,
        "credentials": object_schema,
        "vim_account": string_schema,
        "bootstrap": bool_schema,
        "openshift": bool_schema,
    },
    "required": ["name", "credentials", "vim_account"],
    "additionalProperties": False,
}

cluster_edit_schema = {
    "title": "cluster edit schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

cluster_update_schema = {
    "title": "cluster update schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "k8s_version": string_schema,
        "node_size": string_schema,
        "node_count": integer0_schema,
    },
    "additionalProperties": True,
}

infra_controller_profile_create_new_schema = {
    "title": "infra profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

infra_controller_profile_create_edit_schema = {
    "title": "infra profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

infra_config_profile_create_new_schema = {
    "title": "infra profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

infra_config_profile_create_edit_schema = {
    "title": "infra profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

app_profile_create_new_schema = {
    "title": "app profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}
app_profile_create_edit_schema = {
    "title": "app profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

resource_profile_create_new_schema = {
    "title": "resource profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}
resource_profile_create_edit_schema = {
    "title": "resource profile creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

attach_profile = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": id_schema},
        "additionalProperties": False,
    },
}
remove_profile = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": id_schema},
        "additionalProperties": False,
    },
}
attach_dettach_profile_schema = {
    "title": "attach/dettach profiles",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "add_profile": attach_profile,
        "remove_profile": remove_profile,
    },
    "additionalProperties": False,
}

node_create_new_schema = {
    "title": "node creation operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "cluster_id": id_schema,
        "description": string_schema,
        "node_count": integer0_schema,
        "node_size": string_schema,
        "private_subnet": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^subnet-[a-f0-9]+$",
            },
            "uniqueItems": True,
        },
        "public_subnet": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^subnet-[a-f0-9]+$",
            },
            "uniqueItems": True,
        },
        "iam_role": {
            "type": "string",
            "pattern": "^arn:aws:iam::\\d{12}:role\\/[A-Za-z0-9]+$",
        },
    },
    "required": [
        "name",
        "cluster_id",
        "node_size",
        "node_count",
    ],
    "anyOf": [{"required": ["private_subnet"]}, {"required": ["public_subnet"]}],
    "additionalProperties": False,
}

node_edit_schema = {
    "title": "node update operation input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "cluster_id": id_schema,
        "description": string_schema,
        "node_count": integer0_schema,
    },
    "additionalProperties": False,
}

# USERS
project_role_mappings = {
    "title": "list pf projects/roles",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"project": shortname_schema, "role": shortname_schema},
        "required": ["project", "role"],
        "additionalProperties": False,
    },
    "minItems": 1,
}

project_role_mappings_optional = {
    "title": "list of projects/roles or projects only",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"project": shortname_schema, "role": shortname_schema},
        "required": ["project"],
        "additionalProperties": False,
    },
    "minItems": 1,
}

user_new_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "New user schema",
    "type": "object",
    "properties": {
        "username": string_schema,
        "email_id": email_schema,
        "domain_name": shortname_schema,
        "password": user_passwd_schema,
        "projects": nameshort_list_schema,
        "project_role_mappings": project_role_mappings,
    },
    "required": ["username", "password"],
    "additionalProperties": False,
}
user_edit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "User edit schema for administrators",
    "type": "object",
    "properties": {
        "password": user_passwd_schema,
        "email_id": email_schema,
        "old_password": passwd_schema,
        "username": string_schema,  # To allow User Name modification
        "projects": {"oneOf": [nameshort_list_schema, array_edition_schema]},
        "project_role_mappings": project_role_mappings,
        "add_project_role_mappings": project_role_mappings,
        "remove_project_role_mappings": project_role_mappings_optional,
        "system_admin_id": id_schema,
        "unlock": bool_schema,
        "renew": bool_schema,
    },
    "minProperties": 1,
    "additionalProperties": False,
}

# PROJECTS
topics_with_quota = [
    "vnfds",
    "nsds",
    "slice_templates",
    "pduds",
    "ns_instances",
    "slice_instances",
    "vim_accounts",
    "wim_accounts",
    "sdn_controllers",
    "k8sclusters",
    "vca",
    "k8srepos",
    "osmrepos",
    "ns_subscriptions",
]
project_new_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "New project schema for administrators",
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "admin": bool_schema,
        "domain_name": shortname_schema,
        "quotas": {
            "type": "object",
            "properties": {topic: integer0_schema for topic in topics_with_quota},
            "additionalProperties": False,
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}
project_edit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "Project edit schema for administrators",
    "type": "object",
    "properties": {
        "admin": bool_schema,
        "name": shortname_schema,  # To allow Project Name modification
        "quotas": {
            "type": "object",
            "properties": {
                topic: {"oneOf": [integer0_schema, null_schema]}
                for topic in topics_with_quota
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

# ROLES
roles_new_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "New role schema for administrators",
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "permissions": {
            "type": "object",
            "patternProperties": {
                ".": bool_schema,
            },
            # "minProperties": 1,
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}
roles_edit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "Roles edit schema for administrators",
    "type": "object",
    "properties": {
        "name": shortname_schema,
        "permissions": {
            "type": "object",
            "patternProperties": {".": {"oneOf": [bool_schema, null_schema]}},
            # "minProperties": 1,
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
}

# GLOBAL SCHEMAS

nbi_new_input_schemas = {
    "users": user_new_schema,
    "projects": project_new_schema,
    "vim_accounts": vim_account_new_schema,
    "sdns": sdn_new_schema,
    "ns_instantiate": ns_instantiate,
    "ns_action": ns_action,
    "ns_scale": ns_scale,
    "ns_update": ns_update,
    "ns_heal": ns_heal,
    "pdus": pdu_new_schema,
}

nbi_edit_input_schemas = {
    "users": user_edit_schema,
    "projects": project_edit_schema,
    "vim_accounts": vim_account_edit_schema,
    "sdns": sdn_edit_schema,
    "pdus": pdu_edit_schema,
    "vnf": vnf_schema,
    "vld": vld_schema,
    "additionalParamsForVnf": additional_params_for_vnf,
}

# NETSLICE SCHEMAS
nsi_subnet_instantiate = deepcopy(ns_instantiate)
nsi_subnet_instantiate["title"] = "netslice subnet instantiation params input schema"
nsi_subnet_instantiate["properties"]["id"] = name_schema
del nsi_subnet_instantiate["required"]

nsi_vld_instantiate = {
    "title": "netslice vld instantiation params input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": string_schema,
        "vim-network-name": {"oneOf": [string_schema, object_schema]},
        "vim-network-id": {"oneOf": [string_schema, object_schema]},
        "ip-profile": object_schema,
    },
    "required": ["name"],
    "additionalProperties": False,
}

nsi_instantiate = {
    "title": "netslice action instantiate input schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "lcmOperationType": string_schema,
        "netsliceInstanceId": id_schema,
        "nsiName": name_schema,
        "nsiDescription": {"oneOf": [description_schema, null_schema]},
        "nstId": string_schema,
        "vimAccountId": id_schema,
        "timeout_nsi_deploy": integer1_schema,
        "ssh_keys": {"type": "array", "items": {"type": "string"}},
        "nsi_id": id_schema,
        "additionalParamsForNsi": object_schema,
        "netslice-subnet": {
            "type": "array",
            "minItems": 1,
            "items": nsi_subnet_instantiate,
        },
        "netslice-vld": {"type": "array", "minItems": 1, "items": nsi_vld_instantiate},
    },
    "required": ["nsiName", "nstId", "vimAccountId"],
    "additionalProperties": False,
}

nsi_action = {}

nsi_terminate = {}

nsinstancesubscriptionfilter_schema = {
    "title": "instance identifier schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "nsdIds": {"type": "array"},
        "vnfdIds": {"type": "array"},
        "pnfdIds": {"type": "array"},
        "nsInstanceIds": {"type": "array"},
        "nsInstanceNames": {"type": "array"},
    },
}

nslcmsub_schema = {
    "title": "nslcmsubscription input schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "nsInstanceSubscriptionFilter": nsinstancesubscriptionfilter_schema,
        "notificationTypes": {
            "type": "array",
            "items": {
                "enum": [
                    "NsLcmOperationOccurrenceNotification",
                    "NsChangeNotification",
                    "NsIdentifierCreationNotification",
                    "NsIdentifierDeletionNotification",
                ]
            },
        },
        "operationTypes": {
            "type": "array",
            "items": {"enum": ["INSTANTIATE", "SCALE", "TERMINATE", "UPDATE", "HEAL"]},
        },
        "operationStates": {
            "type": "array",
            "items": {
                "enum": [
                    "PROCESSING",
                    "COMPLETED",
                    "PARTIALLY_COMPLETED",
                    "FAILED",
                    "FAILED_TEMP",
                    "ROLLING_BACK",
                    "ROLLED_BACK",
                ]
            },
        },
        "nsComponentTypes": {"type": "array", "items": {"enum": ["VNF", "NS", "PNF"]}},
        "lcmOpNameImpactingNsComponent": {
            "type": "array",
            "items": {
                "enum": [
                    "VNF_INSTANTIATE",
                    "VNF_SCALE",
                    "VNF_SCALE_TO_LEVEL",
                    "VNF_CHANGE_FLAVOUR",
                    "VNF_TERMINATE",
                    "VNF_HEAL",
                    "VNF_OPERATE",
                    "VNF_CHANGE_EXT_CONN",
                    "VNF_MODIFY_INFO",
                    "NS_INSTANTIATE",
                    "NS_SCALE",
                    "NS_UPDATE",
                    "NS_TERMINATE",
                    "NS_HEAL",
                ]
            },
        },
        "lcmOpOccStatusImpactingNsComponent": {
            "type": "array",
            "items": {
                "enum": [
                    "START",
                    "COMPLETED",
                    "PARTIALLY_COMPLETED",
                    "FAILED",
                    "ROLLED_BACK",
                ]
            },
        },
    },
    "allOf": [
        {
            "if": {
                "properties": {
                    "notificationTypes": {
                        "contains": {"const": "NsLcmOperationOccurrenceNotification"}
                    }
                },
            },
            "then": {
                "anyOf": [
                    {"required": ["operationTypes"]},
                    {"required": ["operationStates"]},
                ]
            },
        },
        {
            "if": {
                "properties": {
                    "notificationTypes": {"contains": {"const": "NsChangeNotification"}}
                },
            },
            "then": {
                "anyOf": [
                    {"required": ["nsComponentTypes"]},
                    {"required": ["lcmOpNameImpactingNsComponent"]},
                    {"required": ["lcmOpOccStatusImpactingNsComponent"]},
                ]
            },
        },
    ],
}

authentication_schema = {
    "title": "authentication schema for subscription",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "authType": {"enum": ["basic"]},
        "paramsBasic": {
            "type": "object",
            "properties": {
                "userName": string_schema,
                "password": passwd_schema,
            },
        },
    },
}

subscription = {
    "title": "subscription input schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "filter": nslcmsub_schema,
        "CallbackUri": description_schema,
        "authentication": authentication_schema,
    },
    "required": ["CallbackUri"],
}

vnflcmsub_schema = {
    "title": "vnflcmsubscription input schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "VnfInstanceSubscriptionFilter": {
            "type": "object",
            "properties": {
                "vnfdIds": {"type": "array"},
                "vnfInstanceIds": {"type": "array"},
            },
        },
        "notificationTypes": {
            "type": "array",
            "items": {
                "enum": [
                    "VnfIdentifierCreationNotification",
                    "VnfLcmOperationOccurrenceNotification",
                    "VnfIdentifierDeletionNotification",
                ]
            },
        },
        "operationTypes": {
            "type": "array",
            "items": {
                "enum": [
                    "INSTANTIATE",
                    "SCALE",
                    "SCALE_TO_LEVEL",
                    "CHANGE_FLAVOUR",
                    "TERMINATE",
                    "HEAL",
                    "OPERATE",
                    "CHANGE_EXT_CONN",
                    "MODIFY_INFO",
                    "CREATE_SNAPSHOT",
                    "REVERT_TO_SNAPSHOT",
                    "CHANGE_VNFPKG",
                ]
            },
        },
        "operationStates": {
            "type": "array",
            "items": {
                "enum": [
                    "STARTING",
                    "PROCESSING",
                    "COMPLETED",
                    "FAILED_TEMP",
                    "FAILED",
                    "ROLLING_BACK",
                    "ROLLED_BACK",
                ]
            },
        },
    },
    "required": ["VnfInstanceSubscriptionFilter", "notificationTypes"],
}

vnf_subscription = {
    "title": "vnf subscription input schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "filter": vnflcmsub_schema,
        "CallbackUri": description_schema,
        "authentication": authentication_schema,
    },
    "required": ["filter", "CallbackUri"],
}

oka_schema = {
    "title": "Create OKA package input schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "profile_type": profile_type_schema,
    },
    "additionalProperties": False,
}

ksu_schema = {
    "title": "ksu schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "profile": {
            "type": "object",
            "properties": {
                "profile_type": profile_type_schema,
                "_id": id_schema,
            },
            "additionalProperties": False,
        },
        "oka": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "_id": id_schema,
                    "sw_catalog_path": string_schema,
                    "transformation": object_schema,
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


app_instance_schema = {
    "title": "app instance schema",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "profile": id_schema,
        "profile_type": profile_type_schema,
        "oka": id_schema,
        "sw_catalog_path": string_schema,
        "model": object_schema,
        "params": object_schema,
        "secret_params": object_schema,
    },
    "additionalProperties": False,
    "required": ["name", "profile", "profile_type"],
}

app_instance_edit_schema = {
    "title": "app instance edit schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": string_schema,
    },
    "additionalProperties": False,
}

app_instance_update_schema = {
    "title": "app instance update schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "properties": {
        "model": object_schema,
        "params": object_schema,
        "secret_params": object_schema,
    },
    "additionalProperties": True,
}


class ValidationError(Exception):
    def __init__(self, message, http_code=HTTPStatus.UNPROCESSABLE_ENTITY):
        self.http_code = http_code
        Exception.__init__(self, message)


def validate_input(indata, schema_to_use):
    """
    Validates input data against json schema
    :param indata: user input data. Should be a dictionary
    :param schema_to_use: jsonschema to test
    :return: None if ok, raises ValidationError exception on error
    """
    try:
        if schema_to_use:
            js_v(indata, schema_to_use)
        return None
    except js_e.ValidationError as e:
        if e.path:
            error_pos = "at '" + ":".join(map(str, e.path)) + "'"
        else:
            error_pos = ""
        raise ValidationError("Format error {} '{}' ".format(error_pos, e.message))
    except js_e.SchemaError:
        raise ValidationError(
            "Bad json schema {}".format(schema_to_use),
            http_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def is_valid_uuid(x):
    """
    Test for a valid UUID
    :param x: string to test
    :return: True if x is a valid uuid, False otherwise
    """
    try:
        if UUID(x):
            return True
    except (TypeError, ValueError, AttributeError):
        return False
