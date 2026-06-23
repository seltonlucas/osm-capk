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

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, validator


def _get_ip_from_service(service: Dict[str, Any]) -> List[str]:
    return (
        [service["cluster_ip"]]
        if service["type"] == "ClusterIP"
        else service["external_ip"]
    )


class K8sConfigV0(BaseModel):
    services: List[Dict]

    @validator("services")
    @classmethod
    def parse_services(cls, services: Dict[str, Any]):
        return {
            service["name"]: {
                "type": service["type"],
                "ip": _get_ip_from_service(service),
                "ports": {
                    port["name"]: {
                        "port": port["port"],
                        "protocol": port["protocol"],
                    }
                    for port in service["ports"]
                },
            }
            for service in services
        }


class OsmConfigV0(BaseModel):
    k8s: Optional[K8sConfigV0]


class OsmConfig(BaseModel):
    v0: OsmConfigV0


class OsmConfigBuilder:
    def __init__(self, k8s: Dict[str, Any] = {}) -> None:
        self._k8s = k8s
        self._configs = {}
        if k8s:
            self._configs["k8s"] = k8s

    def build(self) -> Dict[str, Any]:
        return OsmConfig(v0=OsmConfigV0(**self._configs)).dict()
