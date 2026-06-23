# Copyright 2021 K Sai Kiran (Tata Elxsi)
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

__author__ = "K Sai Kiran <saikiran.k@tataelxsi.co.in>, Selvi Jayaraman <selvi.j@tataelxsi.co.in>"
__date__ = "$12-June-2021 8:30:59$"

from osm_nbi.instance_topics import NsrTopic, NsLcmOpTopic, VnfrTopic
from .base_methods import BaseMethod


class VnfLcmOp2NsLcmOp:
    def __init__(self, db, fs, msg, auth):
        """
        Constructor of Vnf lcm op to Ns lcm op
        """
        self.new_vnf_lcmop = NewVnfLcmOp(db, fs, msg, auth)
        self.list_vnf_lcmop = ListVnfLcmOp(db, fs, msg, auth)
        self.show_vnf_lcmop = ShowVnfLcmOp(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates a new entry into database.
        :param rollback: list to append created items at database in case a rollback may to be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: data to be inserted
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: _id, op_id:
            _id: identity of the inserted data.
             op_id: operation id if this is asynchronous, None otherwise
        """
        return self.new_vnf_lcmop.action(rollback, session, indata, kwargs, headers)

    def list(self, session, filter_q=None, api_req=False):
        """
        Get a list of the Vnf Lcm Operation that matches a filter
        :param session: contains the used login username and working project
        :param filter_q: filter of data to be applied
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: The list, it can be empty if no one match the filter.
        """
        return self.list_vnf_lcmop.action(session, filter_q, api_req)

    def show(self, session, _id, api_req=False):
        """
        Get complete information on an Vnf Lcm Operation
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: dictionary, raise exception if not found.
        """
        return self.show_vnf_lcmop.action(session, _id, api_req)


class NewVnfLcmOp(BaseMethod):
    def __init__(self, db, fs, msg, auth):
        """
        Constructor of new Vnf Lcm Op
        """
        super().__init__()
        self.msg = msg
        self.nslcmoptopic = NsLcmOpTopic(db, fs, msg, auth)
        self.nsrtopic = NsrTopic(db, fs, msg, auth)
        self.vnfrtopic = VnfrTopic(db, fs, msg, auth)

    def __get_nsdid(self, session, vnf_instance_id):
        """
        Returns a nsd id from vnf instance id.
        :param session: contains the used login username and working project
        :param vnf_instance_id: id of vnf instance
        :return: id of nsd id
        """
        nsr = self.nsrtopic.show(session, vnf_instance_id)
        return nsr["nsd"]["_id"]

    def __get_formatted_indata(self, session, indata):
        """
        Returns formatted data for new vnf lcm op
        :param session: contains the used login username and working project
        :param indata: contains information for new lcm operation.
        :return: formatted indata for new lcm op.
        """
        formatted_indata = {}
        if indata["lcmOperationType"] == "instantiate":
            formatted_indata = {
                "nsName": indata["vnfName"],
                "nsDescription": indata["vnfDescription"],
                "nsdId": self.__get_nsdid(session, indata["vnfInstanceId"]),
                "vimAccountId": indata["vimAccountId"],
                "nsr_id": indata["vnfInstanceId"],
                "lcmOperationType": indata["lcmOperationType"],
                "nsInstanceId": indata["vnfInstanceId"],
            }
        elif indata["lcmOperationType"] == "terminate":
            formatted_indata = {
                "lcmOperationType": indata["lcmOperationType"],
                "nsInstanceId": indata["vnfInstanceId"],
            }
        elif indata["lcmOperationType"] == "scale":
            formatted_indata = {
                "lcmOperationType": indata["lcmOperationType"],
                "nsInstanceId": indata["vnfInstanceId"],
                "scaleType": "SCALE_VNF",
                "scaleVnfData": {
                    "scaleVnfType": indata["type"],
                    "scaleByStepData": {
                        "scaling-group-descriptor": indata["aspectId"],
                        "member-vnf-index": indata["additionalParams"][
                            "member-vnf-index"
                        ],
                    },
                },
            }
        elif indata["lcmOperationType"] == "action":
            formatted_indata = {
                "lcmOperationType": indata["lcmOperationType"],
                "nsInstanceId": indata["vnfInstanceId"],
                "member_vnf_index": indata["member_vnf_index"],
                "primitive": indata["primitive"],
                "primitive_params": indata["primitive_params"],
            }
        return formatted_indata

    def notify_operation(self, session, _id, lcm_operation, op_id):
        """
        Formats the operation message params and sends to kafka
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: vnf instance id
        :param lcm_operation: lcm operation type of a VNF (instantiate, scale, terminate)
        :param op_id: lcm operation id of a VNF
        :return: None
        """
        vnfInstanceId = _id
        operation = lcm_operation
        nslcmop_rec = self.nslcmoptopic.show(session, op_id)
        operation_status = nslcmop_rec["operationState"]
        vnfr = self.vnfrtopic.show(session, vnfInstanceId)
        links = {
            "self": "/osm/vnflcm/v1/vnf_lcm_op_occs/" + op_id,
            "vnfInstance": "/osm/vnflcm/v1/vnf_instances/" + vnfInstanceId,
        }
        params = {
            "vnfdId": vnfr["vnfd-ref"],
            "vnfInstanceId": vnfInstanceId,
            "operationState": operation_status,
            "vnfLcmOpOccId": op_id,
            "_links": links,
        }
        self.msg.write("vnf", operation, params)
        return None

    def action(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates an new lcm operation.
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the nsr
        :param kwargs: used to override the indata
        :param headers: http request headers
        :return: id of new lcm operation.
        """
        vnfInstanceId = indata["vnfInstanceId"]
        lcm_operation = indata["lcmOperationType"]
        vnfr = self.vnfrtopic.show(session, vnfInstanceId)
        indata["vnfInstanceId"] = vnfr.get("nsr-id-ref")
        indata = self.__get_formatted_indata(session, indata)
        op_id, nsName, _ = self.nslcmoptopic.new(
            rollback, session, indata, kwargs, headers
        )
        self.notify_operation(session, vnfInstanceId, lcm_operation, op_id)
        return op_id, nsName, _


class ListVnfLcmOp(BaseMethod):
    def __init__(self, db, fs, msg, auth):
        """
        Constructor call for listing vnf lcm operations
        """
        super().__init__()
        self.nslcmoptopic = NsLcmOpTopic(db, fs, msg, auth)
        self.nsrtopic = NsrTopic(db, fs, msg, auth)

    def action(self, session, filter_q=None, api_req=False):
        """
        To get list of vnf lcm operations that matches a filter
        :param session: contains the used login username and working project
        :param filter_q: filter of data to be applied
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: The list, it can be empty if no one match the filter.
        """
        list = []
        records = self.nslcmoptopic.list(session, filter_q, api_req)
        for record in records:
            ns_id = record.get("nsInstanceId")
            nsr = self.nsrtopic.show(session, ns_id)
            vnfInstance_id = nsr["constituent-vnfr-ref"][0]
            outdata = sol003_projection(record, vnfInstance_id)
            list.append(outdata)
        return list


class ShowVnfLcmOp(BaseMethod):
    def __init__(self, db, fs, msg, auth):
        """
        Constructor call for showing vnf lcm operation
        """
        super().__init__()
        self.nslcmoptopic = NsLcmOpTopic(db, fs, msg, auth)
        self.nsrtopic = NsrTopic(db, fs, msg, auth)

    def action(self, session, _id, api_req=False):
        """
        Get complete information on an Vnf Lcm Operation.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: Vnf Lcm operation id
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: dictionary, raise exception if not found.
        """
        record = self.nslcmoptopic.show(session, _id, api_req)
        ns_id = record.get("nsInstanceId")
        nsr = self.nsrtopic.show(session, ns_id)
        vnfinstance_id = nsr["constituent-vnfr-ref"][0]
        outdata = sol003_projection(record, vnfinstance_id)
        return outdata


def sol003_projection(data, vnfinstance_id):
    """
    Returns SOL003 formatted data
    :param data: contains Lcm Operation information
    :param vnfinstance_id: id of vnf_instance
    :return: SOL003 formatted data of vnf lcm op
    """
    data.pop("nsInstanceId")
    data.pop("operationParams")
    data.pop("links")
    links = {
        "self": "/osm/vnflcm/v1/vnf_lcm_op_occs/" + data["_id"],
        "vnfInstance": "/osm/vnflcm/v1/vnf_instances/" + vnfinstance_id,
    }
    data["_links"] = links
    data["vnfInstanceId"] = vnfinstance_id
    return data
