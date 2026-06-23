# Copyright 2020 Canonical Ltd.
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

import asyncio

from osm_lcm.n2vc.utils import Dict, N2VCDeploymentStatus
from osm_lcm.n2vc.n2vc_conn import N2VCConnector
from unittest.mock import MagicMock


kubeconfig = """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1\
        JSURBVENDQWVtZ0F3SUJBZ0lKQUxjMk9xVUpwcnVCTUEwR0NTcUdTSWIzRFFFQk\
        N3VUFNQmN4RlRBVEJnTlYKQkFNTURERXdMakUxTWk0eE9ETXVNVEFlRncweU1EQ\
        TVNVEV4TkRJeU16VmFGdzB6TURBNU1Ea3hOREl5TXpWYQpNQmN4RlRBVEJnTlZC\
        QU1NRERFd0xqRTFNaTR4T0RNdU1UQ0NBU0l3RFFZSktvWklodmNOQVFFQkJRQUR\
        nZ0VQCkFEQ0NBUW9DZ2dFQkFNV0tyQkdxWlJRT0VONDExR2RESmY2ckZWRDcvMU\
        xHNlZMWjNhd1BRdHBhRTRxdVdyNisKWjExTWwra2kwVEU1cGZFV3dKenVUZXlCU\
        XVkUEpnYm1QTjF1VWROdGRiNlpocHEzeC9oT0hCMVJLNC9iSlNFUgpiZ0dITmN6\
        MzR6SHRaZ1dwb2NPTXpPOW9oRUdhMTZUaDhmQWVxYU1CQTJRaklmeUFlaVp3VHJ\
        nZ3BrY2dBMUlOCjBvQkdqSURnSGVoSU5tbGZOOURkQ3hNN1FNTmtSbzRXdE13bF\
        JSRWZ4QnFiVkNpZGFjbVhhb1VPUjJPeFVmQWEKN1orSUU1TmN5ZFQ1TGovazdwd\
        XZCVkdIa0JQWnE0TmlBa3R4aXd5NVB5R29GTk9mT0NrV2I2VnBzVzNhTlNJeAo4\
        aXBITkc3enV3elc1TGQ5TkhQYWpRckZwdFZBSHpJNWNhRUNBd0VBQWFOUU1FNHd\
        IUVlEVlIwT0JCWUVGQ1dVCkFaTXNaeE13L1k1OGlXMGZJWVAzcDdTYk1COEdBMV\
        VkSXdRWU1CYUFGQ1dVQVpNc1p4TXcvWTU4aVcwZklZUDMKcDdTYk1Bd0dBMVVkR\
        XdRRk1BTUJBZjh3RFFZSktvWklodmNOQVFFTEJRQURnZ0VCQUJaMlYxMWowRzhh\
        Z1Z6Twp2YWtKTGt4UGZ0UE1NMFFOaVRzZmV6RzlicnBkdEVLSjFyalFCblNXYTN\
        WbThWRGZTYkhLQUNXaGh0OEhzcXhtCmNzdVQyOWUyaGZBNHVIOUxMdy9MVG5EdE\
        tJSjZ6aWFzaTM5RGh3UGwwaExuamJRMjk4VVo5TGovVlpnZGlqemIKWnVPdHlpT\
        nVOS0E2Nmd0dGxXcWZRQ2hkbnJ5MlZUbjBjblR5dU9UalByYWdOdXJMdlVwL3Nl\
        eURhZmsxNXJ4egozcmlYZldiQnRhUUk1dnM0ekFKU2xneUg2RnpiZStoTUhlUzF\
        mM2ppb3dJV0lRR2NNbHpGT1RpMm1xWFRybEJYCnh1WmpLZlpOcndjQVNGbk9qYV\
        BWeFQ1ODJ4WWhtTm8wR3J2MlZEck51bDlSYkgvK3lNS2J5NEhkOFRvVThMU2kKY\
        3Uxajh3cz0KLS0tLS1FTkQgQ0VSVElGSUNBVEUtLS0tLQo=
    server: https://192.168.0.22:16443
  name: microk8s-cluster
contexts:
- context:
    cluster: microk8s-cluster
    user: admin
  name: microk8s
current-context: microk8s
kind: Config
preferences: {}
users:
- name: admin
  user:
    token: clhkRExRem5Xd1dCdnFEVXdvRGtDRGE5b1F3WnNrZk5qeHFCOU10bHBZRT0K
"""


async def AsyncMockFunc():
    await asyncio.sleep(1)


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class FakeN2VC(MagicMock):
    last_written_values = None

    async def write_app_status_to_db(
        self,
        db_dict: dict,
        status: N2VCDeploymentStatus,
        detailed_status: str,
        vca_status: str,
        entity_type: str,
        vca_id: str = None,
    ):
        """
        Write application status to database

        :param: db_dict: DB dictionary
        :param: status: Status of the application
        :param: detailed_status: Detailed status
        :param: vca_status: VCA status
        :param: entity_type: Entity type ("application", "machine, and "action")
        :param: vca_id: Id of the VCA. If None, the default VCA will be used.
        """
        self.last_written_values = Dict(
            {
                "n2vc_status": status,
                "message": detailed_status,
                "vca_status": vca_status,
                "entity": entity_type,
            }
        )

    osm_status = N2VCConnector.osm_status


class FakeMachine(MagicMock):
    entity_id = "2"
    dns_name = "FAKE ENDPOINT"
    model_name = "FAKE MODEL"
    entity_type = "machine"
    safe_data = {"instance-id": "myid"}

    async def destroy(self, force):
        pass


class FakeManualMachine(MagicMock):
    entity_id = "2"
    dns_name = "FAKE ENDPOINT"
    model_name = "FAKE MODEL"
    entity_type = "machine"
    safe_data = {"instance-id": "manual:myid"}
    series = "FAKE SERIES"

    async def destroy(self, force):
        pass


class FakeWatcher(AsyncMock):
    delta_to_return = None

    async def Next(self):
        return Dict({"deltas": self.delta_to_return})


class FakeConnection(MagicMock):
    endpoint = None
    is_open = False


class FakeAction(MagicMock):
    entity_id = "id"
    status = "ready"


class FakeModel:
    def __init__(self, applications: dict = {}):
        self._applications = applications

    @property
    def applications(self):
        return self._applications


class FakeUnit(MagicMock):
    async def is_leader_from_status(self):
        return True

    async def run_action(self, action_name, **kwargs):
        return FakeAction()

    @property
    def machine_id(self):
        return "existing_machine_id"

    name = "existing_unit"


class FakeApplication(AsyncMock):
    async def set_config(self, config):
        pass

    async def add_unit(self, to):
        pass

    async def destroy_unit(self, unit_name):
        pass

    async def get_actions(self):
        return ["existing_action"]

    async def get_config(self):
        return ["app_config"]

    async def scale(self, scale):
        pass

    units = [FakeUnit(), FakeUnit()]


class FakeFile:
    def __init__(self, content: str = ""):
        self.content = content

    def read(self, size: int = -1):
        return self.content


class FakeFileWrapper:
    def __init__(self, content: str = ""):
        self.file = FakeFile(content=content)

    def __enter__(self):
        return self.file

    def __exit__(self, type, value, traceback):
        pass


FAKE_DELTA_MACHINE_PENDING = Dict(
    {
        "deltas": ["machine", "change", {}],
        "entity": "machine",
        "type": "change",
        "data": {
            "id": "2",
            "instance-id": "juju-1b5808-2",
            "agent-status": {"current": "pending", "message": "", "version": ""},
            "instance-status": {"current": "running", "message": "Running"},
        },
    }
)
FAKE_DELTA_MACHINE_STARTED = Dict(
    {
        "deltas": ["machine", "change", {}],
        "entity": "machine",
        "type": "change",
        "data": {
            "id": "2",
            "instance-id": "juju-1b5808-2",
            "agent-status": {"current": "started", "message": "", "version": ""},
            "instance-status": {"current": "running", "message": "Running"},
        },
    }
)

FAKE_DELTA_UNIT_PENDING = Dict(
    {
        "deltas": ["unit", "change", {}],
        "entity": "unit",
        "type": "change",
        "data": {
            "name": "git/0",
            "application": "git",
            "machine-id": "6",
            "workload-status": {"current": "waiting", "message": ""},
            "agent-status": {"current": "idle", "message": ""},
        },
    }
)

FAKE_DELTA_UNIT_STARTED = Dict(
    {
        "deltas": ["unit", "change", {}],
        "entity": "unit",
        "type": "change",
        "data": {
            "name": "git/0",
            "application": "git",
            "machine-id": "6",
            "workload-status": {"current": "active", "message": ""},
            "agent-status": {"current": "idle", "message": ""},
        },
    }
)

FAKE_DELTA_APPLICATION_MAINTENANCE = Dict(
    {
        "deltas": ["application", "change", {}],
        "entity": "application",
        "type": "change",
        "data": {
            "name": "git",
            "status": {
                "current": "maintenance",
                "message": "installing charm software",
            },
        },
    }
)

FAKE_DELTA_APPLICATION_ACTIVE = Dict(
    {
        "deltas": ["application", "change", {}],
        "entity": "application",
        "type": "change",
        "data": {"name": "git", "status": {"current": "active", "message": "Ready!"}},
    }
)

FAKE_DELTA_ACTION_COMPLETED = Dict(
    {
        "deltas": ["action", "change", {}],
        "entity": "action",
        "type": "change",
        "data": {
            "model-uuid": "af19cdd4-374a-4d9f-86b1-bfed7b1b5808",
            "id": "1",
            "receiver": "git/0",
            "name": "add-repo",
            "status": "completed",
            "message": "",
        },
    }
)

Deltas = [
    Dict(
        {
            "entity": Dict({"id": "2", "type": "machine"}),
            "filter": Dict({"entity_id": "2", "entity_type": "machine"}),
            "delta": FAKE_DELTA_MACHINE_PENDING,
            "entity_status": Dict(
                {"status": "pending", "message": "Running", "vca_status": "running"}
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "Running",
                            "entity": "machine",
                            "vca_status": "running",
                            "n2vc_status": N2VCDeploymentStatus.PENDING,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "2", "type": "machine"}),
            "filter": Dict({"entity_id": "1", "entity_type": "machine"}),
            "delta": FAKE_DELTA_MACHINE_PENDING,
            "entity_status": Dict(
                {"status": "pending", "message": "Running", "vca_status": "running"}
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "2", "type": "machine"}),
            "filter": Dict({"entity_id": "2", "entity_type": "machine"}),
            "delta": FAKE_DELTA_MACHINE_STARTED,
            "entity_status": Dict(
                {"status": "started", "message": "Running", "vca_status": "running"}
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "Running",
                            "entity": "machine",
                            "vca_status": "running",
                            "n2vc_status": N2VCDeploymentStatus.COMPLETED,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "2", "type": "machine"}),
            "filter": Dict({"entity_id": "1", "entity_type": "machine"}),
            "delta": FAKE_DELTA_MACHINE_STARTED,
            "entity_status": Dict(
                {"status": "started", "message": "Running", "vca_status": "running"}
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git/0", "type": "unit"}),
            "filter": Dict({"entity_id": "git", "entity_type": "application"}),
            "delta": FAKE_DELTA_UNIT_PENDING,
            "entity_status": Dict(
                {"status": "waiting", "message": "", "vca_status": "waiting"}
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "",
                            "entity": "unit",
                            "vca_status": "waiting",
                            "n2vc_status": N2VCDeploymentStatus.RUNNING,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git/0", "type": "unit"}),
            "filter": Dict({"entity_id": "2", "entity_type": "machine"}),
            "delta": FAKE_DELTA_UNIT_PENDING,
            "entity_status": Dict(
                {"status": "waiting", "message": "", "vca_status": "waiting"}
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git/0", "type": "unit"}),
            "filter": Dict({"entity_id": "git", "entity_type": "application"}),
            "delta": FAKE_DELTA_UNIT_STARTED,
            "entity_status": Dict(
                {"status": "active", "message": "", "vca_status": "active"}
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "",
                            "entity": "unit",
                            "vca_status": "active",
                            "n2vc_status": N2VCDeploymentStatus.COMPLETED,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git/0", "type": "unit"}),
            "filter": Dict({"entity_id": "1", "entity_type": "action"}),
            "delta": FAKE_DELTA_UNIT_STARTED,
            "entity_status": Dict(
                {"status": "active", "message": "", "vca_status": "active"}
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git", "type": "application"}),
            "filter": Dict({"entity_id": "git", "entity_type": "application"}),
            "delta": FAKE_DELTA_APPLICATION_MAINTENANCE,
            "entity_status": Dict(
                {
                    "status": "maintenance",
                    "message": "installing charm software",
                    "vca_status": "maintenance",
                }
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "installing charm software",
                            "entity": "application",
                            "vca_status": "maintenance",
                            "n2vc_status": N2VCDeploymentStatus.RUNNING,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git", "type": "application"}),
            "filter": Dict({"entity_id": "2", "entity_type": "machine"}),
            "delta": FAKE_DELTA_APPLICATION_MAINTENANCE,
            "entity_status": Dict(
                {
                    "status": "maintenance",
                    "message": "installing charm software",
                    "vca_status": "maintenance",
                }
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git", "type": "application"}),
            "filter": Dict({"entity_id": "git", "entity_type": "application"}),
            "delta": FAKE_DELTA_APPLICATION_ACTIVE,
            "entity_status": Dict(
                {"status": "active", "message": "Ready!", "vca_status": "active"}
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "Ready!",
                            "entity": "application",
                            "vca_status": "active",
                            "n2vc_status": N2VCDeploymentStatus.COMPLETED,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git", "type": "application"}),
            "filter": Dict({"entity_id": "1", "entity_type": "action"}),
            "delta": FAKE_DELTA_APPLICATION_ACTIVE,
            "entity_status": Dict(
                {"status": "active", "message": "Ready!", "vca_status": "active"}
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "1", "type": "action"}),
            "filter": Dict({"entity_id": "1", "entity_type": "action"}),
            "delta": FAKE_DELTA_ACTION_COMPLETED,
            "entity_status": Dict(
                {
                    "status": "completed",
                    "message": "completed",
                    "vca_status": "completed",
                }
            ),
            "db": Dict(
                {
                    "written": True,
                    "data": Dict(
                        {
                            "message": "completed",
                            "entity": "action",
                            "vca_status": "completed",
                            "n2vc_status": N2VCDeploymentStatus.COMPLETED,
                        }
                    ),
                }
            ),
        }
    ),
    Dict(
        {
            "entity": Dict({"id": "git", "type": "action"}),
            "filter": Dict({"entity_id": "1", "entity_type": "machine"}),
            "delta": FAKE_DELTA_ACTION_COMPLETED,
            "entity_status": Dict(
                {
                    "status": "completed",
                    "message": "completed",
                    "vca_status": "completed",
                }
            ),
            "db": Dict({"written": False, "data": None}),
        }
    ),
]
