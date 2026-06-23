# Copyright 2021 Canonical Ltd.
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

from typing import Any, Dict, NoReturn


def safe_get_ee_relation(
    nsr_id: str, ee_relation: Dict[str, Any], vnf_profile_id: str = None
) -> Dict[str, Any]:
    return {
        "nsr-id": nsr_id,
        "vnf-profile-id": ee_relation.get("vnf-profile-id") or vnf_profile_id,
        "vdu-profile-id": ee_relation.get("vdu-profile-id"),
        "kdu-resource-profile-id": ee_relation.get("kdu-resource-profile-id"),
        "execution-environment-ref": ee_relation.get("execution-environment-ref"),
        "endpoint": ee_relation["endpoint"],
    }


class EELevel:
    VDU = "vdu"
    VNF = "vnf"
    KDU = "kdu"
    NS = "ns"

    @staticmethod
    def get_level(ee_relation: dict):
        """Get the execution environment level"""
        level = None
        if (
            not ee_relation["vnf-profile-id"]
            and not ee_relation["vdu-profile-id"]
            and not ee_relation["kdu-resource-profile-id"]
        ):
            level = EELevel.NS
        elif (
            ee_relation["vnf-profile-id"]
            and not ee_relation["vdu-profile-id"]
            and not ee_relation["kdu-resource-profile-id"]
        ):
            level = EELevel.VNF
        elif (
            ee_relation["vnf-profile-id"]
            and ee_relation["vdu-profile-id"]
            and not ee_relation["kdu-resource-profile-id"]
        ):
            level = EELevel.VDU
        elif (
            ee_relation["vnf-profile-id"]
            and not ee_relation["vdu-profile-id"]
            and ee_relation["kdu-resource-profile-id"]
        ):
            level = EELevel.KDU
        else:
            raise Exception("invalid relation endpoint")
        return level


class EERelation(dict):
    """Represents the execution environment of a relation"""

    def __init__(
        self,
        relation_ee: Dict[str, Any],
    ) -> NoReturn:
        """
        Args:
            relation_ee: Relation Endpoint object in the VNFd or NSd.
                      Example:
                        {
                            "nsr-id": <>,
                            "vdu-profile-id": <>,
                            "kdu-resource-profile-id": <>,
                            "vnf-profile-id": <>,
                            "execution-environment-ref": <>,
                            "endpoint": <>,
                        }
        """
        for key, value in relation_ee.items():
            self.__setitem__(key, value)

    @property
    def vdu_profile_id(self):
        """Returns the vdu-profile id"""
        return self["vdu-profile-id"]

    @property
    def kdu_resource_profile_id(self):
        """Returns the kdu-resource-profile id"""
        return self["kdu-resource-profile-id"]

    @property
    def vnf_profile_id(self):
        """Returns the vnf-profile id"""
        return self["vnf-profile-id"]

    @property
    def execution_environment_ref(self):
        """Returns the reference to the execution environment (id)"""
        return self["execution-environment-ref"]

    @property
    def endpoint(self):
        """Returns the endpoint of the execution environment"""
        return self["endpoint"]

    @property
    def nsr_id(self) -> str:
        """Returns the nsr id"""
        return self["nsr-id"]


class Relation(dict):
    """Represents a relation"""

    def __init__(self, name, provider: EERelation, requirer: EERelation) -> NoReturn:
        """
        Args:
            name: Name of the relation.
            provider: Execution environment that provides the service for the relation.
            requirer: Execution environment that requires the service from the provider.
        """
        self.__setitem__("name", name)
        self.__setitem__("provider", provider)
        self.__setitem__("requirer", requirer)

    @property
    def name(self) -> str:
        """Returns the name of the relation"""
        return self["name"]

    @property
    def provider(self) -> EERelation:
        """Returns the provider endpoint"""
        return self["provider"]

    @property
    def requirer(self) -> EERelation:
        """Returns the requirer endpoint"""
        return self["requirer"]


class DeployedComponent(dict):
    """Represents a deployed component (nsr["_admin"]["deployed"]["VCA" | "K8s"])"""

    def __init__(self, data: Dict[str, Any]):
        """
        Args:
            data: dictionary with the data of the deployed component
        """
        for key, value in data.items():
            self.__setitem__(key, value)

    @property
    def vnf_profile_id(self):
        """Returns the vnf-profile id"""
        return self["member-vnf-index"]

    @property
    def ee_id(self):
        raise NotImplementedError()

    @property
    def config_sw_installed(self) -> bool:
        raise NotImplementedError()


class DeployedK8sResource(DeployedComponent):
    """Represents a deployed component for a kdu resource"""

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)

    @property
    def ee_id(self):
        """Returns the execution environment id"""
        model = self["namespace"]
        application_name = self["resource-name"]
        return f"{model}.{application_name}.k8s"

    @property
    def config_sw_installed(self) -> bool:
        return True


class DeployedVCA(DeployedComponent):
    """Represents a VCA deployed component"""

    def __init__(self, nsr_id: str, deployed_vca: Dict[str, Any]) -> NoReturn:
        """
        Args:
            db_nsr: NS record
            vca_index: Vca index for the deployed VCA
        """
        super().__init__(deployed_vca)
        self.nsr_id = nsr_id

    @property
    def ee_id(self) -> str:
        """Returns the execution environment id"""
        return self["ee_id"]

    @property
    def vdu_profile_id(self) -> str:
        """Returns the vdu-profile id"""
        return self["vdu_id"]

    @property
    def execution_environment_ref(self) -> str:
        """Returns the execution environment id"""
        return self["ee_descriptor_id"]

    @property
    def config_sw_installed(self) -> bool:
        return self.get("config_sw_installed", False)

    @property
    def target_element(self) -> str:
        return self.get("target_element", "")
