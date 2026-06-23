#!/usr/bin/python3
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

import cherrypy
import time
import json
import yaml
import osm_nbi.html_out as html
import logging
import logging.handlers
import getopt
import sys

from osm_nbi.authconn import AuthException, AuthconnException
from osm_nbi.auth import Authenticator
from osm_nbi.engine import Engine, EngineException
from osm_nbi.subscriptions import SubscriptionThread
from osm_nbi.utils import cef_event, cef_event_builder
from osm_nbi.validation import ValidationError
from osm_common.dbbase import DbException
from osm_common.fsbase import FsException
from osm_common.msgbase import MsgException
from http import HTTPStatus
from codecs import getreader
from os import environ, path
from osm_nbi import version as nbi_version, version_date as nbi_version_date

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"

__version__ = "0.1.3"  # file version, not NBI version
version_date = "Aug 2019"

database_version = "1.2"
auth_database_version = "1.0"
nbi_server = None  # instance of Server class
subscription_thread = None  # instance of SubscriptionThread class
cef_logger = None
logger = logging.getLogger("nbi.nbi")

"""
North Bound Interface  (O: OSM specific; 5,X: SOL005 not implemented yet; O5: SOL005 implemented)
URL: /osm                                                       GET     POST    PUT     DELETE  PATCH
        /nsd/v1
            /ns_descriptors_content                             O       O
                /<nsdInfoId>                                    O       O       O       O
            /ns_descriptors                                     O5      O5
                /<nsdInfoId>                                    O5                      O5      5
                    /nsd_content                                O5              O5
                    /nsd                                        O
                    /artifacts[/<artifactPath>]                 O
            /ns_config_template                                 O       O
                /<nsConfigTemplateId>                           O                       O
                    /template_content                           O               O
            /pnf_descriptors                                    5       5
                /<pnfdInfoId>                                   5                       5       5
                    /pnfd_content                               5               5
            /subscriptions                                      5       5
                /<subscriptionId>                               5                       X

        /vnfpkgm/v1
            /vnf_packages_content                               O       O
                /<vnfPkgId>                                     O                       O
            /vnf_packages                                       O5      O5
                /<vnfPkgId>                                     O5                      O5      5
                    /package_content                            O5               O5
                        /upload_from_uri                                X
                    /vnfd                                       O5
                    /artifacts[/<artifactPath>]                 O5
            /subscriptions                                      X       X
                /<subscriptionId>                               X                       X

        /nslcm/v1
            /ns_instances_content                               O       O
                /<nsInstanceId>                                 O                       O
            /ns_instances                                       5       5
                /<nsInstanceId>                                 O5                      O5
                    instantiate                                         O5
                    terminate                                           O5
                    action                                              O
                    scale                                               O5
                    migrate                                             O
                    update                                              05
                    heal                                                O5
            /ns_lcm_op_occs                                     5       5
                /<nsLcmOpOccId>                                 5                       5       5
                    cancel                                              05
            /vnf_instances  (also vnfrs for compatibility)      O
                /<vnfInstanceId>                                O
            /subscriptions                                      5       5
                /<subscriptionId>                               5                       X

        /pdu/v1
            /pdu_descriptors                                    O       O
                /<id>                                           O               O       O       O

        /admin/v1
            /tokens                                             O       O
                /<id>                                           O                       O
            /users                                              O       O
                /<id>                                           O               O       O       O
            /projects                                           O       O
                /<id>                                           O                       O
            /vim_accounts  (also vims for compatibility)        O       O
                /<id>                                           O                       O       O
            /wim_accounts                                       O       O
                /<id>                                           O                       O       O
            /sdns                                               O       O
                /<id>                                           O                       O       O
            /k8sclusters                                        O       O
                /<id>                                           O                       O       O
            /k8srepos                                           O       O
                /<id>                                           O                               O
            /osmrepos                                           O       O
                /<id>                                           O                               O

        /nst/v1                                                 O       O
            /netslice_templates_content                         O       O
                /<nstInfoId>                                    O       O       O       O
            /netslice_templates                                 O       O
                /<nstInfoId>                                    O                       O       O
                    /nst_content                                O               O
                    /nst                                        O
                    /artifacts[/<artifactPath>]                 O
            /subscriptions                                      X       X
                /<subscriptionId>                               X                       X

        /nsilcm/v1
            /netslice_instances_content                         O       O
                /<SliceInstanceId>                              O                       O
            /netslice_instances                                 O       O
                /<SliceInstanceId>                              O                       O
                    instantiate                                         O
                    terminate                                           O
                    action                                              O
            /nsi_lcm_op_occs                                    O       O
                /<nsiLcmOpOccId>                                O                       O       O
            /subscriptions                                      X       X
                /<subscriptionId>                               X                       X

        /k8scluster/v1
            /clusters                                           O       O
                /<clustersId>                                   O                       O
                    app_profiles                                O                               O
                    infra_controller_profiles                   O                               O
                    infra_config_profiles                       O                               O
                    resource_profiles                           O                               O
                    deregister                                                          O
                /register                                               O
            /app_profiles                                       O       O
                /<app_profilesId>                               O                       O       O
            /infra_controller_profiles                          O       O
                /<infra_controller_profilesId>                  O                       O       O
            /infra_config_profiles                              O       O
                /<infra_config_profilesId>                      O                       O       O
            /resource_profiles                                  O       O
                /<resource_profilesID>                          O                       O       O

query string:
    Follows SOL005 section 4.3.2 It contains extra METHOD to override http method, FORCE to force.
        simpleFilterExpr := <attrName>["."<attrName>]*["."<op>]"="<value>[","<value>]*
        filterExpr := <simpleFilterExpr>["&"<simpleFilterExpr>]*
        op := "eq" | "neq" (or "ne") | "gt" | "lt" | "gte" | "lte" | "cont" | "ncont"
        attrName := string
    For filtering inside array, it must select the element of the array, or add ANYINDEX to apply the filtering over any
    item of the array, that is, pass if any item of the array pass the filter.
    It allows both ne and neq for not equal
    TODO: 4.3.3 Attribute selectors
        all_fields, fields=x,y,.., exclude_default, exclude_fields=x,y,...
        (none)	… same as “exclude_default”
        all_fields	… all attributes.
        fields=<list>	… all attributes except all complex attributes with minimum cardinality of zero that are not
        conditionally mandatory, and that are not provided in <list>.
        exclude_fields=<list>	… all attributes except those complex attributes with a minimum cardinality of zero that
        are not conditionally mandatory, and that are provided in <list>.
        exclude_default	… all attributes except those complex attributes with a minimum cardinality of zero that are not
        conditionally mandatory, and that are part of the "default exclude set" defined in the present specification for
        the particular resource
        exclude_default and include=<list>	… all attributes except those complex attributes with a minimum cardinality
        of zero that are not conditionally mandatory and that are part of the "default exclude set" defined in the
        present specification for the particular resource, but that are not part of <list>
    Additionally it admits some administrator values:
        FORCE: To force operations skipping dependency checkings
        ADMIN: To act as an administrator or a different project
        PUBLIC: To get public descriptors or set a descriptor as public
        SET_PROJECT: To make a descriptor available for other project

Header field name	Reference	Example	Descriptions
    Accept	IETF RFC 7231 [19]	application/json	Content-Types that are acceptable for the response.
    This header field shall be present if the response is expected to have a non-empty message body.
    Content-Type	IETF RFC 7231 [19]	application/json	The MIME type of the body of the request.
    This header field shall be present if the request has a non-empty message body.
    Authorization	IETF RFC 7235 [22]	Bearer mF_9.B5f-4.1JqM 	The authorization token for the request.
    Details are specified in clause 4.5.3.
    Range	IETF RFC 7233 [21]	1000-2000	Requested range of bytes from a file
Header field name	Reference	Example	Descriptions
    Content-Type	IETF RFC 7231 [19]	application/json	The MIME type of the body of the response.
    This header field shall be present if the response has a non-empty message body.
    Location	IETF RFC 7231 [19]	http://www.example.com/vnflcm/v1/vnf_instances/123	Used in redirection, or when a
    new resource has been created.
    This header field shall be present if the response status code is 201 or 3xx.
    In the present document this header field is also used if the response status code is 202 and a new resource was
    created.
    WWW-Authenticate	IETF RFC 7235 [22]	Bearer realm="example"	Challenge if the corresponding HTTP request has not
    provided authorization, or error details if the corresponding HTTP request has provided an invalid authorization
    token.
    Accept-Ranges	IETF RFC 7233 [21]	bytes	Used by the Server to signal whether or not it supports ranges for
    certain resources.
    Content-Range	IETF RFC 7233 [21]	bytes 21010-47021/ 47022	Signals the byte range that is contained in the
    response, and the total length of the file.
    Retry-After	IETF RFC 7231 [19]	Fri, 31 Dec 1999 23:59:59 GMT
"""

valid_query_string = ("ADMIN", "SET_PROJECT", "FORCE", "PUBLIC")
# ^ Contains possible administrative query string words:
#     ADMIN=True(by default)|Project|Project-list:  See all elements, or elements of a project
#           (not owned by my session project).
#     PUBLIC=True(by default)|False: See/hide public elements. Set/Unset a topic to be public
#     FORCE=True(by default)|False: Force edition/deletion operations
#     SET_PROJECT=Project|Project-list: Add/Delete the topic to the projects portfolio

valid_url_methods = {
    # contains allowed URL and methods, and the role_permission name
    "admin": {
        "v1": {
            "tokens": {
                "METHODS": ("GET", "POST", "DELETE"),
                "ROLE_PERMISSION": "tokens:",
                "<ID>": {"METHODS": ("GET", "DELETE"), "ROLE_PERMISSION": "tokens:id:"},
            },
            "users": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "users:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "users:id:",
                },
            },
            "projects": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "projects:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "projects:id:",
                },
            },
            "roles": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "roles:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "roles:id:",
                },
            },
            "vims": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vims:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "vims:id:",
                },
            },
            "vim_accounts": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vim_accounts:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "vim_accounts:id:",
                },
            },
            "wim_accounts": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "wim_accounts:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "wim_accounts:id:",
                },
            },
            "sdns": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "sdn_controllers:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "sdn_controllers:id:",
                },
            },
            "k8sclusters": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "k8sclusters:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "k8sclusters:id:",
                },
            },
            "vca": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vca:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "vca:id:",
                },
            },
            "k8srepos": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "k8srepos:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "k8srepos:id:",
                },
            },
            "osmrepos": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "osmrepos:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "osmrepos:id:",
                },
            },
            "domains": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "domains:",
            },
        }
    },
    "pdu": {
        "v1": {
            "pdu_descriptors": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "pduds:",
                "<ID>": {
                    "METHODS": ("GET", "POST", "DELETE", "PATCH", "PUT"),
                    "ROLE_PERMISSION": "pduds:id:",
                },
            },
        }
    },
    "nsd": {
        "v1": {
            "ns_descriptors_content": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "nsds:content:",
                "<ID>": {
                    "METHODS": ("GET", "PUT", "DELETE"),
                    "ROLE_PERMISSION": "nsds:id:",
                },
            },
            "ns_descriptors": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "nsds:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),
                    "ROLE_PERMISSION": "nsds:id:",
                    "nsd_content": {
                        "METHODS": ("GET", "PUT"),
                        "ROLE_PERMISSION": "nsds:id:content:",
                    },
                    "nsd": {
                        "METHODS": ("GET",),  # descriptor inside package
                        "ROLE_PERMISSION": "nsds:id:nsd:",
                    },
                    "artifacts": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "nsds:id:nsd_artifact:",
                        "*": None,
                    },
                },
            },
            "ns_config_template": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "ns_config_template:content:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "ns_config_template:id:",
                    "template_content": {
                        "METHODS": ("GET", "PUT"),
                        "ROLE_PERMISSION": "ns_config_template:id:content:",
                    },
                },
            },
            "pnf_descriptors": {
                "TODO": ("GET", "POST"),
                "<ID>": {
                    "TODO": ("GET", "DELETE", "PATCH"),
                    "pnfd_content": {"TODO": ("GET", "PUT")},
                },
            },
            "subscriptions": {
                "TODO": ("GET", "POST"),
                "<ID>": {"TODO": ("GET", "DELETE")},
            },
        }
    },
    "vnfpkgm": {
        "v1": {
            "vnf_packages_content": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vnfds:content:",
                "<ID>": {
                    "METHODS": ("GET", "PUT", "DELETE"),
                    "ROLE_PERMISSION": "vnfds:id:",
                },
            },
            "vnf_packages": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vnfds:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE", "PATCH"),  # GET: vnfPkgInfo
                    "ROLE_PERMISSION": "vnfds:id:",
                    "package_content": {
                        "METHODS": ("GET", "PUT"),  # package
                        "ROLE_PERMISSION": "vnfds:id:content:",
                        "upload_from_uri": {
                            "METHODS": (),
                            "TODO": ("POST",),
                            "ROLE_PERMISSION": "vnfds:id:upload:",
                        },
                    },
                    "vnfd": {
                        "METHODS": ("GET",),  # descriptor inside package
                        "ROLE_PERMISSION": "vnfds:id:vnfd:",
                    },
                    "artifacts": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "vnfds:id:vnfd_artifact:",
                        "*": None,
                    },
                    "action": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "vnfds:id:action:",
                    },
                },
            },
            "subscriptions": {
                "TODO": ("GET", "POST"),
                "<ID>": {"TODO": ("GET", "DELETE")},
            },
            "vnfpkg_op_occs": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "vnfds:vnfpkgops:",
                "<ID>": {"METHODS": ("GET",), "ROLE_PERMISSION": "vnfds:vnfpkgops:id:"},
            },
        }
    },
    "nslcm": {
        "v1": {
            "ns_instances_terminate": {
                "METHODS": ("POST"),
                "ROLE_PERMISSION": "ns_instances:",
            },
            "ns_instances_content": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "ns_instances:content:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "ns_instances:id:",
                },
            },
            "ns_instances": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "ns_instances:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "ns_instances:id:",
                    "heal": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:heal:",
                    },
                    "scale": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:scale:",
                    },
                    "terminate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:terminate:",
                    },
                    "instantiate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:instantiate:",
                    },
                    "migrate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:migrate:",
                    },
                    "action": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:action:",
                    },
                    "update": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:id:update:",
                    },
                },
            },
            "ns_lcm_op_occs": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "ns_instances:opps:",
                "<ID>": {
                    "METHODS": ("GET",),
                    "ROLE_PERMISSION": "ns_instances:opps:id:",
                    "cancel": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ns_instances:opps:cancel:",
                    },
                },
            },
            "vnfrs": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "vnf_instances:",
                "<ID>": {"METHODS": ("GET",), "ROLE_PERMISSION": "vnf_instances:id:"},
            },
            "vnf_instances": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "vnf_instances:",
                "<ID>": {"METHODS": ("GET",), "ROLE_PERMISSION": "vnf_instances:id:"},
            },
            "subscriptions": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "ns_subscriptions:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "ns_subscriptions:id:",
                },
            },
        }
    },
    "vnflcm": {
        "v1": {
            "vnf_instances": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vnflcm_instances:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "vnflcm_instances:id:",
                    "scale": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "vnflcm_instances:id:scale:",
                    },
                    "terminate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "vnflcm_instances:id:terminate:",
                    },
                    "instantiate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "vnflcm_instances:id:instantiate:",
                    },
                },
            },
            "vnf_lcm_op_occs": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "vnf_instances:opps:",
                "<ID>": {
                    "METHODS": ("GET",),
                    "ROLE_PERMISSION": "vnf_instances:opps:id:",
                },
            },
            "subscriptions": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "vnflcm_subscriptions:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "vnflcm_subscriptions:id:",
                },
            },
        }
    },
    "nst": {
        "v1": {
            "netslice_templates_content": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "slice_templates:",
                "<ID>": {
                    "METHODS": ("GET", "PUT", "DELETE"),
                    "ROLE_PERMISSION": "slice_templates:id:",
                },
            },
            "netslice_templates": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "slice_templates:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "TODO": ("PATCH",),
                    "ROLE_PERMISSION": "slice_templates:id:",
                    "nst_content": {
                        "METHODS": ("GET", "PUT"),
                        "ROLE_PERMISSION": "slice_templates:id:content:",
                    },
                    "nst": {
                        "METHODS": ("GET",),  # descriptor inside package
                        "ROLE_PERMISSION": "slice_templates:id:content:",
                    },
                    "artifacts": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "slice_templates:id:content:",
                        "*": None,
                    },
                },
            },
            "subscriptions": {
                "TODO": ("GET", "POST"),
                "<ID>": {"TODO": ("GET", "DELETE")},
            },
        }
    },
    "nsilcm": {
        "v1": {
            "netslice_instances_content": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "slice_instances:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "slice_instances:id:",
                },
            },
            "netslice_instances": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "slice_instances:",
                "<ID>": {
                    "METHODS": ("GET", "DELETE"),
                    "ROLE_PERMISSION": "slice_instances:id:",
                    "terminate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "slice_instances:id:terminate:",
                    },
                    "instantiate": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "slice_instances:id:instantiate:",
                    },
                    "action": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "slice_instances:id:action:",
                    },
                },
            },
            "nsi_lcm_op_occs": {
                "METHODS": ("GET",),
                "ROLE_PERMISSION": "slice_instances:opps:",
                "<ID>": {
                    "METHODS": ("GET",),
                    "ROLE_PERMISSION": "slice_instances:opps:id:",
                },
            },
        }
    },
    "nspm": {
        "v1": {
            "pm_jobs": {
                "<ID>": {
                    "reports": {
                        "<ID>": {
                            "METHODS": ("GET",),
                            "ROLE_PERMISSION": "reports:id:",
                        }
                    }
                },
            },
        },
    },
    "nsfm": {
        "v1": {
            "alarms": {
                "METHODS": ("GET", "PATCH"),
                "ROLE_PERMISSION": "alarms:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH"),
                    "ROLE_PERMISSION": "alarms:id:",
                },
            }
        },
    },
    "k8scluster": {
        "v1": {
            "clusters": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "k8scluster:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "k8scluster:id:",
                    "app_profiles": {
                        "METHODS": ("PATCH", "GET"),
                        "ROLE_PERMISSION": "k8scluster:id:app_profiles:",
                    },
                    "infra_controller_profiles": {
                        "METHODS": ("PATCH", "GET"),
                        "ROLE_PERMISSION": "k8scluster:id:infra_profiles:",
                    },
                    "infra_config_profiles": {
                        "METHODS": ("PATCH", "GET"),
                        "ROLE_PERMISSION": "k8scluster:id:infra_profiles:",
                    },
                    "resource_profiles": {
                        "METHODS": ("PATCH", "GET"),
                        "ROLE_PERMISSION": "k8scluster:id:infra_profiles:",
                    },
                    "deregister": {
                        "METHODS": ("DELETE",),
                        "ROLE_PERMISSION": "k8scluster:id:deregister:",
                    },
                    "get_creds": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "k8scluster:id:get_creds:",
                    },
                    "get_creds_file": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "k8scluster:id:get_creds_file:",
                        "<ID>": {
                            "METHODS": ("GET",),
                            "ROLE_PERMISSION": "k8scluster:id:get_creds_file:id",
                        },
                    },
                    "update": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "k8scluster:id:update:",
                    },
                    "scale": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "k8scluster:id:scale:",
                    },
                    "upgrade": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "k8scluster:id:upgrade:",
                    },
                    "nodegroup": {
                        "METHODS": ("POST", "GET"),
                        "ROLE_PERMISSION": "k8scluster:id:nodegroup:",
                        "<ID>": {
                            "METHODS": ("GET", "PATCH", "DELETE"),
                            "ROLE_PERMISSION": "k8scluster:id:nodegroup:id",
                            "scale": {
                                "METHODS": ("POST",),
                                "ROLE_PERMISSION": "k8scluster:id:nodegroup:id:scale:",
                            },
                        },
                    },
                    "ksus": {
                        "METHODS": ("GET",),
                        "ROLE_PERMISSION": "k8scluster:id:ksus:",
                    },
                },
                "register": {
                    "METHODS": ("POST",),
                    "ROLE_PERMISSION": "k8scluster:register:",
                },
            },
            "app_profiles": {
                "METHODS": ("POST", "GET"),
                "ROLE_PERMISSION": "k8scluster:app_profiles:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "k8scluster:app_profiles:id:",
                },
            },
            "infra_controller_profiles": {
                "METHODS": ("POST", "GET"),
                "ROLE_PERMISSION": "k8scluster:infra_controller_profiles:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "k8scluster:infra_controller_profiles:id:",
                },
            },
            "infra_config_profiles": {
                "METHODS": ("POST", "GET"),
                "ROLE_PERMISSION": "k8scluster:infra_config_profiles:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "k8scluster:infra_config_profiles:id:",
                },
            },
            "resource_profiles": {
                "METHODS": ("POST", "GET"),
                "ROLE_PERMISSION": "k8scluster:resource_profiles:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "k8scluster:resource_profiles:id:",
                },
            },
        }
    },
    "ksu": {
        "v1": {
            "ksus": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "ksu:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "ksu:id:",
                    "clone": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ksu:id:clone:",
                    },
                    "move": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "ksu:id:move:",
                    },
                },
                "update": {
                    "METHODS": ("POST",),
                    "ROLE_PERMISSION": "ksu:",
                },
                "delete": {
                    "METHODS": ("POST",),
                    "ROLE_PERMISSION": "ksu:",
                },
            },
        }
    },
    "appinstance": {
        "v1": {
            "appinstances": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "appinstance:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE"),
                    "ROLE_PERMISSION": "appinstance:id:",
                    "update": {
                        "METHODS": ("POST",),
                        "ROLE_PERMISSION": "appinstance:id:update:",
                    },
                },
            },
        }
    },
    "oka": {
        "v1": {
            "oka_packages": {
                "METHODS": ("GET", "POST"),
                "ROLE_PERMISSION": "oka_pkg:",
                "<ID>": {
                    "METHODS": ("GET", "PATCH", "DELETE", "PUT"),
                    "ROLE_PERMISSION": "oka_pkg:id:",
                },
            }
        }
    },
}


class NbiException(Exception):
    def __init__(self, message, http_code=HTTPStatus.METHOD_NOT_ALLOWED):
        Exception.__init__(self, message)
        self.http_code = http_code


class Server(object):
    instance = 0
    # to decode bytes to str
    reader = getreader("utf-8")

    def __init__(self):
        self.instance += 1
        self.authenticator = Authenticator(valid_url_methods, valid_query_string)
        self.engine = Engine(self.authenticator)
        self.logger = logging.getLogger("nbi.server")

    def _format_in(self, kwargs):
        error_text = ""  # error_text must be initialized outside try
        try:
            indata = None
            if cherrypy.request.body.length:
                error_text = "Invalid input format "

                if "Content-Type" in cherrypy.request.headers:
                    if "application/json" in cherrypy.request.headers["Content-Type"]:
                        error_text = "Invalid json format "
                        indata = json.load(self.reader(cherrypy.request.body))
                        cherrypy.request.headers.pop("Content-File-MD5", None)
                    elif "application/yaml" in cherrypy.request.headers["Content-Type"]:
                        error_text = "Invalid yaml format "
                        indata = yaml.safe_load(cherrypy.request.body)
                        cherrypy.request.headers.pop("Content-File-MD5", None)
                    elif (
                        "application/binary" in cherrypy.request.headers["Content-Type"]
                        or "application/gzip"
                        in cherrypy.request.headers["Content-Type"]
                        or "application/zip" in cherrypy.request.headers["Content-Type"]
                        or "text/plain" in cherrypy.request.headers["Content-Type"]
                    ):
                        indata = cherrypy.request.body  # .read()
                    elif (
                        "multipart/form-data"
                        in cherrypy.request.headers["Content-Type"]
                    ):
                        if (
                            "descriptor_file" in kwargs
                            or "package" in kwargs
                            and "name" in kwargs
                        ):
                            filecontent = ""
                            if "descriptor_file" in kwargs:
                                filecontent = kwargs.pop("descriptor_file")
                            if "package" in kwargs:
                                filecontent = kwargs.pop("package")
                            if not filecontent.file:
                                raise NbiException(
                                    "empty file or content", HTTPStatus.BAD_REQUEST
                                )
                            indata = filecontent
                            if filecontent.content_type.value:
                                cherrypy.request.headers[
                                    "Content-Type"
                                ] = filecontent.content_type.value
                        elif "package" in kwargs:
                            filecontent = kwargs.pop("package")
                            if not filecontent.file:
                                raise NbiException(
                                    "empty file or content", HTTPStatus.BAD_REQUEST
                                )
                            indata = filecontent
                            if filecontent.content_type.value:
                                cherrypy.request.headers[
                                    "Content-Type"
                                ] = filecontent.content_type.value
                    else:
                        # raise cherrypy.HTTPError(HTTPStatus.Not_Acceptable,
                        #                          "Only 'Content-Type' of type 'application/json' or
                        # 'application/yaml' for input format are available")
                        error_text = "Invalid yaml format "
                        indata = yaml.safe_load(cherrypy.request.body)
                        cherrypy.request.headers.pop("Content-File-MD5", None)
                else:
                    error_text = "Invalid yaml format "
                    indata = yaml.safe_load(cherrypy.request.body)
                    cherrypy.request.headers.pop("Content-File-MD5", None)
            if not indata:
                indata = {}
            format_yaml = False
            if cherrypy.request.headers.get("Query-String-Format") == "yaml":
                format_yaml = True

            for k, v in kwargs.items():
                if isinstance(v, str):
                    if v == "":
                        kwargs[k] = None
                    elif format_yaml:
                        try:
                            kwargs[k] = yaml.safe_load(v)
                        except Exception:
                            pass
                    elif (
                        k.endswith(".gt")
                        or k.endswith(".lt")
                        or k.endswith(".gte")
                        or k.endswith(".lte")
                    ):
                        try:
                            kwargs[k] = int(v)
                        except Exception:
                            try:
                                kwargs[k] = float(v)
                            except Exception:
                                pass
                    elif v.find(",") > 0:
                        kwargs[k] = v.split(",")
                elif isinstance(v, (list, tuple)):
                    for index in range(0, len(v)):
                        if v[index] == "":
                            v[index] = None
                        elif format_yaml:
                            try:
                                v[index] = yaml.safe_load(v[index])
                            except Exception:
                                pass

            return indata
        except (ValueError, yaml.YAMLError) as exc:
            raise NbiException(error_text + str(exc), HTTPStatus.BAD_REQUEST)
        except KeyError as exc:
            raise NbiException(
                "Query string error: " + str(exc), HTTPStatus.BAD_REQUEST
            )
        except Exception as exc:
            raise NbiException(error_text + str(exc), HTTPStatus.BAD_REQUEST)

    @staticmethod
    def _format_out(data, token_info=None, _format=None):
        """
        return string of dictionary data according to requested json, yaml, xml. By default json
        :param data: response to be sent. Can be a dict, text or file
        :param token_info: Contains among other username and project
        :param _format: The format to be set as Content-Type if data is a file
        :return: None
        """
        accept = cherrypy.request.headers.get("Accept")
        if data is None:
            if accept and "text/html" in accept:
                return html.format(
                    data, cherrypy.request, cherrypy.response, token_info
                )
            # cherrypy.response.status = HTTPStatus.NO_CONTENT.value
            return
        elif hasattr(data, "read"):  # file object
            if _format:
                cherrypy.response.headers["Content-Type"] = _format
            elif "b" in data.mode:  # binariy asssumig zip
                cherrypy.response.headers["Content-Type"] = "application/zip"
            else:
                cherrypy.response.headers["Content-Type"] = "text/plain"
            # TODO check that cherrypy close file. If not implement pending things to close  per thread next
            return data
        if accept:
            if "text/html" in accept:
                return html.format(
                    data, cherrypy.request, cherrypy.response, token_info
                )
            elif "application/yaml" in accept or "*/*" in accept:
                pass
            elif "application/json" in accept or (
                cherrypy.response.status and cherrypy.response.status >= 300
            ):
                cherrypy.response.headers[
                    "Content-Type"
                ] = "application/json; charset=utf-8"
                a = json.dumps(data, indent=4) + "\n"
                return a.encode("utf8")
        cherrypy.response.headers["Content-Type"] = "application/yaml"
        return yaml.safe_dump(
            data,
            explicit_start=True,
            indent=4,
            default_flow_style=False,
            tags=False,
            encoding="utf-8",
            allow_unicode=True,
        )  # , canonical=True, default_style='"'

    @cherrypy.expose
    def index(self, *args, **kwargs):
        token_info = None
        try:
            if cherrypy.request.method == "GET":
                token_info = self.authenticator.authorize()
                outdata = token_info  # Home page
            else:
                raise cherrypy.HTTPError(
                    HTTPStatus.METHOD_NOT_ALLOWED.value,
                    "Method {} not allowed for tokens".format(cherrypy.request.method),
                )

            return self._format_out(outdata, token_info)

        except (EngineException, AuthException) as e:
            # cherrypy.log("index Exception {}".format(e))
            cherrypy.response.status = e.http_code.value
            return self._format_out("Welcome to OSM!", token_info)

    @cherrypy.expose
    def version(self, *args, **kwargs):
        # TODO consider to remove and provide version using the static version file
        try:
            if cherrypy.request.method != "GET":
                raise NbiException(
                    "Only method GET is allowed", HTTPStatus.METHOD_NOT_ALLOWED
                )
            elif args or kwargs:
                raise NbiException(
                    "Invalid URL or query string for version",
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            # TODO include version of other modules, pick up from some kafka admin message
            osm_nbi_version = {"version": nbi_version, "date": nbi_version_date}
            return self._format_out(osm_nbi_version)
        except NbiException as e:
            cherrypy.response.status = e.http_code.value
            problem_details = {
                "code": e.http_code.name,
                "status": e.http_code.value,
                "detail": str(e),
            }
            return self._format_out(problem_details, None)

    def domain(self):
        try:
            domains = {
                "user_domain_name": cherrypy.tree.apps["/osm"]
                .config["authentication"]
                .get("user_domain_name"),
                "project_domain_name": cherrypy.tree.apps["/osm"]
                .config["authentication"]
                .get("project_domain_name"),
            }
            return self._format_out(domains)
        except NbiException as e:
            cherrypy.response.status = e.http_code.value
            problem_details = {
                "code": e.http_code.name,
                "status": e.http_code.value,
                "detail": str(e),
            }
            return self._format_out(problem_details, None)

    @staticmethod
    def _format_login(token_info):
        """
        Changes cherrypy.request.login to include username/project_name;session so that cherrypy access log will
        log this information
        :param token_info: Dictionary with token content
        :return: None
        """
        cherrypy.request.login = token_info.get("username", "-")
        if token_info.get("project_name"):
            cherrypy.request.login += "/" + token_info["project_name"]
        if token_info.get("id"):
            cherrypy.request.login += ";session=" + token_info["id"][0:12]

    # NS Fault Management
    @cherrypy.expose
    def nsfm(
        self,
        version=None,
        topic=None,
        uuid=None,
        project_name=None,
        ns_id=None,
        *args,
        **kwargs,
    ):
        if topic == "alarms":
            try:
                method = cherrypy.request.method
                role_permission = self._check_valid_url_method(
                    method, "nsfm", version, topic, None, None, *args
                )
                query_string_operations = self._extract_query_string_operations(
                    kwargs, method
                )

                self.authenticator.authorize(
                    role_permission, query_string_operations, None
                )

                # to handle get request
                if cherrypy.request.method == "GET":
                    # if request is on basis of uuid
                    if uuid and uuid != "None":
                        try:
                            alarm = self.engine.db.get_one("alarms", {"uuid": uuid})
                            alarm_action = self.engine.db.get_one(
                                "alarms_action", {"uuid": uuid}
                            )
                            alarm.update(alarm_action)
                            vnf = self.engine.db.get_one(
                                "vnfrs", {"nsr-id-ref": alarm["tags"]["ns_id"]}
                            )
                            alarm["vnf-id"] = vnf["_id"]
                            return self._format_out(str(alarm))
                        except Exception:
                            return self._format_out("Please provide valid alarm uuid")
                    elif ns_id and ns_id != "None":
                        # if request is on basis of ns_id
                        try:
                            alarms = self.engine.db.get_list(
                                "alarms", {"tags.ns_id": ns_id}
                            )
                            for alarm in alarms:
                                alarm_action = self.engine.db.get_one(
                                    "alarms_action", {"uuid": alarm["uuid"]}
                                )
                                alarm.update(alarm_action)
                            return self._format_out(str(alarms))
                        except Exception:
                            return self._format_out("Please provide valid ns id")
                    else:
                        # to return only alarm which are related to given project
                        project = self.engine.db.get_one(
                            "projects", {"name": project_name}
                        )
                        project_id = project.get("_id")
                        ns_list = self.engine.db.get_list(
                            "nsrs", {"_admin.projects_read": project_id}
                        )
                        ns_ids = []
                        for ns in ns_list:
                            ns_ids.append(ns.get("_id"))
                        alarms = self.engine.db.get_list("alarms")
                        alarm_list = [
                            alarm
                            for alarm in alarms
                            if alarm["tags"]["ns_id"] in ns_ids
                        ]
                        for alrm in alarm_list:
                            action = self.engine.db.get_one(
                                "alarms_action", {"uuid": alrm.get("uuid")}
                            )
                            alrm.update(action)
                        return self._format_out(str(alarm_list))
                # to handle patch request for alarm update
                elif cherrypy.request.method == "PATCH":
                    data = yaml.safe_load(cherrypy.request.body)
                    try:
                        # check if uuid is valid
                        self.engine.db.get_one("alarms", {"uuid": data.get("uuid")})
                    except Exception:
                        return self._format_out("Please provide valid alarm uuid.")
                    if data.get("is_enable") is not None:
                        if data.get("is_enable"):
                            alarm_status = "ok"
                        else:
                            alarm_status = "disabled"
                        self.engine.db.set_one(
                            "alarms",
                            {"uuid": data.get("uuid")},
                            {"alarm_status": alarm_status},
                        )
                    else:
                        self.engine.db.set_one(
                            "alarms",
                            {"uuid": data.get("uuid")},
                            {"threshold": data.get("threshold")},
                        )
                    return self._format_out("Alarm updated")
            except Exception as e:
                if isinstance(
                    e,
                    (
                        NbiException,
                        EngineException,
                        DbException,
                        FsException,
                        MsgException,
                        AuthException,
                        ValidationError,
                        AuthconnException,
                    ),
                ):
                    http_code_value = cherrypy.response.status = e.http_code.value
                    http_code_name = e.http_code.name
                    cherrypy.log("Exception {}".format(e))
                else:
                    http_code_value = (
                        cherrypy.response.status
                    ) = HTTPStatus.BAD_REQUEST.value  # INTERNAL_SERVER_ERROR
                    cherrypy.log("CRITICAL: Exception {}".format(e), traceback=True)
                    http_code_name = HTTPStatus.BAD_REQUEST.name
                problem_details = {
                    "code": http_code_name,
                    "status": http_code_value,
                    "detail": str(e),
                }
                return self._format_out(problem_details)

    @cherrypy.expose
    def token(self, method, token_id=None, kwargs=None):
        token_info = None
        # self.engine.load_dbase(cherrypy.request.app.config)
        indata = self._format_in(kwargs)
        if not isinstance(indata, dict):
            raise NbiException(
                "Expected application/yaml or application/json Content-Type",
                HTTPStatus.BAD_REQUEST,
            )

        if method == "GET":
            token_info = self.authenticator.authorize()
            # for logging
            self._format_login(token_info)
            if token_id:
                outdata = self.authenticator.get_token(token_info, token_id)
            else:
                outdata = self.authenticator.get_token_list(token_info)
        elif method == "POST":
            try:
                token_info = self.authenticator.authorize()
            except Exception:
                token_info = None
            if kwargs:
                indata.update(kwargs)
            # This is needed to log the user when authentication fails
            cherrypy.request.login = "{}".format(indata.get("username", "-"))
            outdata = token_info = self.authenticator.new_token(
                token_info, indata, cherrypy.request.remote
            )
            if outdata.get("email") or outdata.get("otp") == "invalid":
                return self._format_out(outdata, token_info)
            cherrypy.session["Authorization"] = outdata["_id"]  # pylint: disable=E1101
            self._set_location_header("admin", "v1", "tokens", outdata["_id"])
            # for logging
            self._format_login(token_info)
            if outdata.get("otp") == "valid":
                outdata = {
                    "id": outdata["id"],
                    "message": "valid_otp",
                    "user_id": outdata["user_id"],
                }
            # password expiry check
            elif self.authenticator.check_password_expiry(outdata):
                outdata = {
                    "id": outdata["id"],
                    "message": "change_password",
                    "user_id": outdata["user_id"],
                }
            # cherrypy.response.cookie["Authorization"] = outdata["id"]
            # cherrypy.response.cookie["Authorization"]['expires'] = 3600
            cef_event(
                cef_logger,
                {
                    "name": "User Login",
                    "sourceUserName": token_info.get("username"),
                    "message": "User Logged In, Project={} Outcome=Success".format(
                        token_info.get("project_name")
                    ),
                },
            )
            cherrypy.log("{}".format(cef_logger))
        elif method == "DELETE":
            if not token_id and "id" in kwargs:
                token_id = kwargs["id"]
            elif not token_id:
                token_info = self.authenticator.authorize()
                # for logging
                self._format_login(token_info)
                token_id = token_info["_id"]
            if current_backend != "keystone":
                token_details = self.engine.db.get_one("tokens", {"_id": token_id})
                current_user = token_details.get("username")
                current_project = token_details.get("project_name")
            else:
                current_user = "keystone backend"
                current_project = "keystone backend"
            outdata = self.authenticator.del_token(token_id)
            token_info = None
            cherrypy.session["Authorization"] = "logout"  # pylint: disable=E1101
            cef_event(
                cef_logger,
                {
                    "name": "User Logout",
                    "sourceUserName": current_user,
                    "message": "User Logged Out, Project={} Outcome=Success".format(
                        current_project
                    ),
                },
            )
            cherrypy.log("{}".format(cef_logger))
            # cherrypy.response.cookie["Authorization"] = token_id
            # cherrypy.response.cookie["Authorization"]['expires'] = 0
        else:
            raise NbiException(
                "Method {} not allowed for token".format(method),
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
        return self._format_out(outdata, token_info)

    @cherrypy.expose
    def test(self, *args, **kwargs):
        if not cherrypy.config.get("server.enable_test") or (
            isinstance(cherrypy.config["server.enable_test"], str)
            and cherrypy.config["server.enable_test"].lower() == "false"
        ):
            cherrypy.response.status = HTTPStatus.METHOD_NOT_ALLOWED.value
            return "test URL is disabled"
        thread_info = None
        if args and args[0] == "help":
            return (
                "<html><pre>\ninit\nfile/<name>  download file\ndb-clear/table\nfs-clear[/folder]\nlogin\nlogin2\n"
                "sleep/<time>\nmessage/topic\n</pre></html>"
            )

        elif args and args[0] == "init":
            try:
                # self.engine.load_dbase(cherrypy.request.app.config)
                pid = self.authenticator.create_admin_project()
                self.authenticator.create_admin_user(pid)
                return "Done. User 'admin', password 'admin' created"
            except Exception:
                cherrypy.response.status = HTTPStatus.FORBIDDEN.value
                return self._format_out("Database already initialized")
        elif args and args[0] == "file":
            return cherrypy.lib.static.serve_file(
                cherrypy.tree.apps["/osm"].config["storage"]["path"] + "/" + args[1],
                "text/plain",
                "attachment",
            )
        elif args and args[0] == "file2":
            f_path = (
                cherrypy.tree.apps["/osm"].config["storage"]["path"] + "/" + args[1]
            )
            f = open(f_path, "r")
            cherrypy.response.headers["Content-type"] = "text/plain"
            return f

        elif len(args) == 2 and args[0] == "db-clear":
            deleted_info = self.engine.db.del_list(args[1], kwargs)
            return "{} {} deleted\n".format(deleted_info["deleted"], args[1])
        elif len(args) and args[0] == "fs-clear":
            if len(args) >= 2:
                folders = (args[1],)
            else:
                folders = self.engine.fs.dir_ls(".")
            for folder in folders:
                self.engine.fs.file_delete(folder)
            return ",".join(folders) + " folders deleted\n"
        elif args and args[0] == "login":
            if not cherrypy.request.headers.get("Authorization"):
                cherrypy.response.headers[
                    "WWW-Authenticate"
                ] = 'Basic realm="Access to OSM site", charset="UTF-8"'
                cherrypy.response.status = HTTPStatus.UNAUTHORIZED.value
        elif args and args[0] == "login2":
            if not cherrypy.request.headers.get("Authorization"):
                cherrypy.response.headers[
                    "WWW-Authenticate"
                ] = 'Bearer realm="Access to OSM site"'
                cherrypy.response.status = HTTPStatus.UNAUTHORIZED.value
        elif args and args[0] == "sleep":
            sleep_time = 5
            try:
                sleep_time = int(args[1])
            except Exception:
                cherrypy.response.status = HTTPStatus.FORBIDDEN.value
                return self._format_out("Database already initialized")
            thread_info = cherrypy.thread_data
            print(thread_info)
            time.sleep(sleep_time)
            # thread_info
        elif len(args) >= 2 and args[0] == "message":
            main_topic = args[1]
            return_text = "<html><pre>{} ->\n".format(main_topic)
            try:
                if cherrypy.request.method == "POST":
                    to_send = yaml.safe_load(cherrypy.request.body)
                    for k, v in to_send.items():
                        self.engine.msg.write(main_topic, k, v)
                        return_text += "  {}: {}\n".format(k, v)
                elif cherrypy.request.method == "GET":
                    for k, v in kwargs.items():
                        v_dict = yaml.safe_load(v)
                        self.engine.msg.write(main_topic, k, v_dict)
                        return_text += "  {}: {}\n".format(k, v_dict)
            except Exception as e:
                return_text += "Error: " + str(e)
            return_text += "</pre></html>\n"
            return return_text

        return_text = (
            "<html><pre>\nheaders:\n  args: {}\n".format(args)
            + "  kwargs: {}\n".format(kwargs)
            + "  headers: {}\n".format(cherrypy.request.headers)
            + "  path_info: {}\n".format(cherrypy.request.path_info)
            + "  query_string: {}\n".format(cherrypy.request.query_string)
            + "  session: {}\n".format(cherrypy.session)  # pylint: disable=E1101
            + "  cookie: {}\n".format(cherrypy.request.cookie)
            + "  method: {}\n".format(cherrypy.request.method)
            + "  session: {}\n".format(
                cherrypy.session.get("fieldname")  # pylint: disable=E1101
            )
            + "  body:\n"
        )
        return_text += "    length: {}\n".format(cherrypy.request.body.length)
        if cherrypy.request.body.length:
            return_text += "    content: {}\n".format(
                str(
                    cherrypy.request.body.read(
                        int(cherrypy.request.headers.get("Content-Length", 0))
                    )
                )
            )
        if thread_info:
            return_text += "thread: {}\n".format(thread_info)
        return_text += "</pre></html>"
        return return_text

    @staticmethod
    def _check_valid_url_method(method, *args):
        if len(args) < 3:
            raise NbiException(
                "URL must contain at least 'main_topic/version/topic'",
                HTTPStatus.METHOD_NOT_ALLOWED,
            )

        reference = valid_url_methods
        for arg in args:
            if arg is None:
                break
            if not isinstance(reference, dict):
                raise NbiException(
                    "URL contains unexpected extra items '{}'".format(arg),
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )

            if arg in reference:
                reference = reference[arg]
            elif "<ID>" in reference:
                reference = reference["<ID>"]
            elif "*" in reference:
                # if there is content
                if reference["*"]:
                    reference = reference["*"]
                break
            else:
                raise NbiException(
                    "Unexpected URL item {}".format(arg), HTTPStatus.METHOD_NOT_ALLOWED
                )
        if "TODO" in reference and method in reference["TODO"]:
            raise NbiException(
                "Method {} not supported yet for this URL".format(method),
                HTTPStatus.NOT_IMPLEMENTED,
            )
        elif "METHODS" in reference and method not in reference["METHODS"]:
            raise NbiException(
                "Method {} not supported for this URL".format(method),
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
        return reference["ROLE_PERMISSION"] + method.lower()

    @staticmethod
    def _set_location_header(main_topic, version, topic, id):
        """
        Insert response header Location with the URL of created item base on URL params
        :param main_topic:
        :param version:
        :param topic:
        :param id:
        :return: None
        """
        # Use cherrypy.request.base for absoluted path and make use of request.header HOST just in case behind aNAT
        cherrypy.response.headers["Location"] = "/osm/{}/{}/{}/{}".format(
            main_topic, version, topic, id
        )
        return

    @staticmethod
    def _extract_query_string_operations(kwargs, method):
        """

        :param kwargs:
        :return:
        """
        query_string_operations = []
        if kwargs:
            for qs in ("FORCE", "PUBLIC", "ADMIN", "SET_PROJECT"):
                if qs in kwargs and kwargs[qs].lower() != "false":
                    query_string_operations.append(qs.lower() + ":" + method.lower())
        return query_string_operations

    @staticmethod
    def _manage_admin_query(token_info, kwargs, method, _id):
        """
        Processes the administrator query inputs (if any) of FORCE, ADMIN, PUBLIC, SET_PROJECT
        Check that users has rights to use them and returs the admin_query
        :param token_info: token_info rights obtained by token
        :param kwargs: query string input.
        :param method: http method: GET, POSST, PUT, ...
        :param _id:
        :return: admin_query dictionary with keys:
            public: True, False or None
            force: True or False
            project_id: tuple with projects used for accessing an element
            set_project: tuple with projects that a created element will belong to
            method: show, list, delete, write
        """
        admin_query = {
            "force": False,
            "project_id": (token_info["project_id"],),
            "username": token_info["username"],
            "user_id": token_info["user_id"],
            "admin": token_info["admin"],
            "admin_show": token_info["admin_show"],
            "public": None,
            "allow_show_user_project_role": token_info["allow_show_user_project_role"],
        }
        if kwargs:
            # FORCE
            if "FORCE" in kwargs:
                if (
                    kwargs["FORCE"].lower() != "false"
                ):  # if None or True set force to True
                    admin_query["force"] = True
                del kwargs["FORCE"]
            # PUBLIC
            if "PUBLIC" in kwargs:
                if (
                    kwargs["PUBLIC"].lower() != "false"
                ):  # if None or True set public to True
                    admin_query["public"] = True
                else:
                    admin_query["public"] = False
                del kwargs["PUBLIC"]
            # ADMIN
            if "ADMIN" in kwargs:
                behave_as = kwargs.pop("ADMIN")
                if behave_as.lower() != "false":
                    if not token_info["admin"]:
                        raise NbiException(
                            "Only admin projects can use 'ADMIN' query string",
                            HTTPStatus.UNAUTHORIZED,
                        )
                    if (
                        not behave_as or behave_as.lower() == "true"
                    ):  # convert True, None to empty list
                        admin_query["project_id"] = ()
                    elif isinstance(behave_as, (list, tuple)):
                        admin_query["project_id"] = behave_as
                    else:  # isinstance(behave_as, str)
                        admin_query["project_id"] = (behave_as,)
            if "SET_PROJECT" in kwargs:
                set_project = kwargs.pop("SET_PROJECT")
                if not set_project:
                    admin_query["set_project"] = list(admin_query["project_id"])
                else:
                    if isinstance(set_project, str):
                        set_project = (set_project,)
                    if admin_query["project_id"]:
                        for p in set_project:
                            if p not in admin_query["project_id"]:
                                raise NbiException(
                                    "Unauthorized for 'SET_PROJECT={p}'. Try with 'ADMIN=True' or "
                                    "'ADMIN='{p}'".format(p=p),
                                    HTTPStatus.UNAUTHORIZED,
                                )
                    admin_query["set_project"] = set_project

            # PROJECT_READ
            # if "PROJECT_READ" in kwargs:
            #     admin_query["project"] = kwargs.pop("project")
            #     if admin_query["project"] == token_info["project_id"]:
        if method == "GET":
            if _id:
                admin_query["method"] = "show"
            else:
                admin_query["method"] = "list"
        elif method == "DELETE":
            admin_query["method"] = "delete"
        else:
            admin_query["method"] = "write"
        return admin_query

    @cherrypy.expose
    def default(
        self,
        main_topic=None,
        version=None,
        topic=None,
        _id=None,
        item=None,
        *args,
        **kwargs,
    ):
        token_info = None
        outdata = {}
        _format = None
        method = "DONE"
        engine_topic = None
        rollback = []
        engine_session = None
        url_id = ""
        log_mapping = {
            "POST": "Creating",
            "GET": "Fetching",
            "DELETE": "Deleting",
            "PUT": "Updating",
            "PATCH": "Updating",
        }
        try:
            if not main_topic or not version or not topic:
                raise NbiException(
                    "URL must contain at least 'main_topic/version/topic'",
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            if main_topic not in (
                "admin",
                "vnfpkgm",
                "nsd",
                "nslcm",
                "pdu",
                "nst",
                "nsilcm",
                "nspm",
                "vnflcm",
                "k8scluster",
                "ksu",
                "appinstance",
                "oka",
            ):
                raise NbiException(
                    "URL main_topic '{}' not supported".format(main_topic),
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            if version != "v1":
                raise NbiException(
                    "URL version '{}' not supported".format(version),
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            if _id is not None:
                url_id = _id

            if (
                kwargs
                and "METHOD" in kwargs
                and kwargs["METHOD"] in ("PUT", "POST", "DELETE", "GET", "PATCH")
            ):
                method = kwargs.pop("METHOD")
            else:
                method = cherrypy.request.method

            role_permission = self._check_valid_url_method(
                method, main_topic, version, topic, _id, item, *args
            )
            query_string_operations = self._extract_query_string_operations(
                kwargs, method
            )
            if main_topic == "admin" and topic == "tokens":
                return self.token(method, _id, kwargs)
            token_info = self.authenticator.authorize(
                role_permission, query_string_operations, _id
            )
            if main_topic == "admin" and topic == "domains":
                return self.domain()
            engine_session = self._manage_admin_query(token_info, kwargs, method, _id)
            indata = self._format_in(kwargs)
            engine_topic = topic

            if item and topic != "pm_jobs":
                engine_topic = item

            if main_topic == "nsd":
                engine_topic = "nsds"
                if topic == "ns_config_template":
                    engine_topic = "nsconfigtemps"
            elif main_topic == "vnfpkgm":
                engine_topic = "vnfds"
                if topic == "vnfpkg_op_occs":
                    engine_topic = "vnfpkgops"
                if topic == "vnf_packages" and item == "action":
                    engine_topic = "vnfpkgops"
            elif main_topic == "nslcm":
                engine_topic = "nsrs"
                if topic == "ns_lcm_op_occs":
                    engine_topic = "nslcmops"
                if topic == "vnfrs" or topic == "vnf_instances":
                    engine_topic = "vnfrs"
            elif main_topic == "vnflcm":
                if topic == "vnf_lcm_op_occs":
                    engine_topic = "vnflcmops"
            elif main_topic == "nst":
                engine_topic = "nsts"
            elif main_topic == "nsilcm":
                engine_topic = "nsis"
                if topic == "nsi_lcm_op_occs":
                    engine_topic = "nsilcmops"
            elif main_topic == "pdu":
                engine_topic = "pdus"
            elif main_topic == "k8scluster":
                engine_topic = "cluster"
                if topic == "clusters" and _id == "register" or item == "deregister":
                    engine_topic = "clusterops"
                elif topic == "infra_controller_profiles":
                    engine_topic = "infras_cont"
                elif topic == "infra_config_profiles":
                    engine_topic = "infras_conf"
                elif topic == "resource_profiles":
                    engine_topic = "resources"
                elif topic == "app_profiles":
                    engine_topic = "apps"
                elif topic == "clusters" and item == "nodegroup":
                    engine_topic = "node_groups"
            elif main_topic == "ksu" and engine_topic in ("ksus", "clone", "move"):
                engine_topic = "ksus"
            elif main_topic == "appinstance":
                engine_topic = "appinstances"
            if (
                engine_topic == "vims"
            ):  # TODO this is for backward compatibility, it will be removed in the future
                engine_topic = "vim_accounts"

            if topic == "subscriptions":
                engine_topic = main_topic + "_" + topic

            if method == "GET":
                if item in (
                    "nsd_content",
                    "package_content",
                    "artifacts",
                    "vnfd",
                    "nsd",
                    "nst",
                    "nst_content",
                    "ns_config_template",
                ):
                    if item in ("vnfd", "nsd", "nst"):
                        path = "$DESCRIPTOR"
                    elif args:
                        path = args
                    elif item == "artifacts":
                        path = ()
                    else:
                        path = None
                    file, _format = self.engine.get_file(
                        engine_session,
                        engine_topic,
                        _id,
                        path,
                        cherrypy.request.headers.get("Accept"),
                    )
                    outdata = file
                # elif not _id and topic != "clusters":
                #     outdata = self.engine.get_item_list(
                #         engine_session, engine_topic, kwargs, api_req=True
                #     )
                elif topic == "clusters" and item in (
                    "infra_controller_profiles",
                    "infra_config_profiles",
                    "app_profiles",
                    "resource_profiles",
                ):
                    profile = item
                    filter_q = None
                    outdata = self.engine.get_one_item(
                        engine_session,
                        engine_topic,
                        _id,
                        profile,
                        filter_q,
                        api_req=True,
                    )
                elif (
                    topic == "clusters"
                    and item == "get_creds_file"
                    or item == "get_creds"
                ):
                    if item == "get_creds_file":
                        op_id = args[0]
                        file, _format = self.engine.get_cluster_creds_file(
                            engine_session, engine_topic, _id, item, op_id
                        )
                        outdata = file
                    if item == "get_creds":
                        op_id = self.engine.get_cluster_creds(
                            engine_session, engine_topic, _id, item
                        )
                        outdata = {"op_id": op_id}
                elif topic == "clusters" and not _id:
                    outdata = self.engine.get_item_list_cluster(
                        engine_session, engine_topic, kwargs, api_req=True
                    )
                elif topic == "clusters" and item == "nodegroup" and args:
                    _id = args[0]
                    outdata = outdata = self.engine.get_item(
                        engine_session, engine_topic, _id, kwargs, True
                    )
                elif topic == "clusters" and item == "nodegroup":
                    kwargs["cluster_id"] = _id
                    outdata = self.engine.get_item_list(
                        engine_session, engine_topic, kwargs, api_req=True
                    )
                elif topic == "clusters" and item == "ksus":
                    engine_topic = "ksus"
                    kwargs["cluster_id"] = _id
                    outdata = self.engine.get_cluster_list_ksu(
                        engine_session, engine_topic, kwargs, api_req=True
                    )
                elif not _id:
                    outdata = self.engine.get_item_list(
                        engine_session, engine_topic, kwargs, api_req=True
                    )
                else:
                    if item == "reports":
                        # TODO check that project_id (_id in this context) has permissions
                        _id = args[0]
                    filter_q = None
                    if "vcaStatusRefresh" in kwargs:
                        filter_q = {"vcaStatusRefresh": kwargs["vcaStatusRefresh"]}
                    outdata = self.engine.get_item(
                        engine_session, engine_topic, _id, filter_q, True
                    )

            elif method == "POST":
                cherrypy.response.status = HTTPStatus.CREATED.value
                if topic in (
                    "ns_descriptors_content",
                    "vnf_packages_content",
                    "netslice_templates_content",
                    "ns_config_template",
                ):
                    _id = cherrypy.request.headers.get("Transaction-Id")

                    if not _id:
                        _id, _ = self.engine.new_item(
                            rollback,
                            engine_session,
                            engine_topic,
                            {},
                            None,
                            cherrypy.request.headers,
                        )
                    completed = self.engine.upload_content(
                        engine_session,
                        engine_topic,
                        _id,
                        indata,
                        kwargs,
                        cherrypy.request.headers,
                    )
                    if completed:
                        self._set_location_header(main_topic, version, topic, _id)
                    else:
                        cherrypy.response.headers["Transaction-Id"] = _id
                    outdata = {"id": _id}
                elif topic == "oka_packages":
                    _id = cherrypy.request.headers.get("Transaction-Id")

                    if not _id:
                        _id, _ = self.engine.new_item(
                            rollback,
                            engine_session,
                            engine_topic,
                            {},
                            kwargs,
                            cherrypy.request.headers,
                        )
                    cherrypy.request.headers["method"] = cherrypy.request.method
                    if indata:
                        completed = self.engine.upload_content(
                            engine_session,
                            engine_topic,
                            _id,
                            indata,
                            None,
                            cherrypy.request.headers,
                        )
                    if completed:
                        self._set_location_header(main_topic, version, topic, _id)
                    else:
                        cherrypy.response.headers["Transaction-Id"] = _id
                    outdata = {"_id": _id, "id": _id}
                elif topic == "ns_instances_content":
                    # creates NSR
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, engine_topic, indata, kwargs
                    )
                    # creates nslcmop
                    indata["lcmOperationType"] = "instantiate"
                    indata["nsInstanceId"] = _id
                    nslcmop_id, nsName, _ = self.engine.new_item(
                        rollback, engine_session, "nslcmops", indata, None
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    outdata = {"id": _id, "nslcmop_id": nslcmop_id, "nsName": nsName}
                elif topic == "ns_instances_terminate":
                    if indata.get("ns_ids"):
                        for ns_id in indata.get("ns_ids"):
                            nslcmop_desc = {
                                "lcmOperationType": "terminate",
                                "nsInstanceId": ns_id,
                                "autoremove": (
                                    indata.get("autoremove")
                                    if "autoremove" in indata
                                    else True
                                ),
                            }
                            op_id, _, _ = self.engine.new_item(
                                rollback,
                                engine_session,
                                "nslcmops",
                                nslcmop_desc,
                                kwargs,
                            )
                            if not op_id:
                                _ = self.engine.del_item(
                                    engine_session, engine_topic, ns_id
                                )
                    outdata = {"ns_ids": indata.get("ns_ids")}
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "ns_instances" and item:
                    indata["lcmOperationType"] = item
                    indata["nsInstanceId"] = _id
                    _id, nsName, _ = self.engine.new_item(
                        rollback, engine_session, "nslcmops", indata, kwargs
                    )
                    self._set_location_header(
                        main_topic, version, "ns_lcm_op_occs", _id
                    )
                    outdata = {"id": _id, "nsName": nsName}
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "netslice_instances_content":
                    # creates NetSlice_Instance_record (NSIR)
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, engine_topic, indata, kwargs
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    indata["lcmOperationType"] = "instantiate"
                    indata["netsliceInstanceId"] = _id
                    nsilcmop_id, _ = self.engine.new_item(
                        rollback, engine_session, "nsilcmops", indata, kwargs
                    )
                    outdata = {"id": _id, "nsilcmop_id": nsilcmop_id}
                elif topic == "netslice_instances" and item:
                    indata["lcmOperationType"] = item
                    indata["netsliceInstanceId"] = _id
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, "nsilcmops", indata, kwargs
                    )
                    self._set_location_header(
                        main_topic, version, "nsi_lcm_op_occs", _id
                    )
                    outdata = {"id": _id}
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "vnf_packages" and item == "action":
                    indata["lcmOperationType"] = item
                    indata["vnfPkgId"] = _id
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, "vnfpkgops", indata, kwargs
                    )
                    self._set_location_header(
                        main_topic, version, "vnfpkg_op_occs", _id
                    )
                    outdata = {"id": _id}
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "subscriptions":
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, engine_topic, indata, kwargs
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    link = {}
                    link["self"] = cherrypy.response.headers["Location"]
                    outdata = {
                        "id": _id,
                        "filter": indata["filter"],
                        "callbackUri": indata["CallbackUri"],
                        "_links": link,
                    }
                    cherrypy.response.status = HTTPStatus.CREATED.value
                elif topic == "vnf_instances" and item:
                    indata["lcmOperationType"] = item
                    indata["vnfInstanceId"] = _id
                    _id, nsName, _ = self.engine.new_item(
                        rollback, engine_session, "vnflcmops", indata, kwargs
                    )
                    self._set_location_header(
                        main_topic, version, "vnf_lcm_op_occs", _id
                    )
                    outdata = {"id": _id, "nsName": nsName}
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "ns_lcm_op_occs" and item == "cancel":
                    indata["nsLcmOpOccId"] = _id
                    self.engine.cancel_item(
                        rollback, engine_session, "nslcmops", indata, None
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                elif topic == "clusters" and _id == "register":
                    # To register a cluster
                    _id, _ = self.engine.add_item(
                        rollback, engine_session, engine_topic, indata, kwargs
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    outdata = {"_id": _id, "id": _id}
                elif (
                    topic
                    in (
                        "clusters",
                        "infra_controller_profiles",
                        "infra_config_profiles",
                        "app_profiles",
                        "resource_profiles",
                    )
                    and item is None
                ):
                    # creates cluster, infra_controller_profiles, app_profiles, infra_config_profiles, and resource_profiles
                    _id, _ = self.engine.new_item(
                        rollback, engine_session, engine_topic, indata, kwargs
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    outdata = {"_id": _id, "id": _id}
                elif topic == "ksus" and item:
                    if item == "clone":
                        _id = self.engine.clone(
                            rollback,
                            engine_session,
                            engine_topic,
                            _id,
                            indata,
                            kwargs,
                            cherrypy.request.headers,
                        )
                        self._set_location_header(main_topic, version, topic, _id)
                        outdata = {"_id": _id, "id": _id}
                    if item == "move":
                        op_id = self.engine.move_ksu(
                            engine_session, engine_topic, _id, indata, kwargs
                        )
                        outdata = {"op_id": op_id}
                elif topic == "ksus" and _id == "delete":
                    op_id = self.engine.delete_ksu(
                        engine_session, engine_topic, _id, indata
                    )
                    outdata = {"op_id": op_id}
                elif topic == "ksus" and _id == "update":
                    op_id = self.engine.edit_item(
                        engine_session, engine_topic, _id, indata, kwargs
                    )
                    outdata = {"op_id": op_id}
                elif topic == "appinstances" and item == "update":
                    op_id = self.engine.update_item(
                        engine_session, engine_topic, _id, item, indata
                    )
                    outdata = {"op_id": op_id}
                elif topic == "clusters" and item in ("upgrade", "scale"):
                    op_id = self.engine.update_item(
                        engine_session, engine_topic, _id, item, indata
                    )
                    outdata = {"op_id": op_id}
                elif topic == "clusters" and item == "nodegroup":
                    indata["cluster_id"] = _id
                    if args:
                        _id = args[0]
                        op_id = self.engine.update_item(
                            engine_session, engine_topic, _id, item, indata
                        )
                        outdata = {"op_id": op_id}
                    else:
                        _id, _ = self.engine.new_item(
                            rollback, engine_session, engine_topic, indata, kwargs
                        )
                        self._set_location_header(main_topic, version, topic, _id)
                        outdata = {"_id": _id, "id": _id}
                else:
                    self.logger.debug(
                        "Creating new item in topic {}".format(engine_topic)
                    )
                    _id, op_id = self.engine.new_item(
                        rollback,
                        engine_session,
                        engine_topic,
                        indata,
                        kwargs,
                        cherrypy.request.headers,
                    )
                    self._set_location_header(main_topic, version, topic, _id)
                    outdata = {"_id": _id, "id": _id}
                    if op_id:
                        outdata["op_id"] = op_id
                        cherrypy.response.status = HTTPStatus.ACCEPTED.value
                    # TODO form NsdInfo when topic in ("ns_descriptors", "vnf_packages")

            elif method == "DELETE":
                if not _id:
                    outdata = self.engine.del_item_list(
                        engine_session, engine_topic, kwargs
                    )
                    cherrypy.response.status = HTTPStatus.OK.value
                else:  # len(args) > 1
                    # for NS NSI generate an operation
                    op_id = None
                    if topic == "ns_instances_content" and not engine_session["force"]:
                        nslcmop_desc = {
                            "lcmOperationType": "terminate",
                            "nsInstanceId": _id,
                            "autoremove": True,
                        }
                        op_id, nsName, _ = self.engine.new_item(
                            rollback, engine_session, "nslcmops", nslcmop_desc, kwargs
                        )
                        if op_id:
                            outdata = {"_id": op_id, "nsName": nsName}
                    elif (
                        topic == "netslice_instances_content"
                        and not engine_session["force"]
                    ):
                        nsilcmop_desc = {
                            "lcmOperationType": "terminate",
                            "netsliceInstanceId": _id,
                            "autoremove": True,
                        }
                        op_id, _ = self.engine.new_item(
                            rollback, engine_session, "nsilcmops", nsilcmop_desc, None
                        )
                        if op_id:
                            outdata = {"_id": op_id}
                    elif topic == "clusters" and item == "deregister":
                        if not op_id:
                            op_id = self.engine.remove(
                                engine_session, engine_topic, _id
                            )
                            if op_id:
                                outdata = {"_id": op_id}
                        cherrypy.response.status = (
                            HTTPStatus.ACCEPTED.value
                            if op_id
                            else HTTPStatus.NO_CONTENT.value
                        )
                    elif topic == "clusters" and item == "nodegroup" and args:
                        _id = args[0]
                        op_id = self.engine.del_item(engine_session, engine_topic, _id)
                        if op_id:
                            outdata = {"_id": op_id}
                    elif topic == "ksus":
                        op_id = self.engine.delete_ksu(
                            engine_session, engine_topic, _id, indata
                        )
                        outdata = {"op_id": op_id}
                    # if there is not any deletion in process, delete
                    elif not op_id:
                        op_id = self.engine.del_item(engine_session, engine_topic, _id)
                        if op_id:
                            outdata = {"_id": op_id}
                    cherrypy.response.status = (
                        HTTPStatus.ACCEPTED.value
                        if op_id
                        else HTTPStatus.NO_CONTENT.value
                    )

            elif method in ("PUT", "PATCH"):
                op_id = None
                if not indata and not kwargs and not engine_session.get("set_project"):
                    raise NbiException(
                        "Nothing to update. Provide payload and/or query string",
                        HTTPStatus.BAD_REQUEST,
                    )
                if (
                    item
                    in (
                        "nsd_content",
                        "package_content",
                        "nst_content",
                        "template_content",
                    )
                    and method == "PUT"
                ):
                    completed = self.engine.upload_content(
                        engine_session,
                        engine_topic,
                        _id,
                        indata,
                        kwargs,
                        cherrypy.request.headers,
                    )
                    if not completed:
                        cherrypy.response.headers["Transaction-Id"] = id
                elif item in (
                    "app_profiles",
                    "resource_profiles",
                    "infra_controller_profiles",
                    "infra_config_profiles",
                ):
                    op_id = self.engine.edit(
                        engine_session, engine_topic, _id, item, indata, kwargs
                    )
                elif topic == "oka_packages" and method == "PATCH":
                    if kwargs:
                        op_id = self.engine.edit_item(
                            engine_session, engine_topic, _id, None, kwargs
                        )
                    if indata:
                        if isinstance(indata, dict):
                            op_id = self.engine.edit_item(
                                engine_session, engine_topic, _id, indata, kwargs
                            )
                        else:
                            cherrypy.request.headers["method"] = cherrypy.request.method
                            completed = self.engine.upload_content(
                                engine_session,
                                engine_topic,
                                _id,
                                indata,
                                {},
                                cherrypy.request.headers,
                            )
                            if not completed:
                                cherrypy.response.headers["Transaction-Id"] = id
                elif topic == "oka_packages" and method == "PUT":
                    if indata:
                        cherrypy.request.headers["method"] = cherrypy.request.method
                        completed = self.engine.upload_content(
                            engine_session,
                            engine_topic,
                            _id,
                            indata,
                            {},
                            cherrypy.request.headers,
                        )
                        if not completed:
                            cherrypy.response.headers["Transaction-Id"] = id
                elif topic == "clusters" and item == "nodegroup" and args:
                    _id = args[0]
                    op_id = self.engine.edit_item(
                        engine_session, engine_topic, _id, indata, kwargs
                    )
                else:
                    op_id = self.engine.edit_item(
                        engine_session, engine_topic, _id, indata, kwargs
                    )

                if op_id:
                    cherrypy.response.status = HTTPStatus.ACCEPTED.value
                    outdata = {"op_id": op_id}
                else:
                    cherrypy.response.status = HTTPStatus.NO_CONTENT.value
                    outdata = None
            else:
                raise NbiException(
                    "Method {} not allowed".format(method),
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )

            # if Role information changes, it is needed to reload the information of roles
            if topic == "roles" and method != "GET":
                self.authenticator.load_operation_to_allowed_roles()

            if (
                topic == "projects"
                and method == "DELETE"
                or topic in ["users", "roles"]
                and method in ["PUT", "PATCH", "DELETE"]
            ):
                self.authenticator.remove_token_from_cache()

            cef_event(
                cef_logger,
                {
                    "name": "User Operation",
                    "sourceUserName": token_info.get("username"),
                },
            )
            if topic == "ns_instances_content" and url_id:
                nsName = (
                    outdata.get("name") if method == "GET" else outdata.get("nsName")
                )
                cef_event(
                    cef_logger,
                    {
                        "message": "{} {}, nsName={}, nsdId={}, Project={} Outcome=Success".format(
                            log_mapping[method],
                            topic,
                            nsName,
                            outdata.get("id"),
                            token_info.get("project_name"),
                        ),
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            elif topic == "ns_instances_content" and method == "POST":
                cef_event(
                    cef_logger,
                    {
                        "message": "{} {}, nsName={}, nsdId={}, Project={} Outcome=Success".format(
                            log_mapping[method],
                            topic,
                            outdata.get("nsName"),
                            outdata.get("id"),
                            token_info.get("project_name"),
                        ),
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            elif topic in ("ns_instances", "vnf_instances") and item:
                cef_event(
                    cef_logger,
                    {
                        "message": "{} {}, nsName={}, nsdId={}, Project={} Outcome=Success".format(
                            log_mapping[method],
                            topic,
                            outdata.get("nsName"),
                            url_id,
                            token_info.get("project_name"),
                        ),
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            elif item is not None:
                cef_event(
                    cef_logger,
                    {
                        "message": "Performing {} operation on {} {}, Project={} Outcome=Success".format(
                            item,
                            topic,
                            url_id,
                            token_info.get("project_name"),
                        ),
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            else:
                cef_event(
                    cef_logger,
                    {
                        "message": "{} {} {}, Project={} Outcome=Success".format(
                            log_mapping[method],
                            topic,
                            url_id,
                            token_info.get("project_name"),
                        ),
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            return self._format_out(outdata, token_info, _format)
        except Exception as e:
            if isinstance(
                e,
                (
                    NbiException,
                    EngineException,
                    DbException,
                    FsException,
                    MsgException,
                    AuthException,
                    ValidationError,
                    AuthconnException,
                ),
            ):
                http_code_value = cherrypy.response.status = e.http_code.value
                http_code_name = e.http_code.name
                cherrypy.log("Exception {}".format(e))
            else:
                http_code_value = (
                    cherrypy.response.status
                ) = HTTPStatus.BAD_REQUEST.value  # INTERNAL_SERVER_ERROR
                cherrypy.log("CRITICAL: Exception {}".format(e), traceback=True)
                http_code_name = HTTPStatus.BAD_REQUEST.name
            if hasattr(outdata, "close"):  # is an open file
                outdata.close()
            error_text = str(e)
            rollback.reverse()
            for rollback_item in rollback:
                try:
                    if rollback_item.get("operation") == "set":
                        self.engine.db.set_one(
                            rollback_item["topic"],
                            {"_id": rollback_item["_id"]},
                            rollback_item["content"],
                            fail_on_empty=False,
                        )
                    elif rollback_item.get("operation") == "del_list":
                        self.engine.db.del_list(
                            rollback_item["topic"],
                            rollback_item["filter"],
                        )
                    else:
                        self.engine.db.del_one(
                            rollback_item["topic"],
                            {"_id": rollback_item["_id"]},
                            fail_on_empty=False,
                        )
                except Exception as e2:
                    rollback_error_text = "Rollback Exception {}: {}".format(
                        rollback_item, e2
                    )
                    cherrypy.log(rollback_error_text)
                    error_text += ". " + rollback_error_text
            # if isinstance(e, MsgException):
            #     error_text = "{} has been '{}' but other modules cannot be informed because an error on bus".format(
            #         engine_topic[:-1], method, error_text)
            problem_details = {
                "code": http_code_name,
                "status": http_code_value,
                "detail": error_text,
            }
            if item is not None and token_info is not None:
                cef_event(
                    cef_logger,
                    {
                        "name": "User Operation",
                        "sourceUserName": token_info.get("username", None),
                        "message": "Performing {} operation on {} {}, Project={} Outcome=Failure".format(
                            item,
                            topic,
                            url_id,
                            token_info.get("project_name", None),
                        ),
                        "severity": "2",
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            elif token_info is not None:
                cef_event(
                    cef_logger,
                    {
                        "name": "User Operation",
                        "sourceUserName": token_info.get("username", None),
                        "message": "{} {} {}, Project={} Outcome=Failure".format(
                            item,
                            topic,
                            url_id,
                            token_info.get("project_name", None),
                        ),
                        "severity": "2",
                    },
                )
                cherrypy.log("{}".format(cef_logger))
            return self._format_out(problem_details, token_info)
            # raise cherrypy.HTTPError(e.http_code.value, str(e))
        finally:
            if token_info:
                self._format_login(token_info)
                if method in ("PUT", "PATCH", "POST") and isinstance(outdata, dict):
                    for logging_id in ("id", "op_id", "nsilcmop_id", "nslcmop_id"):
                        if outdata.get(logging_id):
                            cherrypy.request.login += ";{}={}".format(
                                logging_id, outdata[logging_id][:36]
                            )


def _start_service():
    """
    Callback function called when cherrypy.engine starts
    Override configuration with env variables
    Set database, storage, message configuration
    Init database with admin/admin user password
    """
    global subscription_thread
    global cef_logger
    global current_backend
    cherrypy.log.error("Starting osm_nbi")
    # update general cherrypy configuration
    update_dict = {}

    engine_config = cherrypy.tree.apps["/osm"].config
    for k, v in environ.items():
        if k == "OSMNBI_USER_MANAGEMENT":
            feature_state = v.lower() == "true"
            engine_config["authentication"]["user_management"] = feature_state
        elif k == "OSMNBI_PWD_EXPIRE_DAYS":
            pwd_expire_days = int(v)
            engine_config["authentication"]["pwd_expire_days"] = pwd_expire_days
        elif k == "OSMNBI_MAX_PWD_ATTEMPT":
            max_pwd_attempt = int(v)
            engine_config["authentication"]["max_pwd_attempt"] = max_pwd_attempt
        elif k == "OSMNBI_ACCOUNT_EXPIRE_DAYS":
            account_expire_days = int(v)
            engine_config["authentication"]["account_expire_days"] = account_expire_days
        elif k == "OSMNBI_SMTP_SERVER":
            engine_config["authentication"]["smtp_server"] = v
            engine_config["authentication"]["all"] = environ
        elif k == "OSMNBI_SMTP_PORT":
            port = int(v)
            engine_config["authentication"]["smtp_port"] = port
        elif k == "OSMNBI_SENDER_EMAIL":
            engine_config["authentication"]["sender_email"] = v
        elif k == "OSMNBI_EMAIL_PASSWORD":
            engine_config["authentication"]["sender_password"] = v
        elif k == "OSMNBI_OTP_RETRY_COUNT":
            otp_retry_count = int(v)
            engine_config["authentication"]["retry_count"] = otp_retry_count
        elif k == "OSMNBI_OTP_EXPIRY_TIME":
            otp_expiry_time = int(v)
            engine_config["authentication"]["otp_expiry_time"] = otp_expiry_time
        if not k.startswith("OSMNBI_"):
            continue
        k1, _, k2 = k[7:].lower().partition("_")
        if not k2:
            continue
        try:
            # update static configuration
            if k == "OSMNBI_STATIC_DIR":
                engine_config["/static"]["tools.staticdir.dir"] = v
                engine_config["/static"]["tools.staticdir.on"] = True
            elif k == "OSMNBI_SOCKET_PORT" or k == "OSMNBI_SERVER_PORT":
                update_dict["server.socket_port"] = int(v)
            elif k == "OSMNBI_SOCKET_HOST" or k == "OSMNBI_SERVER_HOST":
                update_dict["server.socket_host"] = v
            elif k1 in ("server", "test", "auth", "log"):
                update_dict[k1 + "." + k2] = v
            elif k1 in ("message", "database", "storage", "authentication"):
                # k2 = k2.replace('_', '.')
                if k2 in ("port", "db_port"):
                    engine_config[k1][k2] = int(v)
                else:
                    engine_config[k1][k2] = v

        except ValueError as e:
            cherrypy.log.error("Ignoring environ '{}': " + str(e))
        except Exception as e:
            cherrypy.log(
                "WARNING: skipping environ '{}' on exception '{}'".format(k, e)
            )

    if update_dict:
        cherrypy.config.update(update_dict)
        engine_config["global"].update(update_dict)

    # logging cherrypy
    log_format_simple = (
        "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)s %(message)s"
    )
    log_formatter_simple = logging.Formatter(
        log_format_simple, datefmt="%Y-%m-%dT%H:%M:%S"
    )
    logger_server = logging.getLogger("cherrypy.error")
    logger_access = logging.getLogger("cherrypy.access")
    logger_cherry = logging.getLogger("cherrypy")
    logger_nbi = logging.getLogger("nbi")

    if "log.file" in engine_config["global"]:
        file_handler = logging.handlers.RotatingFileHandler(
            engine_config["global"]["log.file"], maxBytes=100e6, backupCount=9, delay=0
        )
        file_handler.setFormatter(log_formatter_simple)
        logger_cherry.addHandler(file_handler)
        logger_nbi.addHandler(file_handler)
    # log always to standard output
    for format_, logger in {
        "nbi.server %(filename)s:%(lineno)s": logger_server,
        "nbi.access %(filename)s:%(lineno)s": logger_access,
        "%(name)s %(filename)s:%(lineno)s": logger_nbi,
    }.items():
        log_format_cherry = "%(asctime)s %(levelname)s {} %(message)s".format(format_)
        log_formatter_cherry = logging.Formatter(
            log_format_cherry, datefmt="%Y-%m-%dT%H:%M:%S"
        )
        str_handler = logging.StreamHandler()
        str_handler.setFormatter(log_formatter_cherry)
        logger.addHandler(str_handler)

    if engine_config["global"].get("log.level"):
        logger_cherry.setLevel(engine_config["global"]["log.level"])
        logger_nbi.setLevel(engine_config["global"]["log.level"])

    # logging other modules
    for k1, logname in {
        "message": "nbi.msg",
        "database": "nbi.db",
        "storage": "nbi.fs",
    }.items():
        engine_config[k1]["logger_name"] = logname
        logger_module = logging.getLogger(logname)
        if "logfile" in engine_config[k1]:
            file_handler = logging.handlers.RotatingFileHandler(
                engine_config[k1]["logfile"], maxBytes=100e6, backupCount=9, delay=0
            )
            file_handler.setFormatter(log_formatter_simple)
            logger_module.addHandler(file_handler)
        if "loglevel" in engine_config[k1]:
            logger_module.setLevel(engine_config[k1]["loglevel"])
    # TODO add more entries, e.g.: storage
    cherrypy.tree.apps["/osm"].root.engine.start(engine_config)
    cherrypy.tree.apps["/osm"].root.authenticator.start(engine_config)
    cherrypy.tree.apps["/osm"].root.engine.init_db(target_version=database_version)
    cherrypy.tree.apps["/osm"].root.authenticator.init_db(
        target_version=auth_database_version
    )

    cef_logger = cef_event_builder(engine_config["authentication"])

    # start subscriptions thread:
    subscription_thread = SubscriptionThread(
        config=engine_config, engine=nbi_server.engine
    )
    subscription_thread.start()
    # Do not capture except SubscriptionException

    backend = engine_config["authentication"]["backend"]
    current_backend = backend
    cherrypy.log.error(
        "Starting OSM NBI Version '{} {}' with '{}' authentication backend".format(
            nbi_version, nbi_version_date, backend
        )
    )


def _stop_service():
    """
    Callback function called when cherrypy.engine stops
    TODO: Ending database connections.
    """
    global subscription_thread
    if subscription_thread:
        subscription_thread.terminate()
    subscription_thread = None
    cherrypy.tree.apps["/osm"].root.engine.stop()
    cherrypy.log.error("Stopping osm_nbi")


def nbi(config_file):
    global nbi_server
    nbi_server = Server()
    cherrypy.engine.subscribe("start", _start_service)
    cherrypy.engine.subscribe("stop", _stop_service)
    cherrypy.quickstart(nbi_server, "/osm", config_file)


def usage():
    print(
        """Usage: {} [options]
        -c|--config [configuration_file]: loads the configuration file (default: ./nbi.cfg)
        -h|--help: shows this help
        """.format(
            sys.argv[0]
        )
    )
    # --log-socket-host HOST: send logs to this host")
    # --log-socket-port PORT: send logs using this port (default: 9022)")


if __name__ == "__main__":
    try:
        # load parameters and configuration
        opts, args = getopt.getopt(sys.argv[1:], "hvc:", ["config=", "help"])
        # TODO add  "log-socket-host=", "log-socket-port=", "log-file="
        config_file = None
        for o, a in opts:
            if o in ("-h", "--help"):
                usage()
                sys.exit()
            elif o in ("-c", "--config"):
                config_file = a
            # elif o == "--log-socket-port":
            #     log_socket_port = a
            # elif o == "--log-socket-host":
            #     log_socket_host = a
            # elif o == "--log-file":
            #     log_file = a
            else:
                raise getopt.GetoptError(f"Unhandled option: {o}")
        if config_file:
            if not path.isfile(config_file):
                print(
                    "configuration file '{}' that not exist".format(config_file),
                    file=sys.stderr,
                )
                exit(1)
        else:
            for config_file in (
                __file__[: __file__.rfind(".")] + ".cfg",
                "./nbi.cfg",
                "/etc/osm/nbi.cfg",
            ):
                if path.isfile(config_file):
                    break
            else:
                print(
                    "No configuration file 'nbi.cfg' found neither at local folder nor at /etc/osm/",
                    file=sys.stderr,
                )
                exit(1)
        nbi(config_file)
    except getopt.GetoptError as e:
        print(str(e), file=sys.stderr)
        # usage()
        exit(1)
