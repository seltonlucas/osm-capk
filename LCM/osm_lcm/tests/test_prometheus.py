##
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
# contact: alfonso.tiernosepulveda@telefonica.com
##

import asynctest
from osm_lcm.prometheus import parse_job

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"


class TestPrometheus(asynctest.TestCase):
    def test_parse_job(self):
        text_to_parse = """
            # yaml format with jinja2
            key1: "parsing var1='{{ var1 }}'"
            key2: "parsing var2='{{ var2 }}'"
        """
        vars = {"var1": "VAR1", "var2": "VAR2", "var3": "VAR3"}
        expected = {"key1": "parsing var1='VAR1'", "key2": "parsing var2='VAR2'"}
        result = parse_job(text_to_parse, vars)
        self.assertEqual(result, expected, "Error at jinja2 parse")


if __name__ == "__main__":
    asynctest.main()
