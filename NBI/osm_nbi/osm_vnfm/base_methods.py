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


import logging


class BaseMethod:
    def __init__(self):
        """
        Constructor of the base method
        """
        self.logger = logging.getLogger("nbi.engine")
