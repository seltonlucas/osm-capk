# Copyright 2022 Canonical Ltd.
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

from unittest import TestCase
from osm_lcm.osm_config import OsmConfigBuilder


class TestOsmConfig(TestCase):
    def test_k8s_services(self):
        input_services = {
            "services": [
                {
                    "name": "ldap",
                    "type": "LoadBalancer",
                    "external_ip": ["1.1.1.1"],
                    "ports": [{"name": "ldap", "port": 1234, "protocol": "TCP"}],
                },
                {
                    "name": "ldap-internal",
                    "type": "ClusterIP",
                    "cluster_ip": "10.10.10.10",
                    "ports": [
                        {"name": "ldap-internal", "port": 1234, "protocol": "TCP"}
                    ],
                },
            ]
        }
        expected_services = {
            "ldap": {
                "type": "LoadBalancer",
                "ip": ["1.1.1.1"],
                "ports": {"ldap": {"port": 1234, "protocol": "TCP"}},
            },
            "ldap-internal": {
                "type": "ClusterIP",
                "ip": ["10.10.10.10"],
                "ports": {"ldap-internal": {"port": 1234, "protocol": "TCP"}},
            },
        }
        self.assertEqual(
            OsmConfigBuilder(k8s=input_services).build(),
            {"v0": {"k8s": {"services": expected_services}}},
        )
