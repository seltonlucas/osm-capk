# -*- coding: utf-8 -*-

# This file is part of OSM Life-Cycle Management module
#
# Copyright 2022 ETSI
#
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
##

from osm_lcm.data_utils.database.database import Database

__author__ = (
    "Lluis Gifre <lluis.gifre@cttc.es>, Ricard Vilalta <ricard.vilalta@cttc.es>"
)


class WimAccountDB:
    db = None
    db_wims = {}

    @classmethod
    def initialize_db(cls):
        cls.db = Database().instance.db

    @classmethod
    def get_all_wim_accounts(cls):
        if not cls.db:
            cls.initialize_db()
        db_wims_list = cls.db.get_list("wim_accounts")
        cls.db_wims.update({db_wim["_id"]: db_wim for db_wim in db_wims_list})
        return cls.db_wims
