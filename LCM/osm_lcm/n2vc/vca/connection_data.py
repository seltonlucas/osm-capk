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

from osm_lcm.n2vc.utils import base64_to_cacert


class ConnectionData:
    def __init__(self, **kwargs):
        """
        Constructor

        :param: kwargs:
            endpoints (list): Endpoints of all the Juju controller units
            user (str): Username for authenticating to the controller
            secret (str): Secret for authenticating to the controller
            cacert (str): Base64 encoded CA certificate for authenticating to the controller
            (optional) pubkey (str): Public key to insert to the charm.
                            This is useful to do `juju ssh`.
                            It is not very useful though.
                            TODO: Test it.
            (optional) lxd-cloud (str): Name of the cloud to use for lxd proxy charms
            (optional) lxd-credentials (str): Name of the lxd-cloud credentials
            (optional) k8s-cloud (str): Name of the cloud to use for k8s proxy charms
            (optional) k8s-credentials (str): Name of the k8s-cloud credentials
            (optional) model-config (n2vc.config.ModelConfig): Config to apply in all Juju models
            (deprecated, optional) api-proxy (str): Proxy IP to reach the controller.
                                                    Used in case native charms cannot react the controller.
        """
        self.endpoints = kwargs["endpoints"]
        self.user = kwargs["user"]
        self.secret = kwargs["secret"]
        self.cacert = base64_to_cacert(kwargs["cacert"])
        self.pubkey = kwargs.get("pubkey", "")
        self.lxd_cloud = kwargs.get("lxd-cloud", None)
        self.lxd_credentials = kwargs.get("lxd-credentials", None)
        self.k8s_cloud = kwargs.get("k8s-cloud", None)
        self.k8s_credentials = kwargs.get("k8s-credentials", None)
        self.model_config = kwargs.get("model-config", {})
        self.model_config.update({"authorized-keys": self.pubkey})
        self.api_proxy = kwargs.get("api-proxy", None)
