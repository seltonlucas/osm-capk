# -*- coding: utf-8 -*-

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

import tarfile
import yaml
import json
import copy
import os
import shutil
import functools
import re
import base64

# import logging
from deepdiff import DeepDiff
from hashlib import md5, sha384
from osm_common.dbbase import DbException, deep_update_rfc7396
from http import HTTPStatus
from time import time
from uuid import uuid4
from re import fullmatch
from zipfile import ZipFile
from urllib.parse import urlparse
from osm_nbi.validation import (
    ValidationError,
    pdu_new_schema,
    pdu_edit_schema,
    validate_input,
    vnfpkgop_new_schema,
    ns_config_template,
    vnf_schema,
    vld_schema,
    additional_params_for_vnf,
)
from osm_nbi.base_topic import (
    BaseTopic,
    EngineException,
    get_iterable,
    detect_descriptor_usage,
)
from osm_im import etsi_nfv_vnfd, etsi_nfv_nsd
from osm_im.validation import Validation as validation_im
from osm_im.nst import nst as nst_im
from pyangbind.lib.serialise import pybindJSONDecoder
import pyangbind.lib.pybindJSON as pybindJSON
from osm_nbi import utils

__author__ = "Alfonso Tierno <alfonso.tiernosepulveda@telefonica.com>"

valid_helm_chart_re = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9]/)?([a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)


class DescriptorTopic(BaseTopic):
    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def _validate_input_new(self, indata, storage_params, force=False):
        return indata

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        final_content = super().check_conflict_on_edit(
            session, final_content, edit_content, _id
        )

        def _check_unique_id_name(descriptor, position=""):
            for desc_key, desc_item in descriptor.items():
                if isinstance(desc_item, list) and desc_item:
                    used_ids = []
                    desc_item_id = None
                    for index, list_item in enumerate(desc_item):
                        if isinstance(list_item, dict):
                            _check_unique_id_name(
                                list_item, "{}.{}[{}]".format(position, desc_key, index)
                            )
                            # Base case
                            if index == 0 and (
                                list_item.get("id") or list_item.get("name")
                            ):
                                desc_item_id = "id" if list_item.get("id") else "name"
                            if desc_item_id and list_item.get(desc_item_id):
                                if list_item[desc_item_id] in used_ids:
                                    position = "{}.{}[{}]".format(
                                        position, desc_key, index
                                    )
                                    raise EngineException(
                                        "Error: identifier {} '{}' is not unique and repeats at '{}'".format(
                                            desc_item_id,
                                            list_item[desc_item_id],
                                            position,
                                        ),
                                        HTTPStatus.UNPROCESSABLE_ENTITY,
                                    )
                                used_ids.append(list_item[desc_item_id])

        _check_unique_id_name(final_content)
        # 1. validate again with pyangbind
        # 1.1. remove internal keys
        internal_keys = {}
        for k in ("_id", "_admin"):
            if k in final_content:
                internal_keys[k] = final_content.pop(k)
        storage_params = internal_keys["_admin"].get("storage")
        serialized = self._validate_input_new(
            final_content, storage_params, session["force"]
        )

        # 1.2. modify final_content with a serialized version
        final_content = copy.deepcopy(serialized)
        # 1.3. restore internal keys
        for k, v in internal_keys.items():
            final_content[k] = v
        if session["force"]:
            return final_content

        # 2. check that this id is not present
        if "id" in edit_content:
            _filter = self._get_project_filter(session)

            _filter["id"] = final_content["id"]
            _filter["_id.neq"] = _id

            if self.db.get_one(self.topic, _filter, fail_on_empty=False):
                raise EngineException(
                    "{} with id '{}' already exists for this project".format(
                        (str(self.topic))[:-1], final_content["id"]
                    ),
                    HTTPStatus.CONFLICT,
                )

        return final_content

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["_admin"]["onboardingState"] = "CREATED"
        content["_admin"]["operationalState"] = "DISABLED"
        content["_admin"]["usageState"] = "NOT_IN_USE"

    def delete_extra(self, session, _id, db_content, not_send_msg=None):
        """
        Deletes file system storage associated with the descriptor
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param db_content: The database content of the descriptor
        :param not_send_msg: To not send message (False) or store content (list) instead
        :return: None if ok or raises EngineException with the problem
        """
        self.fs.file_delete(_id, ignore_non_exist=True)
        self.fs.file_delete(_id + "_", ignore_non_exist=True)  # remove temp folder
        # Remove file revisions
        if "revision" in db_content["_admin"]:
            revision = db_content["_admin"]["revision"]
            while revision > 0:
                self.fs.file_delete(_id + ":" + str(revision), ignore_non_exist=True)
                revision = revision - 1

    @staticmethod
    def get_one_by_id(db, session, topic, id):
        # find owned by this project
        _filter = BaseTopic._get_project_filter(session)
        _filter["id"] = id
        desc_list = db.get_list(topic, _filter)
        if len(desc_list) == 1:
            return desc_list[0]
        elif len(desc_list) > 1:
            raise DbException(
                "Found more than one {} with id='{}' belonging to this project".format(
                    topic[:-1], id
                ),
                HTTPStatus.CONFLICT,
            )

        # not found any: try to find public
        _filter = BaseTopic._get_project_filter(session)
        _filter["id"] = id
        desc_list = db.get_list(topic, _filter)
        if not desc_list:
            raise DbException(
                "Not found any {} with id='{}'".format(topic[:-1], id),
                HTTPStatus.NOT_FOUND,
            )
        elif len(desc_list) == 1:
            return desc_list[0]
        else:
            raise DbException(
                "Found more than one public {} with id='{}'; and no one belonging to this project".format(
                    topic[:-1], id
                ),
                HTTPStatus.CONFLICT,
            )

    def new(self, rollback, session, indata=None, kwargs=None, headers=None):
        """
        Creates a new almost empty DISABLED  entry into database. Due to SOL005, it does not follow normal procedure.
        Creating a VNFD or NSD is done in two steps: 1. Creates an empty descriptor (this step) and 2) upload content
        (self.upload_content)
        :param rollback: list to append created items at database in case a rollback may to be done
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param indata: data to be inserted
        :param kwargs: used to override the indata descriptor
        :param headers: http request headers
        :return: _id, None: identity of the inserted data; and None as there is not any operation
        """

        # No needed to capture exceptions
        # Check Quota
        self.check_quota(session)

        # _remove_envelop
        if indata:
            if "userDefinedData" in indata:
                indata = indata["userDefinedData"]

        # Override descriptor with query string kwargs
        self._update_input_with_kwargs(indata, kwargs)
        # uncomment when this method is implemented.
        # Avoid override in this case as the target is userDefinedData, but not vnfd,nsd descriptors
        # indata = DescriptorTopic._validate_input_new(self, indata, project_id=session["force"])

        content = {"_admin": {"userDefinedData": indata, "revision": 0}}

        self.format_on_new(
            content, session["project_id"], make_public=session["public"]
        )
        _id = self.db.create(self.topic, content)
        rollback.append({"topic": self.topic, "_id": _id})
        self._send_msg("created", {"_id": _id})
        return _id, None

    def upload_content(self, session, _id, indata, kwargs, headers):
        """
        Used for receiving content by chunks (with a transaction_id header and/or gzip file. It will store and extract)
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id : the nsd,vnfd is already created, this is the id
        :param indata: http body request
        :param kwargs: user query string to override parameters. NOT USED
        :param headers:  http request headers
        :return: True if package is completely uploaded or False if partial content has been uploded
            Raise exception on error
        """
        # Check that _id exists and it is valid
        current_desc = self.show(session, _id)

        content_range_text = headers.get("Content-Range")
        expected_md5 = headers.get("Content-File-MD5")
        digest_header = headers.get("Digest")
        compressed = None
        content_type = headers.get("Content-Type")
        if (
            content_type
            and "application/gzip" in content_type
            or "application/x-gzip" in content_type
        ):
            compressed = "gzip"
        if content_type and "application/zip" in content_type:
            compressed = "zip"
        filename = headers.get("Content-Filename")
        if not filename and compressed:
            filename = "package.tar.gz" if compressed == "gzip" else "package.zip"
        elif not filename:
            filename = "package"

        revision = 1
        if "revision" in current_desc["_admin"]:
            revision = current_desc["_admin"]["revision"] + 1

        # TODO change to Content-Disposition filename https://tools.ietf.org/html/rfc6266
        file_pkg = None
        error_text = ""
        fs_rollback = []

        try:
            if content_range_text:
                content_range = (
                    content_range_text.replace("-", " ").replace("/", " ").split()
                )
                if (
                    content_range[0] != "bytes"
                ):  # TODO check x<y not negative < total....
                    raise IndexError()
                start = int(content_range[1])
                end = int(content_range[2]) + 1
                total = int(content_range[3])
            else:
                start = 0
            # Rather than using a temp folder, we will store the package in a folder based on
            # the current revision.
            proposed_revision_path = (
                _id + ":" + str(revision)
            )  # all the content is upload here and if ok, it is rename from id_ to is folder

            if start:
                if not self.fs.file_exists(proposed_revision_path, "dir"):
                    raise EngineException(
                        "invalid Transaction-Id header", HTTPStatus.NOT_FOUND
                    )
            else:
                self.fs.file_delete(proposed_revision_path, ignore_non_exist=True)
                self.fs.mkdir(proposed_revision_path)
                fs_rollback.append(proposed_revision_path)

            storage = self.fs.get_params()
            storage["folder"] = proposed_revision_path

            file_path = (proposed_revision_path, filename)
            if self.fs.file_exists(file_path, "file"):
                file_size = self.fs.file_size(file_path)
            else:
                file_size = 0
            if file_size != start:
                raise EngineException(
                    "invalid Content-Range start sequence, expected '{}' but received '{}'".format(
                        file_size, start
                    ),
                    HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                )
            file_pkg = self.fs.file_open(file_path, "a+b")

            if isinstance(indata, dict):
                indata_text = yaml.safe_dump(indata, indent=4, default_flow_style=False)
                file_pkg.write(indata_text.encode(encoding="utf-8"))
            else:
                indata_len = 0
                while True:
                    indata_text = indata.read(4096)
                    indata_len += len(indata_text)
                    if not indata_text:
                        break
                    file_pkg.write(indata_text)
            if content_range_text:
                if indata_len != end - start:
                    raise EngineException(
                        "Mismatch between Content-Range header {}-{} and body length of {}".format(
                            start, end - 1, indata_len
                        ),
                        HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                    )
                if end != total:
                    # TODO update to UPLOADING
                    return False

            # PACKAGE UPLOADED
            if expected_md5:
                file_pkg.seek(0, 0)
                file_md5 = md5()
                chunk_data = file_pkg.read(1024)
                while chunk_data:
                    file_md5.update(chunk_data)
                    chunk_data = file_pkg.read(1024)
                if expected_md5 != file_md5.hexdigest():
                    raise EngineException("Error, MD5 mismatch", HTTPStatus.CONFLICT)
            if digest_header:
                alg, b64_digest = digest_header.split("=", 1)
                if alg.strip().lower() != "sha-384":
                    raise ValueError(f"Unsupported digest algorithm: {alg}")
                expected_digest = base64.b64decode(b64_digest)
                # Get real digest
                file_pkg.seek(0, 0)
                file_sha384 = sha384()
                chunk_data = file_pkg.read(1024)
                while chunk_data:
                    file_sha384.update(chunk_data)
                    chunk_data = file_pkg.read(1024)
                if expected_digest != file_sha384.digest():
                    raise EngineException("Error, SHA384 mismatch", HTTPStatus.CONFLICT)
            file_pkg.seek(0, 0)
            if compressed == "gzip":
                tar = tarfile.open(mode="r", fileobj=file_pkg)
                descriptor_file_name = None
                for tarinfo in tar:
                    tarname = tarinfo.name
                    tarname_path = tarname.split("/")
                    if (
                        not tarname_path[0] or ".." in tarname_path
                    ):  # if start with "/" means absolute path
                        raise EngineException(
                            "Absolute path or '..' are not allowed for package descriptor tar.gz"
                        )
                    if len(tarname_path) == 1 and not tarinfo.isdir():
                        raise EngineException(
                            "All files must be inside a dir for package descriptor tar.gz"
                        )
                    if (
                        tarname.endswith(".yaml")
                        or tarname.endswith(".json")
                        or tarname.endswith(".yml")
                    ):
                        storage["pkg-dir"] = tarname_path[0]
                        if len(tarname_path) == 2:
                            if descriptor_file_name:
                                raise EngineException(
                                    "Found more than one descriptor file at package descriptor tar.gz"
                                )
                            descriptor_file_name = tarname
                if not descriptor_file_name:
                    raise EngineException(
                        "Not found any descriptor file at package descriptor tar.gz"
                    )
                storage["descriptor"] = descriptor_file_name
                storage["zipfile"] = filename
                self.fs.file_extract(tar, proposed_revision_path)
                with self.fs.file_open(
                    (proposed_revision_path, descriptor_file_name), "r"
                ) as descriptor_file:
                    content = descriptor_file.read()
            elif compressed == "zip":
                zipfile = ZipFile(file_pkg)
                descriptor_file_name = None
                for package_file in zipfile.infolist():
                    zipfilename = package_file.filename
                    file_path = zipfilename.split("/")
                    if (
                        not file_path[0] or ".." in zipfilename
                    ):  # if start with "/" means absolute path
                        raise EngineException(
                            "Absolute path or '..' are not allowed for package descriptor zip"
                        )

                    if (
                        zipfilename.endswith(".yaml")
                        or zipfilename.endswith(".json")
                        or zipfilename.endswith(".yml")
                    ) and (
                        zipfilename.find("/") < 0
                        or zipfilename.find("Definitions") >= 0
                    ):
                        storage["pkg-dir"] = ""
                        if descriptor_file_name:
                            raise EngineException(
                                "Found more than one descriptor file at package descriptor zip"
                            )
                        descriptor_file_name = zipfilename
                if not descriptor_file_name:
                    raise EngineException(
                        "Not found any descriptor file at package descriptor zip"
                    )
                storage["descriptor"] = descriptor_file_name
                storage["zipfile"] = filename
                self.fs.file_extract(zipfile, proposed_revision_path)

                with self.fs.file_open(
                    (proposed_revision_path, descriptor_file_name), "r"
                ) as descriptor_file:
                    content = descriptor_file.read()
            else:
                content = file_pkg.read()
                storage["descriptor"] = descriptor_file_name = filename

            if descriptor_file_name.endswith(".json"):
                error_text = "Invalid json format "
                indata = json.load(content)
            else:
                error_text = "Invalid yaml format "
                indata = yaml.safe_load(content)

            # Need to close the file package here so it can be copied from the
            # revision to the current, unrevisioned record
            if file_pkg:
                file_pkg.close()
            file_pkg = None

            # Fetch both the incoming, proposed revision and the original revision so we
            # can call a validate method to compare them
            current_revision_path = _id + "/"
            self.fs.sync(from_path=current_revision_path)
            self.fs.sync(from_path=proposed_revision_path)

            if revision > 1:
                try:
                    self._validate_descriptor_changes(
                        _id,
                        descriptor_file_name,
                        current_revision_path,
                        proposed_revision_path,
                    )
                except Exception as e:
                    shutil.rmtree(
                        self.fs.path + current_revision_path, ignore_errors=True
                    )
                    shutil.rmtree(
                        self.fs.path + proposed_revision_path, ignore_errors=True
                    )
                    # Only delete the new revision.  We need to keep the original version in place
                    # as it has not been changed.
                    self.fs.file_delete(proposed_revision_path, ignore_non_exist=True)
                    raise e

            indata = self._remove_envelop(indata)

            # Override descriptor with query string kwargs
            if kwargs:
                self._update_input_with_kwargs(indata, kwargs)

            current_desc["_admin"]["storage"] = storage
            current_desc["_admin"]["onboardingState"] = "ONBOARDED"
            current_desc["_admin"]["operationalState"] = "ENABLED"
            current_desc["_admin"]["modified"] = time()
            current_desc["_admin"]["revision"] = revision

            deep_update_rfc7396(current_desc, indata)
            current_desc = self.check_conflict_on_edit(
                session, current_desc, indata, _id=_id
            )

            # Copy the revision to the active package name by its original id
            shutil.rmtree(self.fs.path + current_revision_path, ignore_errors=True)
            os.rename(
                self.fs.path + proposed_revision_path,
                self.fs.path + current_revision_path,
            )
            self.fs.file_delete(current_revision_path, ignore_non_exist=True)
            self.fs.mkdir(current_revision_path)
            self.fs.reverse_sync(from_path=current_revision_path)

            shutil.rmtree(self.fs.path + _id)

            self.db.replace(self.topic, _id, current_desc)

            #  Store a copy of the package as a point in time revision
            revision_desc = dict(current_desc)
            revision_desc["_id"] = _id + ":" + str(revision_desc["_admin"]["revision"])
            self.db.create(self.topic + "_revisions", revision_desc)
            fs_rollback = []

            indata["_id"] = _id
            self._send_msg("edited", indata)

            # TODO if descriptor has changed because kwargs update content and remove cached zip
            # TODO if zip is not present creates one
            return True

        except EngineException:
            raise
        except IndexError:
            raise EngineException(
                "invalid Content-Range header format. Expected 'bytes start-end/total'",
                HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
            )
        except IOError as e:
            raise EngineException(
                "invalid upload transaction sequence: '{}'".format(e),
                HTTPStatus.BAD_REQUEST,
            )
        except tarfile.ReadError as e:
            raise EngineException(
                "invalid file content {}".format(e), HTTPStatus.BAD_REQUEST
            )
        except (ValueError, yaml.YAMLError) as e:
            raise EngineException(error_text + str(e))
        except ValidationError as e:
            raise EngineException(e, HTTPStatus.UNPROCESSABLE_ENTITY)
        finally:
            if file_pkg:
                file_pkg.close()
            for file in fs_rollback:
                self.fs.file_delete(file, ignore_non_exist=True)

    def get_file(self, session, _id, path=None, accept_header=None):
        """
        Return the file content of a vnfd or nsd
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: Identity of the vnfd, nsd
        :param path: artifact path or "$DESCRIPTOR" or None
        :param accept_header: Content of Accept header. Must contain applition/zip or/and text/plain
        :return: opened file plus Accept format or raises an exception
        """
        accept_text = accept_zip = False
        if accept_header:
            if "text/plain" in accept_header or "*/*" in accept_header:
                accept_text = True
            if "application/zip" in accept_header or "*/*" in accept_header:
                accept_zip = "application/zip"
            elif "application/gzip" in accept_header:
                accept_zip = "application/gzip"

        if not accept_text and not accept_zip:
            raise EngineException(
                "provide request header 'Accept' with 'application/zip' or 'text/plain'",
                http_code=HTTPStatus.NOT_ACCEPTABLE,
            )

        content = self.show(session, _id)
        if content["_admin"]["onboardingState"] != "ONBOARDED":
            raise EngineException(
                "Cannot get content because this resource is not at 'ONBOARDED' state. "
                "onboardingState is {}".format(content["_admin"]["onboardingState"]),
                http_code=HTTPStatus.CONFLICT,
            )
        storage = content["_admin"]["storage"]
        if path is not None and path != "$DESCRIPTOR":  # artifacts
            if not storage.get("pkg-dir") and not storage.get("folder"):
                raise EngineException(
                    "Packages does not contains artifacts",
                    http_code=HTTPStatus.BAD_REQUEST,
                )
            if self.fs.file_exists(
                (storage["folder"], storage["pkg-dir"], *path), "dir"
            ):
                folder_content = self.fs.dir_ls(
                    (storage["folder"], storage["pkg-dir"], *path)
                )
                return folder_content, "text/plain"
                # TODO manage folders in http
            else:
                return (
                    self.fs.file_open(
                        (storage["folder"], storage["pkg-dir"], *path), "rb"
                    ),
                    "application/octet-stream",
                )

        # pkgtype   accept  ZIP  TEXT    -> result
        # manyfiles         yes  X       -> zip
        #                   no   yes     -> error
        # onefile           yes  no      -> zip
        #                   X    yes     -> text
        contain_many_files = False
        if storage.get("pkg-dir"):
            # check if there are more than one file in the package, ignoring checksums.txt.
            pkg_files = self.fs.dir_ls((storage["folder"], storage["pkg-dir"]))
            if len(pkg_files) >= 3 or (
                len(pkg_files) == 2 and "checksums.txt" not in pkg_files
            ):
                contain_many_files = True
        if accept_text and (not contain_many_files or path == "$DESCRIPTOR"):
            return (
                self.fs.file_open((storage["folder"], storage["descriptor"]), "r"),
                "text/plain",
            )
        elif contain_many_files and not accept_zip:
            raise EngineException(
                "Packages that contains several files need to be retrieved with 'application/zip'"
                "Accept header",
                http_code=HTTPStatus.NOT_ACCEPTABLE,
            )
        else:
            if not storage.get("zipfile"):
                # TODO generate zipfile if not present
                raise EngineException(
                    "Only allowed 'text/plain' Accept header for this descriptor. To be solved in "
                    "future versions",
                    http_code=HTTPStatus.NOT_ACCEPTABLE,
                )
            return (
                self.fs.file_open((storage["folder"], storage["zipfile"]), "rb"),
                accept_zip,
            )

    def _remove_yang_prefixes_from_descriptor(self, descriptor):
        new_descriptor = {}
        for k, v in descriptor.items():
            new_v = v
            if isinstance(v, dict):
                new_v = self._remove_yang_prefixes_from_descriptor(v)
            elif isinstance(v, list):
                new_v = list()
                for x in v:
                    if isinstance(x, dict):
                        new_v.append(self._remove_yang_prefixes_from_descriptor(x))
                    else:
                        new_v.append(x)
            new_descriptor[k.split(":")[-1]] = new_v
        return new_descriptor

    def pyangbind_validation(self, item, data, force=False):
        raise EngineException(
            "Not possible to validate '{}' item".format(item),
            http_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def _validate_input_edit(self, indata, content, force=False):
        # not needed to validate with pyangbind becuase it will be validated at check_conflict_on_edit
        if "_id" in indata:
            indata.pop("_id")
        if "_admin" not in indata:
            indata["_admin"] = {}

        if "operationalState" in indata:
            if indata["operationalState"] in ("ENABLED", "DISABLED"):
                indata["_admin"]["operationalState"] = indata.pop("operationalState")
            else:
                raise EngineException(
                    "State '{}' is not a valid operational state".format(
                        indata["operationalState"]
                    ),
                    http_code=HTTPStatus.BAD_REQUEST,
                )

        # In the case of user defined data, we need to put the data in the root of the object
        # to preserve current expected behaviour
        if "userDefinedData" in indata:
            data = indata.pop("userDefinedData")
            if isinstance(data, dict):
                indata["_admin"]["userDefinedData"] = data
            else:
                raise EngineException(
                    "userDefinedData should be an object, but is '{}' instead".format(
                        type(data)
                    ),
                    http_code=HTTPStatus.BAD_REQUEST,
                )

        if (
            "operationalState" in indata["_admin"]
            and content["_admin"]["operationalState"]
            == indata["_admin"]["operationalState"]
        ):
            raise EngineException(
                "operationalState already {}".format(
                    content["_admin"]["operationalState"]
                ),
                http_code=HTTPStatus.CONFLICT,
            )

        return indata

    def _validate_descriptor_changes(
        self,
        descriptor_id,
        descriptor_file_name,
        old_descriptor_directory,
        new_descriptor_directory,
    ):
        # Example:
        #    raise EngineException(
        #           "Error in validating new descriptor: <NODE> cannot be modified",
        #           http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        #    )
        pass


class VnfdTopic(DescriptorTopic):
    topic = "vnfds"
    topic_msg = "vnfd"

    def __init__(self, db, fs, msg, auth):
        DescriptorTopic.__init__(self, db, fs, msg, auth)

    def pyangbind_validation(self, item, data, force=False):
        if self._descriptor_data_is_in_old_format(data):
            raise EngineException(
                "ERROR: Unsupported descriptor format. Please, use an ETSI SOL006 descriptor.",
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        try:
            myvnfd = etsi_nfv_vnfd.etsi_nfv_vnfd()
            pybindJSONDecoder.load_ietf_json(
                {"etsi-nfv-vnfd:vnfd": data},
                None,
                None,
                obj=myvnfd,
                path_helper=True,
                skip_unknown=force,
            )
            out = pybindJSON.dumps(myvnfd, mode="ietf")
            desc_out = self._remove_envelop(yaml.safe_load(out))
            desc_out = self._remove_yang_prefixes_from_descriptor(desc_out)
            return utils.deep_update_dict(data, desc_out)
        except Exception as e:
            raise EngineException(
                "Error in pyangbind validation: {}".format(str(e)),
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    @staticmethod
    def _descriptor_data_is_in_old_format(data):
        return ("vnfd-catalog" in data) or ("vnfd:vnfd-catalog" in data)

    @staticmethod
    def _remove_envelop(indata=None):
        if not indata:
            return {}
        clean_indata = indata

        if clean_indata.get("etsi-nfv-vnfd:vnfd"):
            if not isinstance(clean_indata["etsi-nfv-vnfd:vnfd"], dict):
                raise EngineException("'etsi-nfv-vnfd:vnfd' must be a dict")
            clean_indata = clean_indata["etsi-nfv-vnfd:vnfd"]
        elif clean_indata.get("vnfd"):
            if not isinstance(clean_indata["vnfd"], dict):
                raise EngineException("'vnfd' must be dict")
            clean_indata = clean_indata["vnfd"]

        return clean_indata

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        final_content = super().check_conflict_on_edit(
            session, final_content, edit_content, _id
        )

        # set type of vnfd
        contains_pdu = False
        contains_vdu = False
        for vdu in get_iterable(final_content.get("vdu")):
            if vdu.get("pdu-type"):
                contains_pdu = True
            else:
                contains_vdu = True
        if contains_pdu:
            final_content["_admin"]["type"] = "hnfd" if contains_vdu else "pnfd"
        elif contains_vdu:
            final_content["_admin"]["type"] = "vnfd"
        # if neither vud nor pdu do not fill type
        return final_content

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that there is not any NSD that uses this VNFD. Only NSDs belonging to this project are considered. Note
        that VNFD can be public and be used by NSD of other projects. Also check there are not deployments, or vnfr
        that uses this vnfd
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: vnfd internal id
        :param db_content: The database content of the _id.
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return
        descriptor = db_content
        descriptor_id = descriptor.get("id")
        if not descriptor_id:  # empty vnfd not uploaded
            return

        _filter = self._get_project_filter(session)
        # check vnfrs using this vnfd
        _filter["vnfd-id"] = _id

        if self.db.get_list("vnfrs", _filter):
            raise EngineException(
                "There is at least one VNF instance using this descriptor",
                http_code=HTTPStatus.CONFLICT,
            )

        # check NSD referencing this VNFD
        del _filter["vnfd-id"]
        _filter["vnfd-id"] = descriptor_id

        if self.db.get_list("nsds", _filter):
            raise EngineException(
                "There is at least one NS package referencing this descriptor",
                http_code=HTTPStatus.CONFLICT,
            )

    def _validate_input_new(self, indata, storage_params, force=False):
        indata.pop("onboardingState", None)
        indata.pop("operationalState", None)
        indata.pop("usageState", None)
        indata.pop("links", None)

        validation = validation_im()
        indata = self.pyangbind_validation("vnfds", indata, force)
        # Cross references validation in the descriptor

        self.validate_mgmt_interface_connection_point(indata)

        for vdu in get_iterable(indata.get("vdu")):
            self.validate_vdu_internal_connection_points(vdu)
            self._validate_vdu_cloud_init_in_package(storage_params, vdu, indata)
        self._validate_vdu_charms_in_package(storage_params, indata)

        self._validate_vnf_charms_in_package(storage_params, indata)

        self.validate_external_connection_points(indata)
        self.validate_internal_virtual_links(indata)
        self.validate_monitoring_params(indata)
        self.validate_scaling_group_descriptor(indata)
        self.validate_healing_group_descriptor(indata)
        self.validate_alarm_group_descriptor(indata)
        self.validate_storage_compute_descriptor(indata)
        validation.validate_vdu_profile_in_descriptor(indata)
        validation.validate_instantiation_level_descriptor(indata)
        self.validate_helm_chart(indata)

        return indata

    @staticmethod
    def validate_helm_chart(indata):
        def is_url(url):
            result = urlparse(url)
            return all([result.scheme, result.netloc])

        kdus = indata.get("kdu", [])
        for kdu in kdus:
            helm_chart_value = kdu.get("helm-chart")
            if not helm_chart_value:
                continue
            if not (
                valid_helm_chart_re.match(helm_chart_value) or is_url(helm_chart_value)
            ):
                raise EngineException(
                    "helm-chart '{}' is not valid".format(helm_chart_value),
                    http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )

    @staticmethod
    def validate_mgmt_interface_connection_point(indata):
        if not indata.get("vdu"):
            return
        if not indata.get("mgmt-cp"):
            raise EngineException(
                "'mgmt-cp' is a mandatory field and it is not defined",
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        for cp in get_iterable(indata.get("ext-cpd")):
            if cp["id"] == indata["mgmt-cp"]:
                break
        else:
            raise EngineException(
                "mgmt-cp='{}' must match an existing ext-cpd".format(indata["mgmt-cp"]),
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    @staticmethod
    def validate_vdu_internal_connection_points(vdu):
        int_cpds = set()
        for cpd in get_iterable(vdu.get("int-cpd")):
            cpd_id = cpd.get("id")
            if cpd_id and cpd_id in int_cpds:
                raise EngineException(
                    "vdu[id='{}']:int-cpd[id='{}'] is already used by other int-cpd".format(
                        vdu["id"], cpd_id
                    ),
                    http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            int_cpds.add(cpd_id)

    @staticmethod
    def validate_external_connection_points(indata):
        all_vdus_int_cpds = set()
        for vdu in get_iterable(indata.get("vdu")):
            for int_cpd in get_iterable(vdu.get("int-cpd")):
                all_vdus_int_cpds.add((vdu.get("id"), int_cpd.get("id")))

        ext_cpds = set()
        for cpd in get_iterable(indata.get("ext-cpd")):
            cpd_id = cpd.get("id")
            if cpd_id and cpd_id in ext_cpds:
                raise EngineException(
                    "ext-cpd[id='{}'] is already used by other ext-cpd".format(cpd_id),
                    http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            ext_cpds.add(cpd_id)

            int_cpd = cpd.get("int-cpd")
            if int_cpd:
                if (int_cpd.get("vdu-id"), int_cpd.get("cpd")) not in all_vdus_int_cpds:
                    raise EngineException(
                        "ext-cpd[id='{}']:int-cpd must match an existing vdu int-cpd".format(
                            cpd_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
            # TODO: Validate k8s-cluster-net points to a valid k8s-cluster:nets ?

    def _validate_vdu_charms_in_package(self, storage_params, indata):
        for df in indata["df"]:
            if (
                "lcm-operations-configuration" in df
                and "operate-vnf-op-config" in df["lcm-operations-configuration"]
            ):
                configs = df["lcm-operations-configuration"][
                    "operate-vnf-op-config"
                ].get("day1-2", [])
                vdus = df.get("vdu-profile", [])
                for vdu in vdus:
                    for config in configs:
                        if config["id"] == vdu["id"] and utils.find_in_list(
                            config.get("execution-environment-list", []),
                            lambda ee: "juju" in ee,
                        ):
                            if not self._validate_package_folders(
                                storage_params, "charms"
                            ) and not self._validate_package_folders(
                                storage_params, "Scripts/charms"
                            ):
                                raise EngineException(
                                    "Charm defined in vnf[id={}] but not present in "
                                    "package".format(indata["id"])
                                )

    def _validate_vdu_cloud_init_in_package(self, storage_params, vdu, indata):
        if not vdu.get("cloud-init-file"):
            return
        if not self._validate_package_folders(
            storage_params, "cloud_init", vdu["cloud-init-file"]
        ) and not self._validate_package_folders(
            storage_params, "Scripts/cloud_init", vdu["cloud-init-file"]
        ):
            raise EngineException(
                "Cloud-init defined in vnf[id={}]:vdu[id={}] but not present in "
                "package".format(indata["id"], vdu["id"])
            )

    def _validate_vnf_charms_in_package(self, storage_params, indata):
        # Get VNF configuration through new container
        for deployment_flavor in indata.get("df", []):
            if "lcm-operations-configuration" not in deployment_flavor:
                return
            if (
                "operate-vnf-op-config"
                not in deployment_flavor["lcm-operations-configuration"]
            ):
                return
            for day_1_2_config in deployment_flavor["lcm-operations-configuration"][
                "operate-vnf-op-config"
            ]["day1-2"]:
                if day_1_2_config["id"] == indata["id"]:
                    if utils.find_in_list(
                        day_1_2_config.get("execution-environment-list", []),
                        lambda ee: "juju" in ee,
                    ):
                        if not self._validate_package_folders(
                            storage_params, "charms"
                        ) and not self._validate_package_folders(
                            storage_params, "Scripts/charms"
                        ):
                            raise EngineException(
                                "Charm defined in vnf[id={}] but not present in "
                                "package".format(indata["id"])
                            )

    def _validate_package_folders(self, storage_params, folder, file=None):
        if not storage_params:
            return False
        elif not storage_params.get("pkg-dir"):
            if self.fs.file_exists("{}_".format(storage_params["folder"]), "dir"):
                f = "{}_/{}".format(storage_params["folder"], folder)
            else:
                f = "{}/{}".format(storage_params["folder"], folder)
            if file:
                return self.fs.file_exists("{}/{}".format(f, file), "file")
            else:
                if self.fs.file_exists(f, "dir"):
                    if self.fs.dir_ls(f):
                        return True
            return False
        else:
            if self.fs.file_exists("{}_".format(storage_params["folder"]), "dir"):
                f = "{}_/{}/{}".format(
                    storage_params["folder"], storage_params["pkg-dir"], folder
                )
            else:
                f = "{}/{}/{}".format(
                    storage_params["folder"], storage_params["pkg-dir"], folder
                )
            if file:
                return self.fs.file_exists("{}/{}".format(f, file), "file")
            else:
                if self.fs.file_exists(f, "dir"):
                    if self.fs.dir_ls(f):
                        return True
            return False

    @staticmethod
    def validate_internal_virtual_links(indata):
        all_ivld_ids = set()
        for ivld in get_iterable(indata.get("int-virtual-link-desc")):
            ivld_id = ivld.get("id")
            if ivld_id and ivld_id in all_ivld_ids:
                raise EngineException(
                    "Duplicated VLD id in int-virtual-link-desc[id={}]".format(ivld_id),
                    http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            else:
                all_ivld_ids.add(ivld_id)

        for vdu in get_iterable(indata.get("vdu")):
            for int_cpd in get_iterable(vdu.get("int-cpd")):
                int_cpd_ivld_id = int_cpd.get("int-virtual-link-desc")
                if int_cpd_ivld_id and int_cpd_ivld_id not in all_ivld_ids:
                    raise EngineException(
                        "vdu[id='{}']:int-cpd[id='{}']:int-virtual-link-desc='{}' must match an existing "
                        "int-virtual-link-desc".format(
                            vdu["id"], int_cpd["id"], int_cpd_ivld_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

        for df in get_iterable(indata.get("df")):
            for vlp in get_iterable(df.get("virtual-link-profile")):
                vlp_ivld_id = vlp.get("id")
                if vlp_ivld_id and vlp_ivld_id not in all_ivld_ids:
                    raise EngineException(
                        "df[id='{}']:virtual-link-profile='{}' must match an existing "
                        "int-virtual-link-desc".format(df["id"], vlp_ivld_id),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

    @staticmethod
    def validate_monitoring_params(indata):
        all_monitoring_params = set()
        for ivld in get_iterable(indata.get("int-virtual-link-desc")):
            for mp in get_iterable(ivld.get("monitoring-parameters")):
                mp_id = mp.get("id")
                if mp_id and mp_id in all_monitoring_params:
                    raise EngineException(
                        "Duplicated monitoring-parameter id in "
                        "int-virtual-link-desc[id='{}']:monitoring-parameters[id='{}']".format(
                            ivld["id"], mp_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                else:
                    all_monitoring_params.add(mp_id)

        for vdu in get_iterable(indata.get("vdu")):
            for mp in get_iterable(vdu.get("monitoring-parameter")):
                mp_id = mp.get("id")
                if mp_id and mp_id in all_monitoring_params:
                    raise EngineException(
                        "Duplicated monitoring-parameter id in "
                        "vdu[id='{}']:monitoring-parameter[id='{}']".format(
                            vdu["id"], mp_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                else:
                    all_monitoring_params.add(mp_id)

        for df in get_iterable(indata.get("df")):
            for mp in get_iterable(df.get("monitoring-parameter")):
                mp_id = mp.get("id")
                if mp_id and mp_id in all_monitoring_params:
                    raise EngineException(
                        "Duplicated monitoring-parameter id in "
                        "df[id='{}']:monitoring-parameter[id='{}']".format(
                            df["id"], mp_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                else:
                    all_monitoring_params.add(mp_id)

    @staticmethod
    def validate_scaling_group_descriptor(indata):
        all_monitoring_params = set()
        all_vdu_ids = set()
        for df in get_iterable(indata.get("df")):
            for il in get_iterable(df.get("instantiation-level")):
                for vl in get_iterable(il.get("vdu-level")):
                    all_vdu_ids.add(vl.get("vdu-id"))

        for ivld in get_iterable(indata.get("int-virtual-link-desc")):
            for mp in get_iterable(ivld.get("monitoring-parameters")):
                all_monitoring_params.add(mp.get("id"))

        for vdu in get_iterable(indata.get("vdu")):
            for mp in get_iterable(vdu.get("monitoring-parameter")):
                all_monitoring_params.add(mp.get("id"))

        for df in get_iterable(indata.get("df")):
            for mp in get_iterable(df.get("monitoring-parameter")):
                all_monitoring_params.add(mp.get("id"))

        for df in get_iterable(indata.get("df")):
            for sa in get_iterable(df.get("scaling-aspect")):
                for deltas in get_iterable(
                    sa.get("aspect-delta-details").get("deltas")
                ):
                    for vds in get_iterable(deltas.get("vdu-delta")):
                        sa_vdu_id = vds.get("id")
                        if sa_vdu_id and sa_vdu_id not in all_vdu_ids:
                            raise EngineException(
                                "df[id='{}']:scaling-aspect[id='{}']:aspect-delta-details"
                                "[delta='{}']: "
                                "vdu-id='{}' not defined in vdu".format(
                                    df["id"],
                                    sa["id"],
                                    deltas["id"],
                                    sa_vdu_id,
                                ),
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )

        for df in get_iterable(indata.get("df")):
            for sa in get_iterable(df.get("scaling-aspect")):
                for sp in get_iterable(sa.get("scaling-policy")):
                    for sc in get_iterable(sp.get("scaling-criteria")):
                        sc_monitoring_param = sc.get("vnf-monitoring-param-ref")
                        if (
                            sc_monitoring_param
                            and sc_monitoring_param not in all_monitoring_params
                        ):
                            raise EngineException(
                                "df[id='{}']:scaling-aspect[id='{}']:scaling-policy"
                                "[name='{}']:scaling-criteria[name='{}']: "
                                "vnf-monitoring-param-ref='{}' not defined in any monitoring-param".format(
                                    df["id"],
                                    sa["id"],
                                    sp["name"],
                                    sc["name"],
                                    sc_monitoring_param,
                                ),
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )

                for sca in get_iterable(sa.get("scaling-config-action")):
                    if (
                        "lcm-operations-configuration" not in df
                        or "operate-vnf-op-config"
                        not in df["lcm-operations-configuration"]
                        or not utils.find_in_list(
                            df["lcm-operations-configuration"][
                                "operate-vnf-op-config"
                            ].get("day1-2", []),
                            lambda config: config["id"] == indata["id"],
                        )
                    ):
                        raise EngineException(
                            "'day1-2 configuration' not defined in the descriptor but it is "
                            "referenced by df[id='{}']:scaling-aspect[id='{}']:scaling-config-action".format(
                                df["id"], sa["id"]
                            ),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )
                    for configuration in get_iterable(
                        df["lcm-operations-configuration"]["operate-vnf-op-config"].get(
                            "day1-2", []
                        )
                    ):
                        for primitive in get_iterable(
                            configuration.get("config-primitive")
                        ):
                            if (
                                primitive["name"]
                                == sca["vnf-config-primitive-name-ref"]
                            ):
                                break
                        else:
                            raise EngineException(
                                "df[id='{}']:scaling-aspect[id='{}']:scaling-config-action:vnf-"
                                "config-primitive-name-ref='{}' does not match any "
                                "day1-2 configuration:config-primitive:name".format(
                                    df["id"],
                                    sa["id"],
                                    sca["vnf-config-primitive-name-ref"],
                                ),
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )

    @staticmethod
    def validate_healing_group_descriptor(indata):
        all_vdu_ids = set()
        for df in get_iterable(indata.get("df")):
            for il in get_iterable(df.get("instantiation-level")):
                for vl in get_iterable(il.get("vdu-level")):
                    all_vdu_ids.add(vl.get("vdu-id"))

        for df in get_iterable(indata.get("df")):
            for ha in get_iterable(df.get("healing-aspect")):
                for hp in get_iterable(ha.get("healing-policy")):
                    hp_monitoring_param = hp.get("vdu-id")
                    if hp_monitoring_param and hp_monitoring_param not in all_vdu_ids:
                        raise EngineException(
                            "df[id='{}']:healing-aspect[id='{}']:healing-policy"
                            "[name='{}']: "
                            "vdu-id='{}' not defined in vdu".format(
                                df["id"],
                                ha["id"],
                                hp["event-name"],
                                hp_monitoring_param,
                            ),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )

    @staticmethod
    def validate_alarm_group_descriptor(indata):
        all_monitoring_params = set()
        for ivld in get_iterable(indata.get("int-virtual-link-desc")):
            for mp in get_iterable(ivld.get("monitoring-parameters")):
                all_monitoring_params.add(mp.get("id"))

        for vdu in get_iterable(indata.get("vdu")):
            for mp in get_iterable(vdu.get("monitoring-parameter")):
                all_monitoring_params.add(mp.get("id"))

        for df in get_iterable(indata.get("df")):
            for mp in get_iterable(df.get("monitoring-parameter")):
                all_monitoring_params.add(mp.get("id"))

        for vdus in get_iterable(indata.get("vdu")):
            for alarms in get_iterable(vdus.get("alarm")):
                alarm_monitoring_param = alarms.get("vnf-monitoring-param-ref")
                if (
                    alarm_monitoring_param
                    and alarm_monitoring_param not in all_monitoring_params
                ):
                    raise EngineException(
                        "vdu[id='{}']:alarm[id='{}']:"
                        "vnf-monitoring-param-ref='{}' not defined in any monitoring-param".format(
                            vdus["id"],
                            alarms["alarm-id"],
                            alarm_monitoring_param,
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

    @staticmethod
    def validate_storage_compute_descriptor(indata):
        all_vsd_ids = set()
        for vsd in get_iterable(indata.get("virtual-storage-desc")):
            all_vsd_ids.add(vsd.get("id"))

        all_vcd_ids = set()
        for vcd in get_iterable(indata.get("virtual-compute-desc")):
            all_vcd_ids.add(vcd.get("id"))

        for vdu in get_iterable(indata.get("vdu")):
            if "pdu-type" in vdu:
                continue
            for vsd_ref in vdu.get("virtual-storage-desc"):
                if vsd_ref and vsd_ref not in all_vsd_ids:
                    raise EngineException(
                        "vdu[virtual-storage-desc='{}']"
                        "not defined in vnfd".format(
                            vsd_ref,
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

        for vdu in get_iterable(indata.get("vdu")):
            if "pdu-type" in vdu:
                continue
            vcd_ref = vdu.get("virtual-compute-desc")
            if vcd_ref and vcd_ref not in all_vcd_ids:
                raise EngineException(
                    "vdu[virtual-compute-desc='{}']"
                    "not defined in vnfd".format(
                        vdu["virtual-compute-desc"],
                    ),
                    http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )

    def delete_extra(self, session, _id, db_content, not_send_msg=None):
        """
        Deletes associate file system storage (via super)
        Deletes associated vnfpkgops from database.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param db_content: The database content of the descriptor
        :return: None
        :raises: FsException in case of error while deleting associated storage
        """
        super().delete_extra(session, _id, db_content, not_send_msg)
        self.db.del_list("vnfpkgops", {"vnfPkgId": _id})
        self.db.del_list(self.topic + "_revisions", {"_id": {"$regex": _id}})

    def sol005_projection(self, data):
        data["onboardingState"] = data["_admin"]["onboardingState"]
        data["operationalState"] = data["_admin"]["operationalState"]
        data["usageState"] = data["_admin"]["usageState"]

        links = {}
        links["self"] = {"href": "/vnfpkgm/v1/vnf_packages/{}".format(data["_id"])}
        links["vnfd"] = {"href": "/vnfpkgm/v1/vnf_packages/{}/vnfd".format(data["_id"])}
        links["packageContent"] = {
            "href": "/vnfpkgm/v1/vnf_packages/{}/package_content".format(data["_id"])
        }
        data["_links"] = links

        return super().sol005_projection(data)

    @staticmethod
    def find_software_version(vnfd: dict) -> str:
        """Find the sotware version in the VNFD descriptors

        Args:
            vnfd (dict): Descriptor as a dictionary

        Returns:
            software-version (str)
        """
        default_sw_version = "1.0"
        if vnfd.get("vnfd"):
            vnfd = vnfd["vnfd"]
        if vnfd.get("software-version"):
            return vnfd["software-version"]
        else:
            return default_sw_version

    @staticmethod
    def extract_policies(vnfd: dict) -> dict:
        """Removes the policies from the VNFD descriptors

        Args:
            vnfd (dict):   Descriptor as a dictionary

        Returns:
            vnfd (dict): VNFD which does not include policies
        """
        for df in vnfd.get("df", {}):
            for policy in ["scaling-aspect", "healing-aspect"]:
                if df.get(policy, {}):
                    df.pop(policy)
        for vdu in vnfd.get("vdu", {}):
            for alarm_policy in ["alarm", "monitoring-parameter"]:
                if vdu.get(alarm_policy, {}):
                    vdu.pop(alarm_policy)
        return vnfd

    @staticmethod
    def extract_day12_primitives(vnfd: dict) -> dict:
        """Removes the day12 primitives from the VNFD descriptors

        Args:
            vnfd (dict):   Descriptor as a dictionary

        Returns:
            vnfd (dict)
        """
        for df_id, df in enumerate(vnfd.get("df", {})):
            if (
                df.get("lcm-operations-configuration", {})
                .get("operate-vnf-op-config", {})
                .get("day1-2")
            ):
                day12 = df["lcm-operations-configuration"]["operate-vnf-op-config"].get(
                    "day1-2"
                )
                for config_id, config in enumerate(day12):
                    for key in [
                        "initial-config-primitive",
                        "config-primitive",
                        "terminate-config-primitive",
                    ]:
                        config.pop(key, None)
                        day12[config_id] = config
                df["lcm-operations-configuration"]["operate-vnf-op-config"][
                    "day1-2"
                ] = day12
            vnfd["df"][df_id] = df
        return vnfd

    def remove_modifiable_items(self, vnfd: dict) -> dict:
        """Removes the modifiable parts from the VNFD descriptors

        It calls different extract functions according to different update types
        to clear all the modifiable items from VNFD

        Args:
            vnfd (dict): Descriptor as a dictionary

        Returns:
            vnfd (dict): Descriptor which does not include modifiable contents
        """
        if vnfd.get("vnfd"):
            vnfd = vnfd["vnfd"]
        vnfd.pop("_admin", None)
        # If the other extractions need to be done from VNFD,
        # the new extract methods could be appended to below list.
        for extract_function in [self.extract_day12_primitives, self.extract_policies]:
            vnfd_temp = extract_function(vnfd)
            vnfd = vnfd_temp
        return vnfd

    def _validate_descriptor_changes(
        self,
        descriptor_id: str,
        descriptor_file_name: str,
        old_descriptor_directory: str,
        new_descriptor_directory: str,
    ):
        """Compares the old and new VNFD descriptors and validates the new descriptor.

        Args:
            old_descriptor_directory (str):   Directory of descriptor which is in-use
            new_descriptor_directory (str):   Directory of descriptor which is proposed to update (new revision)

        Returns:
            None

        Raises:
            EngineException:    In case of error when there are unallowed changes
        """
        try:
            # If VNFD does not exist in DB or it is not in use by any NS,
            # validation is not required.
            vnfd = self.db.get_one("vnfds", {"_id": descriptor_id})
            if not vnfd or not detect_descriptor_usage(vnfd, "vnfds", self.db):
                return

            # Get the old and new descriptor contents in order to compare them.
            with self.fs.file_open(
                (old_descriptor_directory.rstrip("/"), descriptor_file_name), "r"
            ) as old_descriptor_file:
                with self.fs.file_open(
                    (new_descriptor_directory.rstrip("/"), descriptor_file_name), "r"
                ) as new_descriptor_file:
                    old_content = yaml.safe_load(old_descriptor_file.read())
                    new_content = yaml.safe_load(new_descriptor_file.read())

                    # If software version has changed, we do not need to validate
                    # the differences anymore.
                    if old_content and new_content:
                        if self.find_software_version(
                            old_content
                        ) != self.find_software_version(new_content):
                            return

                        disallowed_change = DeepDiff(
                            self.remove_modifiable_items(old_content),
                            self.remove_modifiable_items(new_content),
                        )

                        if disallowed_change:
                            changed_nodes = functools.reduce(
                                lambda a, b: a + " , " + b,
                                [
                                    node.lstrip("root")
                                    for node in disallowed_change.get(
                                        "values_changed"
                                    ).keys()
                                ],
                            )

                            raise EngineException(
                                f"Error in validating new descriptor: {changed_nodes} cannot be modified, "
                                "there are disallowed changes in the vnf descriptor.",
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )
        except (
            DbException,
            AttributeError,
            IndexError,
            KeyError,
            ValueError,
        ) as e:
            raise type(e)(
                "VNF Descriptor could not be processed with error: {}.".format(e)
            )


class NsdTopic(DescriptorTopic):
    topic = "nsds"
    topic_msg = "nsd"

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def pyangbind_validation(self, item, data, force=False):
        if self._descriptor_data_is_in_old_format(data):
            raise EngineException(
                "ERROR: Unsupported descriptor format. Please, use an ETSI SOL006 descriptor.",
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        try:
            nsd_vnf_profiles = data.get("df", [{}])[0].get("vnf-profile", [])
            mynsd = etsi_nfv_nsd.etsi_nfv_nsd()
            pybindJSONDecoder.load_ietf_json(
                {"nsd": {"nsd": [data]}},
                None,
                None,
                obj=mynsd,
                path_helper=True,
                skip_unknown=force,
            )
            out = pybindJSON.dumps(mynsd, mode="ietf")
            desc_out = self._remove_envelop(yaml.safe_load(out))
            desc_out = self._remove_yang_prefixes_from_descriptor(desc_out)
            if nsd_vnf_profiles:
                desc_out["df"][0]["vnf-profile"] = nsd_vnf_profiles
            return desc_out
        except Exception as e:
            raise EngineException(
                "Error in pyangbind validation: {}".format(str(e)),
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    @staticmethod
    def _descriptor_data_is_in_old_format(data):
        return ("nsd-catalog" in data) or ("nsd:nsd-catalog" in data)

    @staticmethod
    def _remove_envelop(indata=None):
        if not indata:
            return {}
        clean_indata = indata

        if clean_indata.get("nsd"):
            clean_indata = clean_indata["nsd"]
        elif clean_indata.get("etsi-nfv-nsd:nsd"):
            clean_indata = clean_indata["etsi-nfv-nsd:nsd"]
        if clean_indata.get("nsd"):
            if (
                not isinstance(clean_indata["nsd"], list)
                or len(clean_indata["nsd"]) != 1
            ):
                raise EngineException("'nsd' must be a list of only one element")
            clean_indata = clean_indata["nsd"][0]
        return clean_indata

    def _validate_input_new(self, indata, storage_params, force=False):
        indata.pop("nsdOnboardingState", None)
        indata.pop("nsdOperationalState", None)
        indata.pop("nsdUsageState", None)

        indata.pop("links", None)

        indata = self.pyangbind_validation("nsds", indata, force)
        # Cross references validation in the descriptor
        # TODO validata that if contains cloud-init-file or charms, have artifacts _admin.storage."pkg-dir" is not none
        for vld in get_iterable(indata.get("virtual-link-desc")):
            self.validate_vld_mgmt_network_with_virtual_link_protocol_data(vld, indata)
        for fg in get_iterable(indata.get("vnffgd")):
            self.validate_vnffgd_data(fg, indata)

        self.validate_vnf_profiles_vnfd_id(indata)

        return indata

    @staticmethod
    def validate_vld_mgmt_network_with_virtual_link_protocol_data(vld, indata):
        if not vld.get("mgmt-network"):
            return
        vld_id = vld.get("id")
        for df in get_iterable(indata.get("df")):
            for vlp in get_iterable(df.get("virtual-link-profile")):
                if vld_id and vld_id == vlp.get("virtual-link-desc-id"):
                    if vlp.get("virtual-link-protocol-data"):
                        raise EngineException(
                            "Error at df[id='{}']:virtual-link-profile[id='{}']:virtual-link-"
                            "protocol-data You cannot set a virtual-link-protocol-data "
                            "when mgmt-network is True".format(df["id"], vlp["id"]),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )

    @staticmethod
    def validate_vnffgd_data(fg, indata):
        position_list = []
        all_vnf_ids = set(get_iterable(fg.get("vnf-profile-id")))
        for fgposition in get_iterable(fg.get("nfp-position-element")):
            position_list.append(fgposition["id"])

        for nfpd in get_iterable(fg.get("nfpd")):
            nfp_position = []
            for position in get_iterable(nfpd.get("position-desc-id")):
                nfp_position = position.get("nfp-position-element-id")
                if position == "nfp-position-element-id":
                    nfp_position = position.get("nfp-position-element-id")
                if nfp_position[0] not in position_list:
                    raise EngineException(
                        "Error at vnffgd nfpd[id='{}']:nfp-position-element-id='{}' "
                        "does not match any nfp-position-element".format(
                            nfpd["id"], nfp_position[0]
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

                for cp in get_iterable(position.get("cp-profile-id")):
                    for cpe in get_iterable(cp.get("constituent-profile-elements")):
                        constituent_base_element_id = cpe.get(
                            "constituent-base-element-id"
                        )
                        if (
                            constituent_base_element_id
                            and constituent_base_element_id not in all_vnf_ids
                        ):
                            raise EngineException(
                                "Error at vnffgd constituent_profile[id='{}']:vnfd-id='{}' "
                                "does not match any constituent-base-element-id".format(
                                    cpe["id"], constituent_base_element_id
                                ),
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )
                vnf_ip_list = set()
                for ma in get_iterable(position.get("match-attributes")):
                    ma_source_ip = ma.get("source-ip-address")
                    ma_dest_ip = ma.get("destination-ip-address")
                    ma_vp_id = ""
                    if ma_source_ip and ma_dest_ip:
                        if ma_source_ip == ma_dest_ip:
                            raise EngineException(
                                "Error at vnffgd match-attributes:source-ip-address and destination-ip-address should not match",
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )
                    if ma_source_ip:
                        for df in get_iterable(indata.get("df")):
                            for vp in get_iterable(df.get("vnf-profile")):
                                for vlc in get_iterable(
                                    vp.get("virtual-link-connectivity")
                                ):
                                    for cpd in get_iterable(
                                        vlc.get("constituent-cpd-id")
                                    ):
                                        vnf_ip_list.add(cpd.get("ip-address"))
                                        if ma_source_ip == cpd.get("ip-address"):
                                            ma_vp_id = vp.get("id")
                    if ma_source_ip not in vnf_ip_list:
                        raise EngineException(
                            "Error at vnffgd match-attributes:source-ip-address='{}' "
                            "does not match any ip-address".format(ma_source_ip),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )
                    if ma_dest_ip not in vnf_ip_list:
                        raise EngineException(
                            "Error at vnffgd match-attributes:destination-ip-address='{}' "
                            "does not match any ip-address".format(ma_dest_ip),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )
                    constituent_base_element_id = ma.get("constituent-base-element-id")
                    if (
                        constituent_base_element_id
                        and constituent_base_element_id not in ma_vp_id
                    ):
                        raise EngineException(
                            "Error at vnffgd match-attributes:vnfd-id='{}' "
                            "does not match source constituent-base-element-id".format(
                                constituent_base_element_id
                            ),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )

    @staticmethod
    def validate_vnf_profiles_vnfd_id(indata):
        all_vnfd_ids = set(get_iterable(indata.get("vnfd-id")))
        for df in get_iterable(indata.get("df")):
            for vnf_profile in get_iterable(df.get("vnf-profile")):
                vnfd_id = vnf_profile.get("vnfd-id")
                if vnfd_id and vnfd_id not in all_vnfd_ids:
                    raise EngineException(
                        "Error at df[id='{}']:vnf_profile[id='{}']:vnfd-id='{}' "
                        "does not match any vnfd-id".format(
                            df["id"], vnf_profile["id"], vnfd_id
                        ),
                        http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )

    def _validate_input_edit(self, indata, content, force=False):
        # not needed to validate with pyangbind becuase it will be validated at check_conflict_on_edit
        """
        indata looks as follows:
            - In the new case (conformant)
                {'nsdOperationalState': 'DISABLED', 'userDefinedData': {'id': 'string23',
                '_id': 'c6ddc544-cede-4b94-9ebe-be07b298a3c1', 'name': 'simon46'}}
            - In the old case (backwards-compatible)
                {'id': 'string23', '_id': 'c6ddc544-cede-4b94-9ebe-be07b298a3c1', 'name': 'simon46'}
        """
        if "_admin" not in indata:
            indata["_admin"] = {}

        if "nsdOperationalState" in indata:
            if indata["nsdOperationalState"] in ("ENABLED", "DISABLED"):
                indata["_admin"]["operationalState"] = indata.pop("nsdOperationalState")
            else:
                raise EngineException(
                    "State '{}' is not a valid operational state".format(
                        indata["nsdOperationalState"]
                    ),
                    http_code=HTTPStatus.BAD_REQUEST,
                )

        # In the case of user defined data, we need to put the data in the root of the object
        # to preserve current expected behaviour
        if "userDefinedData" in indata:
            data = indata.pop("userDefinedData")
            if isinstance(data, dict):
                indata["_admin"]["userDefinedData"] = data
            else:
                raise EngineException(
                    "userDefinedData should be an object, but is '{}' instead".format(
                        type(data)
                    ),
                    http_code=HTTPStatus.BAD_REQUEST,
                )
        if (
            "operationalState" in indata["_admin"]
            and content["_admin"]["operationalState"]
            == indata["_admin"]["operationalState"]
        ):
            raise EngineException(
                "nsdOperationalState already {}".format(
                    content["_admin"]["operationalState"]
                ),
                http_code=HTTPStatus.CONFLICT,
            )
        return indata

    def _check_descriptor_dependencies(self, session, descriptor):
        """
        Check that the dependent descriptors exist on a new descriptor or edition. Also checks references to vnfd
        connection points are ok
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param descriptor: descriptor to be inserted or edit
        :return: None or raises exception
        """
        if session["force"]:
            return
        vnfds_index = self._get_descriptor_constituent_vnfds_index(session, descriptor)

        # Cross references validation in the descriptor and vnfd connection point validation
        for df in get_iterable(descriptor.get("df")):
            self.validate_df_vnf_profiles_constituent_connection_points(df, vnfds_index)

    def _get_descriptor_constituent_vnfds_index(self, session, descriptor):
        vnfds_index = {}
        if descriptor.get("vnfd-id") and not session["force"]:
            for vnfd_id in get_iterable(descriptor.get("vnfd-id")):
                query_filter = self._get_project_filter(session)
                query_filter["id"] = vnfd_id
                vnf_list = self.db.get_list("vnfds", query_filter)
                if not vnf_list:
                    raise EngineException(
                        "Descriptor error at 'vnfd-id'='{}' references a non "
                        "existing vnfd".format(vnfd_id),
                        http_code=HTTPStatus.CONFLICT,
                    )
                vnfds_index[vnfd_id] = vnf_list[0]
        return vnfds_index

    @staticmethod
    def validate_df_vnf_profiles_constituent_connection_points(df, vnfds_index):
        for vnf_profile in get_iterable(df.get("vnf-profile")):
            vnfd = vnfds_index.get(vnf_profile["vnfd-id"])
            all_vnfd_ext_cpds = set()
            for ext_cpd in get_iterable(vnfd.get("ext-cpd")):
                if ext_cpd.get("id"):
                    all_vnfd_ext_cpds.add(ext_cpd.get("id"))

            for virtual_link in get_iterable(
                vnf_profile.get("virtual-link-connectivity")
            ):
                for vl_cpd in get_iterable(virtual_link.get("constituent-cpd-id")):
                    vl_cpd_id = vl_cpd.get("constituent-cpd-id")
                    if vl_cpd_id and vl_cpd_id not in all_vnfd_ext_cpds:
                        raise EngineException(
                            "Error at df[id='{}']:vnf-profile[id='{}']:virtual-link-connectivity"
                            "[virtual-link-profile-id='{}']:constituent-cpd-id='{}' references a "
                            "non existing ext-cpd:id inside vnfd '{}'".format(
                                df["id"],
                                vnf_profile["id"],
                                virtual_link["virtual-link-profile-id"],
                                vl_cpd_id,
                                vnfd["id"],
                            ),
                            http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                        )

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        final_content = super().check_conflict_on_edit(
            session, final_content, edit_content, _id
        )

        self._check_descriptor_dependencies(session, final_content)

        return final_content

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that there is not any NSR that uses this NSD. Only NSRs belonging to this project are considered. Note
        that NSD can be public and be used by other projects.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: nsd internal id
        :param db_content: The database content of the _id
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return
        descriptor = db_content
        descriptor_id = descriptor.get("id")
        if not descriptor_id:  # empty nsd not uploaded
            return

        # check NSD used by NS
        _filter = self._get_project_filter(session)
        _filter["nsd-id"] = _id
        if self.db.get_list("nsrs", _filter):
            raise EngineException(
                "There is at least one NS instance using this descriptor",
                http_code=HTTPStatus.CONFLICT,
            )

        # check NSD referenced by NST
        del _filter["nsd-id"]
        _filter["netslice-subnet.ANYINDEX.nsd-ref"] = descriptor_id
        if self.db.get_list("nsts", _filter):
            raise EngineException(
                "There is at least one NetSlice Template referencing this descriptor",
                http_code=HTTPStatus.CONFLICT,
            )

    def delete_extra(self, session, _id, db_content, not_send_msg=None):
        """
        Deletes associate file system storage (via super)
        Deletes associated vnfpkgops from database.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: server internal id
        :param db_content: The database content of the descriptor
        :return: None
        :raises: FsException in case of error while deleting associated storage
        """
        super().delete_extra(session, _id, db_content, not_send_msg)
        self.db.del_list(self.topic + "_revisions", {"_id": {"$regex": _id}})

    @staticmethod
    def extract_day12_primitives(nsd: dict) -> dict:
        """Removes the day12 primitives from the NSD descriptors

        Args:
            nsd (dict):    Descriptor as a dictionary

        Returns:
            nsd (dict):    Cleared NSD
        """
        if nsd.get("ns-configuration"):
            for key in [
                "config-primitive",
                "initial-config-primitive",
                "terminate-config-primitive",
            ]:
                nsd["ns-configuration"].pop(key, None)
        return nsd

    def remove_modifiable_items(self, nsd: dict) -> dict:
        """Removes the modifiable parts from the VNFD descriptors

        It calls different extract functions according to different update types
        to clear all the modifiable items from NSD

        Args:
            nsd (dict):  Descriptor as a dictionary

        Returns:
            nsd (dict):  Descriptor which does not include modifiable contents
        """
        while isinstance(nsd, dict) and nsd.get("nsd"):
            nsd = nsd["nsd"]
        if isinstance(nsd, list):
            nsd = nsd[0]
        nsd.pop("_admin", None)
        # If the more extractions need to be done from NSD,
        # the new extract methods could be appended to below list.
        for extract_function in [self.extract_day12_primitives]:
            nsd_temp = extract_function(nsd)
            nsd = nsd_temp
        return nsd

    def _validate_descriptor_changes(
        self,
        descriptor_id: str,
        descriptor_file_name: str,
        old_descriptor_directory: str,
        new_descriptor_directory: str,
    ):
        """Compares the old and new NSD descriptors and validates the new descriptor

        Args:
            old_descriptor_directory:   Directory of descriptor which is in-use
            new_descriptor_directory:   Directory of descriptor which is proposed to update (new revision)

        Returns:
            None

        Raises:
            EngineException:    In case of error if the changes are not allowed
        """

        try:
            # If NSD does not exist in DB, or it is not in use by any NS,
            # validation is not required.
            nsd = self.db.get_one("nsds", {"_id": descriptor_id}, fail_on_empty=False)
            if not nsd or not detect_descriptor_usage(nsd, "nsds", self.db):
                return

            # Get the old and new descriptor contents in order to compare them.
            with self.fs.file_open(
                (old_descriptor_directory.rstrip("/"), descriptor_file_name), "r"
            ) as old_descriptor_file:
                with self.fs.file_open(
                    (new_descriptor_directory.rstrip("/"), descriptor_file_name), "r"
                ) as new_descriptor_file:
                    old_content = yaml.safe_load(old_descriptor_file.read())
                    new_content = yaml.safe_load(new_descriptor_file.read())

                    if old_content and new_content:
                        disallowed_change = DeepDiff(
                            self.remove_modifiable_items(old_content),
                            self.remove_modifiable_items(new_content),
                        )

                        if disallowed_change:
                            changed_nodes = functools.reduce(
                                lambda a, b: a + ", " + b,
                                [
                                    node.lstrip("root")
                                    for node in disallowed_change.get(
                                        "values_changed"
                                    ).keys()
                                ],
                            )

                            raise EngineException(
                                f"Error in validating new descriptor: {changed_nodes} cannot be modified, "
                                "there are disallowed changes in the ns descriptor. ",
                                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                            )
        except (
            DbException,
            AttributeError,
            IndexError,
            KeyError,
            ValueError,
        ) as e:
            raise type(e)(
                "NS Descriptor could not be processed with error: {}.".format(e)
            )

    def sol005_projection(self, data):
        data["nsdOnboardingState"] = data["_admin"]["onboardingState"]
        data["nsdOperationalState"] = data["_admin"]["operationalState"]
        data["nsdUsageState"] = data["_admin"]["usageState"]

        links = {}
        links["self"] = {"href": "/nsd/v1/ns_descriptors/{}".format(data["_id"])}
        links["nsd_content"] = {
            "href": "/nsd/v1/ns_descriptors/{}/nsd_content".format(data["_id"])
        }
        data["_links"] = links

        return super().sol005_projection(data)


class NstTopic(DescriptorTopic):
    topic = "nsts"
    topic_msg = "nst"
    quota_name = "slice_templates"

    def __init__(self, db, fs, msg, auth):
        DescriptorTopic.__init__(self, db, fs, msg, auth)

    def pyangbind_validation(self, item, data, force=False):
        try:
            mynst = nst_im()
            pybindJSONDecoder.load_ietf_json(
                {"nst": [data]},
                None,
                None,
                obj=mynst,
                path_helper=True,
                skip_unknown=force,
            )
            out = pybindJSON.dumps(mynst, mode="ietf")
            desc_out = self._remove_envelop(yaml.safe_load(out))
            return desc_out
        except Exception as e:
            raise EngineException(
                "Error in pyangbind validation: {}".format(str(e)),
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

    @staticmethod
    def _remove_envelop(indata=None):
        if not indata:
            return {}
        clean_indata = indata

        if clean_indata.get("nst"):
            if (
                not isinstance(clean_indata["nst"], list)
                or len(clean_indata["nst"]) != 1
            ):
                raise EngineException("'nst' must be a list only one element")
            clean_indata = clean_indata["nst"][0]
        elif clean_indata.get("nst:nst"):
            if (
                not isinstance(clean_indata["nst:nst"], list)
                or len(clean_indata["nst:nst"]) != 1
            ):
                raise EngineException("'nst:nst' must be a list only one element")
            clean_indata = clean_indata["nst:nst"][0]
        return clean_indata

    def _validate_input_new(self, indata, storage_params, force=False):
        indata.pop("onboardingState", None)
        indata.pop("operationalState", None)
        indata.pop("usageState", None)
        indata = self.pyangbind_validation("nsts", indata, force)
        return indata.copy()

    def _check_descriptor_dependencies(self, session, descriptor):
        """
        Check that the dependent descriptors exist on a new descriptor or edition
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param descriptor: descriptor to be inserted or edit
        :return: None or raises exception
        """
        if not descriptor.get("netslice-subnet"):
            return
        for nsd in descriptor["netslice-subnet"]:
            nsd_id = nsd["nsd-ref"]
            filter_q = self._get_project_filter(session)
            filter_q["id"] = nsd_id
            if not self.db.get_list("nsds", filter_q):
                raise EngineException(
                    "Descriptor error at 'netslice-subnet':'nsd-ref'='{}' references a non "
                    "existing nsd".format(nsd_id),
                    http_code=HTTPStatus.CONFLICT,
                )

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        final_content = super().check_conflict_on_edit(
            session, final_content, edit_content, _id
        )

        self._check_descriptor_dependencies(session, final_content)
        return final_content

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that there is not any NSIR that uses this NST. Only NSIRs belonging to this project are considered. Note
        that NST can be public and be used by other projects.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: nst internal id
        :param db_content: The database content of the _id.
        :return: None or raises EngineException with the conflict
        """
        # TODO: Check this method
        if session["force"]:
            return
        # Get Network Slice Template from Database
        _filter = self._get_project_filter(session)
        _filter["_admin.nst-id"] = _id
        if self.db.get_list("nsis", _filter):
            raise EngineException(
                "there is at least one Netslice Instance using this descriptor",
                http_code=HTTPStatus.CONFLICT,
            )

    def sol005_projection(self, data):
        data["onboardingState"] = data["_admin"]["onboardingState"]
        data["operationalState"] = data["_admin"]["operationalState"]
        data["usageState"] = data["_admin"]["usageState"]

        links = {}
        links["self"] = {"href": "/nst/v1/netslice_templates/{}".format(data["_id"])}
        links["nst"] = {"href": "/nst/v1/netslice_templates/{}/nst".format(data["_id"])}
        data["_links"] = links

        return super().sol005_projection(data)


class PduTopic(BaseTopic):
    topic = "pdus"
    topic_msg = "pdu"
    quota_name = "pduds"
    schema_new = pdu_new_schema
    schema_edit = pdu_edit_schema

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)

    @staticmethod
    def format_on_new(content, project_id=None, make_public=False):
        BaseTopic.format_on_new(content, project_id=project_id, make_public=make_public)
        content["_admin"]["onboardingState"] = "CREATED"
        content["_admin"]["operationalState"] = "ENABLED"
        content["_admin"]["usageState"] = "NOT_IN_USE"

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that there is not any vnfr that uses this PDU
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: pdu internal id
        :param db_content: The database content of the _id.
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return

        _filter = self._get_project_filter(session)
        _filter["vdur.pdu-id"] = _id
        if self.db.get_list("vnfrs", _filter):
            raise EngineException(
                "There is at least one VNF instance using this PDU",
                http_code=HTTPStatus.CONFLICT,
            )


class VnfPkgOpTopic(BaseTopic):
    topic = "vnfpkgops"
    topic_msg = "vnfd"
    schema_new = vnfpkgop_new_schema
    schema_edit = None

    def __init__(self, db, fs, msg, auth):
        BaseTopic.__init__(self, db, fs, msg, auth)

    def edit(self, session, _id, indata=None, kwargs=None, content=None):
        raise EngineException(
            "Method 'edit' not allowed for topic '{}'".format(self.topic),
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

    def delete(self, session, _id, dry_run=False):
        raise EngineException(
            "Method 'delete' not allowed for topic '{}'".format(self.topic),
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

    def delete_list(self, session, filter_q=None):
        raise EngineException(
            "Method 'delete_list' not allowed for topic '{}'".format(self.topic),
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

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
             op_id: None
        """
        self._update_input_with_kwargs(indata, kwargs)
        validate_input(indata, self.schema_new)
        vnfpkg_id = indata["vnfPkgId"]
        filter_q = BaseTopic._get_project_filter(session)
        filter_q["_id"] = vnfpkg_id
        vnfd = self.db.get_one("vnfds", filter_q)
        operation = indata["lcmOperationType"]
        kdu_name = indata["kdu_name"]
        for kdu in vnfd.get("kdu", []):
            if kdu["name"] == kdu_name:
                helm_chart = kdu.get("helm-chart")
                juju_bundle = kdu.get("juju-bundle")
                break
        else:
            raise EngineException(
                "Not found vnfd[id='{}']:kdu[name='{}']".format(vnfpkg_id, kdu_name)
            )
        if helm_chart:
            indata["helm-chart"] = helm_chart
            match = fullmatch(r"([^/]*)/([^/]*)", helm_chart)
            repo_name = match.group(1) if match else None
        elif juju_bundle:
            indata["juju-bundle"] = juju_bundle
            match = fullmatch(r"([^/]*)/([^/]*)", juju_bundle)
            repo_name = match.group(1) if match else None
        else:
            raise EngineException(
                "Found neither 'helm-chart' nor 'juju-bundle' in vnfd[id='{}']:kdu[name='{}']".format(
                    vnfpkg_id, kdu_name
                )
            )
        if repo_name:
            del filter_q["_id"]
            filter_q["name"] = repo_name
            repo = self.db.get_one("k8srepos", filter_q)
            k8srepo_id = repo.get("_id")
            k8srepo_url = repo.get("url")
        else:
            k8srepo_id = None
            k8srepo_url = None
        indata["k8srepoId"] = k8srepo_id
        indata["k8srepo_url"] = k8srepo_url
        vnfpkgop_id = str(uuid4())
        vnfpkgop_desc = {
            "_id": vnfpkgop_id,
            "operationState": "PROCESSING",
            "vnfPkgId": vnfpkg_id,
            "lcmOperationType": operation,
            "isAutomaticInvocation": False,
            "isCancelPending": False,
            "operationParams": indata,
            "links": {
                "self": "/osm/vnfpkgm/v1/vnfpkg_op_occs/" + vnfpkgop_id,
                "vnfpkg": "/osm/vnfpkgm/v1/vnf_packages/" + vnfpkg_id,
            },
        }
        self.format_on_new(
            vnfpkgop_desc, session["project_id"], make_public=session["public"]
        )
        ctime = vnfpkgop_desc["_admin"]["created"]
        vnfpkgop_desc["statusEnteredTime"] = ctime
        vnfpkgop_desc["startTime"] = ctime
        self.db.create(self.topic, vnfpkgop_desc)
        rollback.append({"topic": self.topic, "_id": vnfpkgop_id})
        self.msg.write(self.topic_msg, operation, vnfpkgop_desc)
        return vnfpkgop_id, None


class NsConfigTemplateTopic(DescriptorTopic):
    topic = "ns_config_template"
    topic_msg = "nsd"
    schema_new = ns_config_template
    instantiation_params = {
        "vnf": vnf_schema,
        "vld": vld_schema,
        "additionalParamsForVnf": additional_params_for_vnf,
    }

    def __init__(self, db, fs, msg, auth):
        super().__init__(db, fs, msg, auth)

    def check_conflict_on_del(self, session, _id, db_content):
        """
        Check that there is not any NSR that uses this NS CONFIG TEMPLATE. Only NSRs belonging to this project are considered.
        :param session: contains "username", "admin", "force", "public", "project_id", "set_project"
        :param _id: ns config template internal id
        :param db_content: The database content of the _id
        :return: None or raises EngineException with the conflict
        """
        if session["force"]:
            return
        descriptor = db_content
        descriptor_id = descriptor.get("nsdId")
        if not descriptor_id:  # empty nsd not uploaded
            return

        # check NS CONFIG TEMPLATE used by NS
        ns_config_template_id = _id

        if self.db.get_list(
            "nsrs", {"instantiate_params.nsConfigTemplateId": ns_config_template_id}
        ):
            raise EngineException(
                "There is at least one NS instance using this template",
                http_code=HTTPStatus.CONFLICT,
            )

    def check_unique_template_name(self, edit_content, _id, session):
        """
        Check whether the name of the template is unique or not
        """

        if edit_content.get("name"):
            name = edit_content.get("name")
            db_content = self.db.get_one(
                "ns_config_template", {"name": name}, fail_on_empty=False
            )
            if db_content is not None:
                if db_content.get("_id") == _id:
                    if db_content.get("name") == name:
                        return
                elif db_content.get("_id") != _id:
                    raise EngineException(
                        "{} of the template already exist".format(name)
                    )
            else:
                return

    def check_conflict_on_edit(self, session, final_content, edit_content, _id):
        """
        Check the input data format
        And the edit content data too.
        """
        final_content = super().check_conflict_on_edit(
            session, final_content, edit_content, _id
        )
        db_content_id = self.db.get_one(
            "ns_config_template", {"_id": _id}, fail_on_empty=False
        )
        if not (
            db_content_id.get("name")
            and db_content_id.get("nsdId")
            and db_content_id.get("config")
        ):
            validate_input(edit_content, self.schema_new)

        try:
            for key, value in edit_content.items():
                if key == "name":
                    self.check_unique_template_name(edit_content, _id, session)
                elif key == "nsdId":
                    ns_config_template = self.db.get_one(
                        "ns_config_template", {"_id": _id}, fail_on_empty=False
                    )
                    if not ns_config_template.get("nsdId"):
                        pass
                    else:
                        raise EngineException("Nsd id cannot be edited")
                elif key == "config":
                    edit_content_param = edit_content.get("config")
                    for key, value in edit_content_param.items():
                        param = key
                        param_content = value
                        if param == "vnf":
                            for content in param_content:
                                for vdu in content.get("vdu"):
                                    if vdu.get("vim-flavor-name") and vdu.get(
                                        "vim-flavor-id"
                                    ):
                                        raise EngineException(
                                            "Instantiation parameters vim-flavor-name and vim-flavor-id are mutually exclusive"
                                        )
                        validate_input(param_content, self.instantiation_params[param])
                    final_content.update({"config": edit_content_param})
            return final_content
        except Exception as e:
            raise EngineException(
                "Error in instantiation parameters validation: {}".format(str(e)),
                http_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
