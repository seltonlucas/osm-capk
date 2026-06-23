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

from osm_nbi.base_topic import BaseTopic
from .osm_vnfm.vnf_instances import VnfInstances2NsInstances
from .osm_vnfm.vnf_instance_actions import VnfLcmOp2NsLcmOp


class VnfInstances(BaseTopic):
    def __init__(self, db, fs, msg, auth):
        """
        Constructor call for vnf instance topic
        """
        BaseTopic.__init__(self, db, fs, msg, auth)
        self.vnfinstances2nsinstances = VnfInstances2NsInstances(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates new vnf instance
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the vnf instance
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: the _id of vnf instance created at database. Or an exception.
        """
        return self.vnfinstances2nsinstances.new(
            rollback, session, indata, kwargs, headers
        )

    def list(self, session, filter_q=None, api_req=False):
        """
        Get a list of the vnf instances that match a filter
        :param session: contains the used login username and working project
        :param filter_q: filter of data to be applied
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: The list, it can be empty if no one match the filter.
        """
        return self.vnfinstances2nsinstances.list(session, filter_q, api_req)

    def show(self, session, _id, filter_q=None, api_req=False):
        """
        Get complete information on an vnf instance
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: dictionary, raise exception if not found.
        """
        return self.vnfinstances2nsinstances.show(session, _id, api_req)

    def delete(self, session, _id, dry_run=False, not_send_msg=None):
        """
        Delete vnf instance by its internal _id
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param dry_run: make checking but do not delete
        :param not_send_msg: To not send message (False) or store content (list) instead
        :return: operation id (None if there is not operation), raise exception if error or not found, conflict, ...
        """
        return self.vnfinstances2nsinstances.delete(session, _id, dry_run, not_send_msg)


class VnfLcmOpTopic(BaseTopic):
    def __init__(self, db, fs, msg, auth):
        """
        Constructor call for vnf lcm op topic
        """
        BaseTopic.__init__(self, db, fs, msg, auth)
        self.vnflcmop2nslcmop = VnfLcmOp2NsLcmOp(db, fs, msg, auth)

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates new vnf lcm op
        :param rollback: list to append the created items at database in case a rollback must be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: params to be used for the vnf instance
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: the _id of vnf lcm op created at database. Or an exception.
        """
        return self.vnflcmop2nslcmop.new(rollback, session, indata, kwargs, headers)

    def list(self, session, filter_q=None, api_req=False):
        """
        Get a list of the vnf lcm op that match a filter
        :param session: contains the used login username and working project
        :param filter_q: filter of data to be applied
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: The list, it can be empty if no one match the filter.
        """
        return self.vnflcmop2nslcmop.list(session, filter_q, api_req)

    def show(self, session, _id, filter_q=None, api_req=False):
        """
        Get complete information on an vnf lcm op
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param api_req: True if this call is serving an external API request. False if serving internal request.
        :return: dictionary, raise exception if not found.
        """
        return self.vnflcmop2nslcmop.show(session, _id, api_req)
