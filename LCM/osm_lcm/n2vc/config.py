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

import os
import typing


class EnvironConfig(dict):
    prefixes = ["OSMLCM_VCA_", "OSMMON_VCA_"]

    def __init__(self, prefixes: typing.List[str] = None):
        if prefixes:
            self.prefixes = prefixes
        for key, value in os.environ.items():
            if any(key.startswith(prefix) for prefix in self.prefixes):
                self.__setitem__(self._get_renamed_key(key), value)

    def _get_renamed_key(self, key: str) -> str:
        for prefix in self.prefixes:
            key = key.replace(prefix, "")
        return key.lower()


MODEL_CONFIG_KEYS = [
    "agent-metadata-url",
    "agent-stream",
    "apt-ftp-proxy",
    "apt-http-proxy",
    "apt-https-proxy",
    "apt-mirror",
    "apt-no-proxy",
    "automatically-retry-hooks",
    "backup-dir",
    "cloudinit-userdata",
    "container-image-metadata-url",
    "container-image-stream",
    "container-inherit-properties",
    "container-networking-method",
    "default-series",
    "default-space",
    "development",
    "disable-network-management",
    "egress-subnets",
    "enable-os-refresh-update",
    "enable-os-upgrade",
    "fan-config",
    "firewall-mode",
    "ftp-proxy",
    "http-proxy",
    "https-proxy",
    "ignore-machine-addresses",
    "image-metadata-url",
    "image-stream",
    "juju-ftp-proxy",
    "juju-http-proxy",
    "juju-https-proxy",
    "juju-no-proxy",
    "logforward-enabled",
    "logging-config",
    "lxd-snap-channel",
    "max-action-results-age",
    "max-action-results-size",
    "max-status-history-age",
    "max-status-history-size",
    "net-bond-reconfigure-delay",
    "no-proxy",
    "provisioner-harvest-mode",
    "proxy-ssh",
    "snap-http-proxy",
    "snap-https-proxy",
    "snap-store-assertions",
    "snap-store-proxy",
    "snap-store-proxy-url",
    "ssl-hostname-verification",
    "test-mode",
    "transmit-vendor-metrics",
    "update-status-hook-interval",
]


class ModelConfig(dict):
    prefix = "model_config_"

    def __init__(self, config: dict):
        for key, value in config.items():
            if (
                key.startswith(self.prefix)
                and self._get_renamed_key(key) in MODEL_CONFIG_KEYS
            ):
                self.__setitem__(self._get_renamed_key(key), value)

    def _get_renamed_key(self, key):
        return key.replace(self.prefix, "").replace("_", "-")
