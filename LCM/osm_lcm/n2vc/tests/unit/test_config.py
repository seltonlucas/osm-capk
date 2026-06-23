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

from unittest import TestCase
from unittest.mock import patch


from osm_lcm.n2vc.config import EnvironConfig, ModelConfig, MODEL_CONFIG_KEYS


def generate_os_environ_dict(config, prefix):
    return {f"{prefix}{k.upper()}": v for k, v in config.items()}


class TestEnvironConfig(TestCase):
    def setUp(self):
        self.config = {"host": "1.2.3.4", "port": "17070", "k8s_cloud": "k8s"}

    @patch("os.environ.items")
    def test_environ_config_lcm(self, mock_environ_items):
        envs = generate_os_environ_dict(self.config, "OSMLCM_VCA_")
        envs["not_valid_env"] = "something"
        mock_environ_items.return_value = envs.items()
        config = EnvironConfig()
        self.assertEqual(config, self.config)

    @patch("os.environ.items")
    def test_environ_config_mon(self, mock_environ_items):
        envs = generate_os_environ_dict(self.config, "OSMMON_VCA_")
        envs["not_valid_env"] = "something"
        mock_environ_items.return_value = envs.items()
        config = EnvironConfig()
        self.assertEqual(config, self.config)


class TestModelConfig(TestCase):
    def setUp(self):
        self.config = {
            f'model_config_{model_key.replace("-", "_")}': "somevalue"
            for model_key in MODEL_CONFIG_KEYS
        }
        self.config["model_config_invalid"] = "something"
        self.model_config = {model_key: "somevalue" for model_key in MODEL_CONFIG_KEYS}

    def test_model_config(self):
        model_config = ModelConfig(self.config)
        self.assertEqual(model_config, self.model_config)
