# -*- coding: utf-8 -*-

##
# Copyright 2020 Telefonica S.A.
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

import yaml
from osm_lcm.lcm_utils import LcmException
from jinja2 import Template, TemplateError, TemplateNotFound, TemplateSyntaxError

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"


def parse_job(job_data: str, variables: dict) -> dict:
    try:
        template = Template(job_data)
        job_parsed = template.render(variables or {})
        return yaml.safe_load(job_parsed)
    except (TemplateError, TemplateNotFound, TemplateSyntaxError) as e:
        # TODO yaml exceptions
        raise LcmException(
            "Error parsing Jinja2 to prometheus job. job_data={}, variables={}. Error={}".format(
                job_data, variables, e
            )
        )
