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
from unittest import TestCase
from unittest.mock import patch

from osm_lcm.n2vc.definitions import Offer, RelationEndpoint


@patch("osm_lcm.n2vc.definitions.get_ee_id_components")
class RelationEndpointTest(TestCase):
    def test_success(self, mock_get_ee_id_components) -> NoReturn:
        mock_get_ee_id_components.return_value = ("model", "application", "machine_id")
        relation_endpoint = RelationEndpoint(
            "model.application.machine_id",
            "vca",
            "endpoint",
        )
        self.assertEqual(relation_endpoint.model_name, "model")
        self.assertEqual(relation_endpoint.application_name, "application")
        self.assertEqual(relation_endpoint.vca_id, "vca")
        self.assertEqual(relation_endpoint.endpoint, "application:endpoint")
        self.assertEqual(relation_endpoint.endpoint_name, "endpoint")
        self.assertEqual(
            str(relation_endpoint), "application:endpoint (model: model, vca: vca)"
        )


class OfferTest(TestCase):
    def test_success(self) -> NoReturn:
        url = "admin/test-model.my-offer"
        offer = Offer(url)
        self.assertEqual(offer.model_name, "test-model")
        self.assertEqual(offer.name, "my-offer")
        self.assertEqual(offer.username, "admin")
        self.assertEqual(offer.url, url)
