#######################################################################################
# Copyright ETSI Contributors and Others.
#
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
#######################################################################################


from jinja2 import Environment, PackageLoader, select_autoescape
import json
import yaml


def render_jinja_template(self, template_file, output_file=None, **kwargs):
    """Renders a jinja template with the provided values

    Args:
        template_file: Jinja template to be rendered
        output_file: Output file
        kwargs: (key,value) pairs to be replaced in the template

    Returns:
        content: The content of the rendered template
    """

    # Load the template from file
    # loader = FileSystemLoader("osm_lcm/odu_libs/templates")
    loader = PackageLoader("osm_lcm", "odu_libs/templates")
    self.logger.debug(f"Loader: {loader}")
    env = Environment(loader=loader, autoescape=select_autoescape())
    self.logger.debug(f"Env: {env}")

    template_list = env.list_templates()
    self.logger.debug(f"Template list: {template_list}")
    template = env.get_template(template_file)
    self.logger.debug(f"Template: {template}")

    # Replace kwargs
    self.logger.debug(f"Kwargs: {kwargs}")
    content = template.render(kwargs)
    if output_file:
        with open(output_file, "w") as c_file:
            c_file.write(content)
    return content


def render_yaml_template(self, template_file, output_file=None, **kwargs):
    """Renders a YAML template with the provided values

    Args:
        template_file: Yaml template to be rendered
        output_file: Output file
        kwargs: (key,value) pairs to be replaced in the template

    Returns:
        content: The content of the rendered template
    """

    def print_yaml_json(document, to_json=False):
        if to_json:
            print(json.dumps(document, indent=4))
        else:
            print(
                yaml.safe_dump(
                    document, indent=4, default_flow_style=False, sort_keys=False
                )
            )

    # Load template in dictionary
    with open(template_file, "r") as t_file:
        content_dict = yaml.safe_load(t_file.read())
    # Replace kwargs
    self.self.logger.debug(f"Kwargs: {kwargs}")
    for k, v in kwargs:
        content_dict[k] = v

    content = print_yaml_json(content_dict)
    if output_file:
        with open(output_file, "w") as c_file:
            c_file.write(content)
    return content
