# Copyright 2021 Selvi Jayaraman (Tata Elxsi)
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

__author__ = "Selvi Jayaraman <selvi.j@tataelxsi.co.in>"

from osm_nbi.subscription_topics import CommonSubscriptions
from osm_nbi.validation import vnf_subscription


class VnflcmSubscriptionsTopic(CommonSubscriptions):
    schema_new = vnf_subscription

    def _subscription_mapper(self, _id, data, table):
        """
        Performs data transformation on subscription request
        :param _id: subscription reference id
        :param data: data to be transformed
        :param table: table in which transformed data are inserted
        """
        formatted_data = []
        formed_data = {
            "reference": data.get("_id"),
            "CallbackUri": data.get("CallbackUri"),
        }
        if data.get("authentication"):
            formed_data.update({"authentication": data.get("authentication")})
        if data.get("filter"):
            if data["filter"].get("VnfInstanceSubscriptionFilter"):
                key = list(data["filter"]["VnfInstanceSubscriptionFilter"].keys())[0]
                identifier = data["filter"]["VnfInstanceSubscriptionFilter"][key]
                formed_data.update({"identifier": identifier})
            if data["filter"].get("notificationTypes"):
                for elem in data["filter"].get("notificationTypes"):
                    update_dict = formed_data.copy()
                    update_dict["notificationType"] = elem
                    if elem == "VnfIdentifierCreationNotification":
                        update_dict["operationTypes"] = "CREATE"
                        update_dict["operationStates"] = "ANY"
                        formatted_data.append(update_dict)
                    elif elem == "VnfIdentifierDeletionNotification":
                        update_dict["operationTypes"] = "DELETE"
                        update_dict["operationStates"] = "ANY"
                        formatted_data.append(update_dict)
                    elif elem == "VnfLcmOperationOccurrenceNotification":
                        if "operationTypes" in data["filter"].keys():
                            update_dict["operationTypes"] = data["filter"][
                                "operationTypes"
                            ]
                        else:
                            update_dict["operationTypes"] = "ANY"
                        if "operationStates" in data["filter"].keys():
                            update_dict["operationStates"] = data["filter"][
                                "operationStates"
                            ]
                        else:
                            update_dict["operationStates"] = "ANY"
                        formatted_data.append(update_dict)
        self.db.create_list(table, formatted_data)
        return None
