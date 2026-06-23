# Copyright 2020 K Sai Kiran (Tata Elxsi)
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

__author__ = "K Sai Kiran <saikiran.k@tataelxsi.co.in>"
__date__ = "$28-Apr-2020 23:59:59$"

import asyncio
import aiohttp
import ssl
import certifi
from http import HTTPStatus
import json
import logging
import time
from uuid import uuid4


class NotificationException(Exception):
    """
    Notification Exception
    """

    def __init__(self, message: str, http_code: int = HTTPStatus.BAD_REQUEST) -> None:
        """
        Constructor of notification exception
        :param message: String text containing exception details.
        :param http_code: HTTP status code of exception.
        """
        self.http_code = http_code
        Exception.__init__(self, message)


class NotificationBase:
    response_models = None
    # Common HTTP payload header for all notifications.
    payload_header = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(self, db) -> None:
        """
        Constructor of NotificationBase class.
        :param db: Database handler.
        """
        self.db = db
        self.logger = logging.getLogger("nbi.notifications")
        self.subscriber_collection = None

    def get_models(self) -> dict:
        """
        Returns the SOL005 model of notification class
        :param None
        :return: dict of SOL005 data model
        """
        return NotificationBase.response_models

    def get_subscribers(self, **kwargs) -> NotificationException:
        """
        Method should be implemented by all notification subclasses
        :param kwargs: any keyword arguments needed for db query.
        :return: List of subscribers
        """
        raise NotificationException(
            "Method get_subscribers() is not implemented",
            http_code=HTTPStatus.NOT_IMPLEMENTED,
        )

    @staticmethod
    def _get_basic_auth(username: str, password: str) -> tuple:
        return aiohttp.BasicAuth(username, password)

    def _decrypt_password(
        self, hashed: str, salt: str, schema_version: str = "1.1"
    ) -> str:
        return self.db.decrypt(hashed, schema_version, salt=salt)

    def get_payload(self, meta_notification: dict) -> dict:
        """
        Generates SOL005 compliant payload structure and returns them in dictionary.
        :param meta_notification: notification meta data which needs to be formatted as SOL005 compliant
        :return: A dictionary which is SOL005 compliant.
        """
        model_name = meta_notification["notificationType"]
        response_models = self.get_models()
        if not response_models or not response_models.get(model_name):
            raise NotificationException(
                "Response model {} is not defined.".format(model_name),
                HTTPStatus.NOT_IMPLEMENTED,
            )
        model_keys = response_models[model_name]
        payload = dict.fromkeys(model_keys, "N/A")
        notification_keys = set(meta_notification.keys())
        for model_key in model_keys.intersection(notification_keys):
            payload[model_key] = meta_notification[model_key]
        self.logger.debug(
            "Payload generated for subscriber: {} for {}".format(
                payload["subscriptionId"], payload["notificationType"]
            )
        )
        return payload

    async def send_notifications(
        self,
        subscribers: list,
    ):
        """
        Generate tasks for all notification for an event.
        :param subscribers: A list of subscribers who want to be notified for event.
        """
        notifications = []
        for subscriber in subscribers:
            # Notify without auth
            if not subscriber.get("authentication"):
                notifications.append(
                    {
                        "headers": self.payload_header,
                        "payload": self.get_payload(subscriber),
                        "CallbackUri": subscriber["CallbackUri"],
                    }
                )
            elif subscriber["authentication"]["authType"] == "basic":
                salt = subscriber["subscriptionId"]
                hashed_password = subscriber["authentication"]["paramsBasic"][
                    "password"
                ]
                password = self._decrypt_password(hashed_password, salt)
                auth_basic = self._get_basic_auth(
                    subscriber["authentication"]["paramsBasic"]["userName"], password
                )
                notifications.append(
                    {
                        "headers": self.payload_header,
                        "payload": self.get_payload(subscriber),
                        "auth_basic": auth_basic,
                        "CallbackUri": subscriber["CallbackUri"],
                    }
                )
            # TODO add support for AuthType OAuth and TLS after support is added in subscription.
            else:
                self.logger.debug(
                    "Subscriber {} can not be notified. {} notification auth type is not implemented".format(
                        subscriber["subscriptionId"],
                        subscriber["authentication"]["authType"],
                    )
                )

        if notifications:
            tasks = []
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            conn = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=conn) as session:
                for notification in notifications:
                    tasks.append(
                        asyncio.ensure_future(
                            self.send_notification(session, notification),
                        )
                    )
                await asyncio.gather(*tasks)

    async def send_notification(
        self,
        session: aiohttp.ClientSession,
        notification: dict,
        retry_count: int = 5,
        timeout: float = 5.0,
    ):
        """
        Performs HTTP Post request to notify subscriber. In case if for any reason notification is not sent successfully
        after maximum number of reties, then notification is dropped.
        :param session: An aiohttp client session object to maintain http session.
        :param notification: A dictionary containing all necessary data to make POST request.
        :param retry_count: An integer specifying the maximum number of reties for a notification.
        :param timeout: A float representing client timeout of each HTTP request.
        """
        backoff_delay = 1
        while retry_count > 0:
            try:
                async with session.post(
                    url=notification["CallbackUri"],
                    headers=notification["headers"],
                    auth=notification.get("auth_basic", None),
                    data=json.dumps(notification["payload"]),
                    timeout=timeout,
                ) as resp:
                    # self.logger.debug("Notification response: {}".format(resp.status))
                    if resp.status == HTTPStatus.NO_CONTENT:
                        self.logger.debug(
                            "Notification sent successfully to subscriber {}".format(
                                notification["payload"]["subscriptionId"]
                            )
                        )
                    else:
                        error_text = "Erroneous response code: {}, ".format(resp.status)
                        error_text += await resp.text()
                        raise NotificationException(error_text)
                return True
            except Exception as e:
                error_text = type(e).__name__ + ": " + str(e)
                self.logger.debug(
                    "Unable to send notification to subscriber {}. Details: {}".format(
                        notification["payload"]["subscriptionId"], error_text
                    )
                )
                error_detail = {
                    "error": type(e).__name__,
                    "error_text": str(e),
                    "timestamp": time.time(),
                }
                if "error_details" in notification["payload"].keys():
                    notification["payload"]["error_details"].append(error_detail)
                else:
                    notification["payload"]["error_details"] = [error_detail]
                retry_count -= 1
                backoff_delay *= 2
                self.logger.debug(
                    "Retry Notification for subscriber: {} after backoff delay: {} seconds.".format(
                        notification["payload"]["subscriptionId"], backoff_delay
                    )
                )
                await asyncio.sleep(backoff_delay)
        # Dropping notification
        self.logger.debug(
            "Notification {} sent failed to subscriber:{}.".format(
                notification["payload"]["notificationType"],
                notification["payload"]["subscriptionId"],
            )
        )
        return False


class NsLcmNotification(NotificationBase):
    # maps kafka commands of completed operations to the original operation type
    completed_operation_map = {
        "INSTANTIATED": "INSTANTIATE",
        "SCALED": "SCALE",
        "TERMINATED": "TERMINATE",
        "UPDATED": "UPDATE",
        "HEALED": "HEAL",
    }
    # SOL005 response model for nslcm notifications
    response_models = {
        "NsLcmOperationOccurrenceNotification": {
            "id",
            "nsInstanceId",
            "nsLcmOpOccId",
            "operation",
            "notificationType",
            "subscriptionId",
            "timestamp",
            "notificationStatus",
            "operationState",
            "isAutomaticInvocation",
            "affectedVnf",
            "affectedVl",
            "affectedVnffg",
            "affectedNs",
            "affectedSap",
            "error",
            "_links",
        },
        "NsIdentifierCreationNotification": {
            "notificationType",
            "subscriptionId",
            "timestamp",
            "nsInstanceId",
            "_links",
        },
        "NsIdentifierDeletionNotification": {
            "notificationType",
            "subscriptionId",
            "timestamp",
            "nsInstanceId",
            "_links",
        },
        "NsChangeNotification": {
            "nsInstanceId",
            "nsComponentType",
            "nsComponentId",
            "lcmOpOccIdImpactngNsComponent",
            "lcmOpNameImpactingNsComponent",
            "lcmOpOccStatusImpactingNsComponent",
            "notificationType",
            "subscriptionId",
            "timeStamp",
            "error",
            "_links",
        },
    }

    def __init__(self, db) -> None:
        """
        Constructor of NsLcmNotification class.
        :param db: Database handler.
        """
        super().__init__(db)
        self.subscriber_collection = "mapped_subscriptions"

    def get_models(self) -> dict:
        """
        Returns the SOL005 model of notification class
        :param None
        :return: dict of SOL005 data model
        """
        return NsLcmNotification.response_models

    @staticmethod
    def _format_nslcm_subscribers(subscribers: list, event_details: dict) -> list:
        """
        Formats the raw event details from kakfa message and subscriber details.
        :param subscribers: A list of subscribers whom the event needs to be notified.
        :param event_details: A dict containing all meta data of event.
        :return:
        """
        notification_id = str(uuid4())
        event_timestamp = event_details["params"]["startTime"]
        resource_links = event_details["params"]["links"]
        event_operation = event_details["command"]
        for key in ["_admin", "_id", "id", "links"]:
            event_details["params"].pop(key, None)
        for subscriber in subscribers:
            subscriber["id"] = notification_id
            subscriber["timestamp"] = event_timestamp
            subscriber["_links"] = resource_links
            subscriber["subscriptionId"] = subscriber["reference"]
            subscriber["operation"] = event_operation
            del subscriber["reference"]
            del subscriber["_id"]
            subscriber.update(event_details["params"])
        return subscribers

    def get_subscribers(
        self,
        nsd_id: str,
        ns_instance_id: str,
        command: str,
        op_state: str,
        event_details: dict,
    ) -> list:
        """
        Queries database and returns list of subscribers.
        :param nsd_id: NSD id of an NS whose lifecycle has changed. (scaled, terminated. etc)
        :param ns_instance_id: NS instance id an NS whose lifecycle has changed.
        :param command: the command for event.
        :param op_state: the operation state of NS.
        :param event_details: dict containing raw data of event occured.
        :return: List of interested subscribers for occurred event.
        """
        notification_type = [
            "NsLcmOperationOccurrenceNotification",
            "NsChangeNotification",
            "NsIdentifierCreationNotification",
            "NsIdentifierDeletionNotification",
        ]
        filter_q = {
            "identifier": [nsd_id, ns_instance_id],
            "operationStates": ["ANY"],
            "operationTypes": ["ANY"],
            "notificationType": notification_type,
        }
        if op_state:
            filter_q["operationStates"].append(op_state)
        if command:
            op_type = self.completed_operation_map.get(command, command)
            filter_q["operationTypes"].append(op_type)
        # self.logger.debug("Db query is: {}".format(filter_q))
        subscribers = []
        try:
            subscribers = self.db.get_list(self.subscriber_collection, filter_q)
            subscribers = self._format_nslcm_subscribers(subscribers, event_details)
        except Exception as e:
            error_text = type(e).__name__ + ": " + str(e)
            self.logger.debug("Error getting nslcm subscribers: {}".format(error_text))
        finally:
            return subscribers


class VnfLcmNotification(NotificationBase):
    # SOL003 response model for vnflcm notifications
    response_models = {
        "VnfLcmOperationOccurrenceNotification": {
            "id",
            "notificationType",
            "subscriptionId",
            "timeStamp",
            "notificationStatus",
            "operationState",
            "vnfInstanceId",
            "operation",
            "isAutomaticInvocation",
            "vnfLcmOpOccId",
            "affectedVnfcs",
            "affectedVirtualLinks",
            "affectedExtLinkPorts",
            "affectedVirtualStorages",
            "changedInfo",
            "changedExtConnectivity",
            "modificationsTriggeredByVnfPkgChange",
            "error",
            "_links",
        },
        "VnfIdentifierCreationNotification": {
            "id",
            "notificationType",
            "subscriptionId",
            "timeStamp",
            "vnfInstanceId",
            "_links",
        },
        "VnfIdentifierDeletionNotification": {
            "id",
            "notificationType",
            "subscriptionId",
            "timeStamp",
            "vnfInstanceId",
            "_links",
        },
    }

    def __init__(self, db) -> None:
        """
        Constructor of VnfLcmNotification class.
        :param db: Database handler.
        """
        super().__init__(db)
        self.subscriber_collection = "mapped_subscriptions"

    def get_models(self) -> dict:
        """
        Returns the SOL003 model of notification class
        :param None
        :return: dict of SOL003 data model
        """
        return self.response_models

    def _format_vnflcm_subscribers(
        self, subscribers: list, event_details: dict
    ) -> list:
        """
        Formats the raw event details from kafka message and subscriber details.
        :param subscribers: A list of subscribers whom the event needs to be notified.
        :param event_details: A dict containing all meta data of event.
        :return:
        """
        notification_id = str(uuid4())
        event_timestamp = time.time()
        event_operation = event_details["command"]
        for subscriber in subscribers:
            subscriber["id"] = notification_id
            subscriber["timeStamp"] = event_timestamp
            subscriber["subscriptionId"] = subscriber["reference"]
            subscriber["operation"] = event_operation
            del subscriber["reference"]
            del subscriber["_id"]
            subscriber.update(event_details["params"])
        return subscribers

    def get_subscribers(
        self,
        vnfd_id: str,
        vnf_instance_id: str,
        command: str,
        op_state: str,
        event_details: dict,
    ) -> list:
        """
        Queries database and returns list of subscribers.
        :param vnfd_id: Vnfd id of a VNF whose lifecycle has changed. (instantiated, scaled, terminated. etc)
        :param vnf_instance_id: Vnf instance id of a VNF whose lifecycle has changed.
        :param command: the command for event.
        :param op_state: the operation state of VNF.
        :param event_details: dict containing raw data of event occurred.
        :return: List of interested subscribers for occurred event.
        """
        notification_type = [
            "VnfIdentifierCreationNotification",
            "VnfLcmOperationOccurrenceNotification",
            "VnfIdentifierDeletionNotification",
        ]
        filter_q = {
            "identifier": [vnfd_id, vnf_instance_id],
            "operationStates": ["ANY"],
            "operationTypes": ["ANY"],
            "notificationType": notification_type,
        }
        if op_state:
            filter_q["operationStates"].append(op_state)
        if command:
            filter_q["operationTypes"].append(command)
        subscribers = []
        try:
            subscribers = self.db.get_list(self.subscriber_collection, filter_q)
            subscribers = self._format_vnflcm_subscribers(subscribers, event_details)
        except Exception as e:
            error_text = type(e).__name__ + ": " + str(e)
            self.logger.debug("Error getting vnflcm subscribers: {}".format(error_text))
        finally:
            return subscribers


class NsdNotification(NotificationBase):
    def __init__(self, db):
        """
        Constructor of the class
        """
        super().__init__(db)
        # TODO will update this once support is there from subscription
        self.response_models = {}
        self.subscriber_collection = None


class VnfdNotification(NotificationBase):
    def __init__(self, db):
        """
        Constructor of the class
        """
        super().__init__(db)
        # TODO will update this once support is there from subscription
        self.response_models = {}
        self.subscriber_collection = None
