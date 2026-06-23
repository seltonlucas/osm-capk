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

from typing import NoReturn

from osm_lcm.n2vc.utils import get_ee_id_components


class RelationEndpoint:
    """Represents an endpoint of an application"""

    def __init__(self, ee_id: str, vca_id: str, endpoint_name: str) -> NoReturn:
        """
        Args:
            ee_id: Execution environment id.
                   Format: "<model>.<application_name>.<machine_id>".
            vca_id: Id of the VCA. Identifies the Juju Controller
                    where the application is deployed
            endpoint_name: Name of the endpoint for the relation
        """
        ee_components = get_ee_id_components(ee_id)
        self._model_name = ee_components[0]
        self._application_name = ee_components[1]
        self._vca_id = vca_id
        self._endpoint_name = endpoint_name

    @property
    def application_name(self) -> str:
        """Returns the application name"""
        return self._application_name

    @property
    def endpoint(self) -> str:
        """Returns the application name and the endpoint. Format: <application>:<endpoint>"""
        return f"{self.application_name}:{self._endpoint_name}"

    @property
    def endpoint_name(self) -> str:
        """Returns the endpoint name"""
        return self._endpoint_name

    @property
    def model_name(self) -> str:
        """Returns the model name"""
        return self._model_name

    @property
    def vca_id(self) -> str:
        """Returns the vca id"""
        return self._vca_id

    def __str__(self) -> str:
        app = self.application_name
        endpoint = self.endpoint_name
        model = self.model_name
        vca = self.vca_id
        return f"{app}:{endpoint} (model: {model}, vca: {vca})"


class Offer:
    """Represents a juju offer"""

    def __init__(self, url: str, vca_id: str = None) -> NoReturn:
        """
        Args:
            url: Offer url. Format: <user>/<model>.<offer-name>.
        """
        self._url = url
        self._username = url.split(".")[0].split("/")[0]
        self._model_name = url.split(".")[0].split("/")[1]
        self._name = url.split(".")[1]
        self._vca_id = vca_id

    @property
    def model_name(self) -> str:
        """Returns the model name"""
        return self._model_name

    @property
    def name(self) -> str:
        """Returns the offer name"""
        return self._name

    @property
    def username(self) -> str:
        """Returns the username"""
        return self._username

    @property
    def url(self) -> str:
        """Returns the offer url"""
        return self._url

    @property
    def vca_id(self) -> str:
        """Returns the vca id"""
        return self._vca_id
