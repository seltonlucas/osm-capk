# -*- coding: utf-8 -*-

# Copyright 2020 Whitestack, LLC
# *************************************************************
#
# This file is part of OSM LCM module
# All Rights Reserved to Whitestack, LLC
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
#
# For those usages not covered by the Apache License, Version 2.0 please
# contact: fbravo@whitestack.com or agarcia@whitestack.com
##

import logging
from osm_common import dbmemory, dbmongo
from osm_common.dbbase import DbException


class Database:
    class __Database:
        def __init__(self, config):
            self.logger = logging.getLogger("lcm")
            try:
                # TODO check database version
                if config["database"]["driver"] == "mongo":
                    self.db = dbmongo.DbMongo()
                    self.db.db_connect(config["database"])
                elif config["database"]["driver"] == "memory":
                    self.db = dbmemory.DbMemory()
                    self.db.db_connect(config["database"])
                else:
                    raise Exception(
                        "Invalid configuration param '{}' at '[database]':'driver'".format(
                            config["database"]["driver"]
                        )
                    )
            except DbException as e:
                self.logger.critical(str(e), exc_info=True)
                raise Exception(str(e))

        def __str__(self):
            return repr(self) + self.db

    instance = None

    def __init__(self, config=None):
        if not Database.instance:
            Database.instance = Database.__Database(config)

    def __getattr__(self, name):
        return getattr(self.instance, name)
