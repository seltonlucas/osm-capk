# Copyright 2022 Canonical Ltd.
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
# contact: alfonso.tiernosepulveda@telefonica.com
##
import logging
import tempfile
from unittest.mock import Mock, patch, MagicMock, mock_open
from unittest import TestCase

from osm_common.msgkafka import MsgKafka
from osm_common import fslocal
from osm_lcm.data_utils.database.database import Database
from osm_lcm.data_utils.filesystem.filesystem import Filesystem
from osm_lcm.lcm_utils import LcmBase, LcmException, vld_to_ro_ip_profile
from osm_lcm.tests import test_db_descriptors as descriptors
import yaml
from zipfile import BadZipfile


tmpdir = tempfile.mkdtemp()[1]
tmpfile = tempfile.mkstemp()[1]


class TestLcmBase(TestCase):
    test_nsr_id = "f48163a6-c807-47bc-9682-f72caef5af85"
    test_nsd_id = "8c2f8b95-bb1b-47ee-8001-36dc090678da"
    nsd_package_path = "/" + test_nsd_id
    nsd_package_name = "test_nsd"
    charm_metadata_file = "/path/charm/metadata.yaml"

    def setUp(self):
        # DB
        Database.instance = None
        self.db = Database({"database": {"driver": "memory"}}).instance.db
        self.db.create_list("nsds", yaml.safe_load(descriptors.db_nsds_text))
        self.db.create_list("nsds_revisions", yaml.safe_load(descriptors.db_nsds_text))
        self.db.create_list("nsrs", yaml.safe_load(descriptors.db_nsrs_text))
        # Filesystem
        self.fs = Filesystem({"storage": {"driver": "local", "path": "/"}}).instance.fs
        # Create LCMBase class
        self.msg = Mock(MsgKafka())
        self.logger = Mock(logging)
        self.my_ns = LcmBase(self.msg, self.logger)
        self.my_ns.fs = self.fs
        self.my_ns.db = self.db
        self.hexdigest = "031edd7d41651593c5fe5c006f"

    def test_get_charm_name_successfully(self):
        instance = self.my_ns
        mock_open = MagicMock(open)
        mock_yaml = MagicMock(yaml)
        mock_yaml.safe_load.return_value = {"name": "test_charm"}
        expected_result = "test_charm"

        with patch("osm_lcm.lcm_utils.open", mock_open), patch(
            "osm_lcm.lcm_utils.yaml.safe_load", mock_yaml.safe_load
        ):
            result = instance.get_charm_name(TestLcmBase.charm_metadata_file)
            self.assertEqual(result, expected_result, "wrong charm name")
            self.assertEqual(mock_yaml.safe_load.call_count, 1)
            self.assertEqual(mock_open.call_count, 1)

    def test_get_charm_name_can_not_open_metadata_file(self):
        instance = self.my_ns
        mock_open = MagicMock(open)
        mock_open.side_effect = IOError
        mock_yaml = MagicMock(create_autospec=True)

        with patch("osm_lcm.lcm_utils.open", mock_open), patch(
            "osm_lcm.lcm_utils.yaml.safe_load", mock_yaml.safe_load
        ):
            with self.assertRaises(IOError):
                instance.get_charm_name(TestLcmBase.charm_metadata_file)
                mock_yaml.safe_load.assert_not_called()
                self.assertEqual(mock_open.call_count, 1)

    def test_get_charm_name_wrong_metadata_file_format(self):
        instance = self.my_ns
        mock_open = MagicMock(open)
        mock_yaml = MagicMock(create_autospec=True)
        mock_yaml.safe_load.return_value = {}

        with patch("osm_lcm.lcm_utils.open", mock_open), patch(
            "osm_lcm.lcm_utils.yaml.safe_load", mock_yaml.safe_load
        ):
            with self.assertRaises(KeyError):
                instance.get_charm_name(TestLcmBase.charm_metadata_file)
                self.assertEqual(mock_open.call_count, 1)
                self.assertEqual(mock_yaml.safe_load.call_count, 1)

    def test_get_charm_path_successfully(self):
        instance = self.my_ns
        fs = fslocal.FsLocal()
        fs.path = "/app/storage"
        instance.fs = fs
        charm_folder_name = "simple_charm"
        expected_result = (
            "/app/storage/" + TestLcmBase.test_nsd_id + "/test_nsd/charms/simple_charm"
        )
        result = instance._get_charm_path(
            TestLcmBase.nsd_package_path,
            TestLcmBase.nsd_package_name,
            charm_folder_name,
        )
        self.assertEqual(result, expected_result, "wrong_charm_path")

    def test_get_charm_metadata_file_charm_is_not_zipped(self):
        instance = self.my_ns
        fs = fslocal.FsLocal()
        fs.path = "/app/storage"
        instance.fs = fs
        mock_zipfile = MagicMock(create_autospec=True)
        charm_folder_name = "simple_charm"
        charm_path = (
            "/app/storage/" + TestLcmBase.test_nsd_id + "/test_nsd/charms/simple_charm"
        )
        expected_result = (
            "/app/storage/"
            + TestLcmBase.test_nsd_id
            + "/test_nsd/charms/simple_charm/metadata.yaml"
        )

        with patch("osm_lcm.lcm_utils.ZipFile", mock_zipfile):
            result = instance._get_charm_metadata_file(
                charm_folder_name,
                TestLcmBase.nsd_package_path,
                TestLcmBase.nsd_package_name,
                charm_path=charm_path,
            )
            self.assertEqual(result, expected_result, "wrong charm metadata path")
            mock_zipfile.assert_not_called()

    def test_get_charm_metadata_file_charm_is_zipped(self):
        instance = self.my_ns
        fs = fslocal.FsLocal()
        fs.path = "/app/storage"
        instance.fs = fs
        mock_zipfile = MagicMock(create_autospec=True)
        mock_zipfile.side_effect = None
        charm_folder_name = "ubuntu_18.04_simple_charm2.charm"
        charm_path = (
            "/app/storage/" + TestLcmBase.test_nsd_id + "/test_nsd/charms/simple_charm"
        )
        expected_result = (
            "/app/storage/"
            + TestLcmBase.test_nsd_id
            + "/test_nsd/charms/ubuntu_18.04_simple_charm2/metadata.yaml"
        )

        with patch("osm_lcm.lcm_utils.ZipFile", mock_zipfile):
            result = instance._get_charm_metadata_file(
                charm_folder_name,
                TestLcmBase.nsd_package_path,
                TestLcmBase.nsd_package_name,
                charm_path=charm_path,
            )
            self.assertEqual(result, expected_result, "wrong charm metadata path")
            self.assertEqual(mock_zipfile.call_count, 1)

    def test_find_charm_name_successfully(self):
        db_nsr = self.db.get_one("nsrs", {"_id": TestLcmBase.test_nsr_id})
        instance = self.my_ns
        mock_charm_path = MagicMock()
        mock_metadata_file = MagicMock()
        mock_metadata_file.return_value = (
            "/" + TestLcmBase.test_nsd_id + "/new_test_nsd/charms/simple/metadata.yaml"
        )
        mock_charm_name = MagicMock()
        mock_charm_name.return_value = "test_charm"
        expected_result = "test_charm"

        with patch("osm_lcm.lcm_utils.LcmBase._get_charm_path", mock_charm_path), patch(
            "osm_lcm.lcm_utils.LcmBase._get_charm_metadata_file", mock_metadata_file
        ), patch("osm_lcm.lcm_utils.LcmBase.get_charm_name", mock_charm_name):
            result = instance.find_charm_name(db_nsr, "simple")
            self.assertEqual(result, expected_result, "Wrong charm name")
            mock_charm_path.assert_called_once()
            mock_metadata_file.assert_called_once()
            mock_charm_name.assert_called_once_with(
                "/"
                + TestLcmBase.test_nsd_id
                + "/new_test_nsd/charms/simple/metadata.yaml"
            )

    def test_find_charm_name_charm_bad_zipfile(self):
        db_nsr = self.db.get_one("nsrs", {"_id": TestLcmBase.test_nsr_id})
        instance = self.my_ns
        mock_charm_path = MagicMock()
        mock_metadata_file = MagicMock()
        mock_metadata_file.side_effect = BadZipfile
        mock_charm_name = MagicMock()

        with patch("osm_lcm.lcm_utils.LcmBase._get_charm_path", mock_charm_path), patch(
            "osm_lcm.lcm_utils.LcmBase._get_charm_metadata_file", mock_metadata_file
        ), patch("osm_lcm.lcm_utils.LcmBase.get_charm_name", mock_charm_name):
            with self.assertRaises(LcmException):
                instance.find_charm_name(db_nsr, "simple")
                self.assertEqual(mock_charm_path.call_count, 1)
                self.assertEqual(mock_metadata_file.call_count, 1)
                mock_charm_name.assert_not_called()

    def test_find_charm_name_missing_input_charm_folder_name(self):
        db_nsr = self.db.get_one("nsrs", {"_id": TestLcmBase.test_nsr_id})
        instance = self.my_ns
        mock_metadata_file = MagicMock()
        mock_charm_name = MagicMock()
        mock_charm_path = MagicMock()

        with patch("osm_lcm.lcm_utils.LcmBase._get_charm_path", mock_charm_path), patch(
            "osm_lcm.lcm_utils.LcmBase._get_charm_metadata_file", mock_metadata_file
        ), patch("osm_lcm.lcm_utils.LcmBase.get_charm_name", mock_charm_name):
            with self.assertRaises(LcmException):
                instance.find_charm_name(db_nsr, "")
                mock_charm_path.assert_not_called()
                mock_metadata_file.assert_not_called()
                mock_charm_name.assert_not_called()

    def test_find_charm_name_can_not_open_metadata_file(self):
        db_nsr = self.db.get_one("nsrs", {"_id": TestLcmBase.test_nsr_id})
        instance = self.my_ns

        mock_charm_path = MagicMock()
        mock_metadata_file = MagicMock()
        mock_charm_name = MagicMock()
        mock_charm_name.side_effect = yaml.YAMLError

        with patch("osm_lcm.lcm_utils.LcmBase._get_charm_path", mock_charm_path), patch(
            "osm_lcm.lcm_utils.LcmBase._get_charm_metadata_file", mock_metadata_file
        ), patch("osm_lcm.lcm_utils.LcmBase.get_charm_name", mock_charm_name):
            with self.assertRaises(LcmException):
                instance.find_charm_name(db_nsr, "simple")
                self.assertEqual(mock_charm_path.call_count, 1)
                self.assertEqual(mock_metadata_file.call_count, 1)
                self.assertEqual(mock_charm_name.call_count, 1)

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_hash_sucessfully(self, mock_hashlib, mocking_open):
        """Calculate charm hash successfully."""
        charm = tmpfile
        hexdigest = self.hexdigest
        mock_file_hash = MagicMock()
        mock_hashlib.sha256.return_value = mock_file_hash
        mock_file_hash.hexdigest.return_value = hexdigest
        result = LcmBase.calculate_charm_hash(charm)
        self.assertEqual(result, hexdigest)
        self.assertEqual(mocking_open.call_count, 1)
        self.assertEqual(mock_file_hash.update.call_count, 1)
        self.assertEqual(mock_file_hash.hexdigest.call_count, 1)
        self.assertEqual(mock_hashlib.sha256.call_count, 1)

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_hash_open_raises(self, mock_hashlib, mocking_open):
        """builtins.open raises exception."""
        charm = tmpfile
        hexdigest = self.hexdigest
        mock_file_hash = MagicMock()
        mock_hashlib.sha256.return_value = mock_file_hash
        mock_file_hash.hexdigest.return_value = hexdigest
        mocking_open.side_effect = IOError
        with self.assertRaises(IOError):
            LcmBase.calculate_charm_hash(charm)
        self.assertEqual(mocking_open.call_count, 1)
        mock_file_hash.update.assert_not_called()
        mock_file_hash.hexdigest.assert_not_called()
        self.assertEqual(mock_hashlib.sha256.call_count, 1)

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_filehash_update_raises(self, mock_hashlib, mocking_open):
        """Filehash update raises exception."""
        charm = tmpfile
        hexdigest = self.hexdigest
        mock_file_hash = MagicMock()
        mock_file_hash.update.side_effect = Exception
        mock_hashlib.sha256.return_value = mock_file_hash
        mock_file_hash.hexdigest.return_value = hexdigest
        with self.assertRaises(Exception):
            LcmBase.calculate_charm_hash(charm)
        self.assertEqual(mocking_open.call_count, 1)
        self.assertEqual(mock_file_hash.update.call_count, 1)
        mock_file_hash.hexdigest.assert_not_called()
        self.assertEqual(mock_hashlib.sha256.call_count, 1)

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_filehash_hexdigest_raises(
        self, mock_hashlib, mocking_open
    ):
        """Filehash hexdigest raises exception."""
        charm = tmpfile
        mock_file_hash = MagicMock()
        mock_hashlib.sha256.return_value = mock_file_hash
        mock_file_hash.hexdigest.side_effect = Exception
        with self.assertRaises(Exception):
            LcmBase.calculate_charm_hash(charm)
        self.assertEqual(mocking_open.call_count, 1)
        self.assertEqual(mock_file_hash.update.call_count, 1)
        mock_file_hash.hexdigest.assert_called_once()
        self.assertEqual(mock_hashlib.sha256.call_count, 1)
        mock_file_hash.update.assert_called_once()

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_filehash_hashlib_sha256_raises(
        self, mock_hashlib, mocking_open
    ):
        """Filehash hashlib sha256 raises exception."""
        charm = tmpfile
        mock_hashlib.sha256.side_effect = Exception
        with self.assertRaises(Exception):
            LcmBase.calculate_charm_hash(charm)
        self.assertEqual(mock_hashlib.sha256.call_count, 1)
        mocking_open.assert_not_called()

    @patch("builtins.open", new_callable=mock_open(read_data="charm content"))
    @patch("osm_lcm.lcm_utils.hashlib")
    def test_calculate_charm_hash_file_does_not_exist(self, mock_hashlib, mocking_open):
        """Calculate charm hash, charm file does not exist."""
        file = None
        mock_file_hash = MagicMock()
        mock_hashlib.sha256.return_value = mock_file_hash
        mocking_open.side_effect = FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            LcmBase.calculate_charm_hash(file)
        self.assertEqual(mocking_open.call_count, 1)
        mock_file_hash.update.assert_not_called()
        mock_file_hash.hexdigest.assert_not_called()
        self.assertEqual(mock_hashlib.sha256.call_count, 1)

    @patch("osm_lcm.lcm_utils.LcmBase.calculate_charm_hash")
    def test_compare_charm_hash_charm_changed(self, mock_calculate_charm_hash):
        """Compare charm hash, charm files are different."""
        output = True
        charm1, charm2 = tmpfile, tmpfile
        mock_calculate_charm_hash.side_effect = [
            self.hexdigest,
            "0dd7d4173747593c5fe5c006f",
        ]
        result = LcmBase.compare_charm_hash(charm1, charm2)
        self.assertEqual(output, result)
        self.assertEqual(mock_calculate_charm_hash.call_count, 2)

    @patch("osm_lcm.lcm_utils.LcmBase.calculate_charm_hash")
    def test_compare_charm_hash_charm_is_same(self, mock_calculate_charm_hash):
        """Compare charm hash, charm files are same."""
        output = False
        charm1 = charm2 = tmpfile
        mock_calculate_charm_hash.side_effect = [
            self.hexdigest,
            self.hexdigest,
        ]
        result = LcmBase.compare_charm_hash(charm1, charm2)
        self.assertEqual(output, result)
        self.assertEqual(mock_calculate_charm_hash.call_count, 2)

    @patch("osm_lcm.lcm_utils.LcmBase.calculate_charm_hash")
    def test_compare_charm_hash_one_charm_is_not_valid(self, mock_calculate_charm_hash):
        """Compare charm hash, one charm file is not valid."""
        charm1, charm2 = tmpdir, None
        mock_calculate_charm_hash.side_effect = [
            self.hexdigest,
            FileNotFoundError,
        ]

        with self.assertRaises(FileNotFoundError):
            LcmBase.compare_charm_hash(charm1, charm2)
        self.assertEqual(mock_calculate_charm_hash.call_count, 2)

    @patch("osm_lcm.lcm_utils.LcmBase.calculate_charm_hash")
    def test_compare_charm_hash_both_charms_are_not_valid(
        self, mock_calculate_charm_hash
    ):
        """Compare charm hash, both charm files are not valid."""
        charm1, charm2 = None, None
        mock_calculate_charm_hash.side_effect = [IOError, IOError]
        with self.assertRaises(IOError):
            LcmBase.compare_charm_hash(charm1, charm2)
        self.assertEqual(mock_calculate_charm_hash.call_count, 1)

    @patch("osm_lcm.lcm_utils.checksumdir")
    def test_compare_charmdir_charm_changed(self, mock_checksum):
        """Compare charm directory hash, charms are changed."""
        expected_output = True
        charm_dir1, charm_dir2 = tmpdir, tmpdir
        mock_checksum.dirhash.side_effect = [
            self.hexdigest,
            "031eddtrtr651593c5fe5c006f",
        ]
        result = LcmBase.compare_charmdir_hash(charm_dir1, charm_dir2)
        self.assertEqual(expected_output, result)
        self.assertEqual(mock_checksum.dirhash.call_count, 2)

    @patch("osm_lcm.lcm_utils.checksumdir")
    def test_compare_charmdir_charm_is_same(self, mock_checksum):
        """Compare charm directory hash, charms are same."""
        expected_output = False
        charm_dir1 = charm_dir2 = tmpdir
        mock_checksum.dirhash.side_effect = [
            self.hexdigest,
            self.hexdigest,
        ]
        result = LcmBase.compare_charmdir_hash(charm_dir1, charm_dir2)
        self.assertEqual(expected_output, result)
        self.assertEqual(mock_checksum.dirhash.call_count, 2)

    @patch("osm_lcm.lcm_utils.checksumdir")
    def test_compare_charmdir_one_charmdir_is_not_valid(self, mock_checksum):
        """Compare charm directory hash, one charm directory is not valid."""
        charm_dir1, charm_dir2 = tmpdir, None
        mock_checksum.dirhash.side_effect = [
            self.hexdigest,
            FileNotFoundError,
        ]
        with self.assertRaises(FileNotFoundError):
            LcmBase.compare_charmdir_hash(charm_dir1, charm_dir2)
        self.assertEqual(mock_checksum.dirhash.call_count, 2)

    @patch("osm_lcm.lcm_utils.checksumdir")
    def test_compare_charmdir_both_charmdirs_are_not_valid(self, mock_checksum):
        """Compare charm directory hash, both charm directories are not valid."""
        charm_dir1, charm_dir2 = None, None
        mock_checksum.dirhash.side_effect = [FileNotFoundError, FileNotFoundError]
        with self.assertRaises(FileNotFoundError):
            LcmBase.compare_charmdir_hash(charm_dir1, charm_dir2)
        self.assertEqual(mock_checksum.dirhash.call_count, 1)


class TestLcmUtils(TestCase):
    def setUp(self):
        pass

    def test__vld_to_ro_ip_profile_with_none(self):
        vld_data = None

        result = vld_to_ro_ip_profile(
            source_data=vld_data,
        )

        self.assertIsNone(result)

    def test__vld_to_ro_ip_profile_with_empty_profile(self):
        vld_data = {}

        result = vld_to_ro_ip_profile(
            source_data=vld_data,
        )

        self.assertIsNone(result)

    def test__vld_to_ro_ip_profile_with_wrong_profile(self):
        vld_data = {
            "no-profile": "here",
        }
        expected_result = {
            "ip_version": "IPv4",
            "subnet_address": None,
            "gateway_address": None,
            "dns_address": None,
            "dhcp_enabled": False,
            "dhcp_start_address": None,
            "dhcp_count": None,
            "ipv6_address_mode": None,
        }

        result = vld_to_ro_ip_profile(
            source_data=vld_data,
        )

        self.assertDictEqual(expected_result, result)

    def test__vld_to_ro_ip_profile_with_ipv4_profile(self):
        vld_data = {
            "ip-version": "ipv4",
            "cidr": "192.168.0.0/24",
            "gateway-ip": "192.168.0.254",
            "dhcp-enabled": True,
            "dns-server": [{"address": "8.8.8.8"}],
        }
        expected_result = {
            "ip_version": "IPv4",
            "subnet_address": "192.168.0.0/24",
            "gateway_address": "192.168.0.254",
            "dns_address": "8.8.8.8",
            "dhcp_enabled": True,
            "dhcp_start_address": None,
            "dhcp_count": None,
            "ipv6_address_mode": None,
        }

        result = vld_to_ro_ip_profile(
            source_data=vld_data,
        )

        self.assertDictEqual(expected_result, result)

    def test__vld_to_ro_ip_profile_with_ipv6_profile(self):
        vld_data = {
            "ip-version": "ipv6",
            "cidr": "2001:0200:0001::/48",
            "gateway-ip": "2001:0200:0001:ffff:ffff:ffff:ffff:fffe",
            "dhcp-enabled": True,
        }
        expected_result = {
            "ip_version": "IPv6",
            "subnet_address": "2001:0200:0001::/48",
            "gateway_address": "2001:0200:0001:ffff:ffff:ffff:ffff:fffe",
            "dns_address": None,
            "dhcp_enabled": True,
            "dhcp_start_address": None,
            "dhcp_count": None,
            "ipv6_address_mode": None,
        }

        result = vld_to_ro_ip_profile(
            source_data=vld_data,
        )

        self.assertDictEqual(expected_result, result)
