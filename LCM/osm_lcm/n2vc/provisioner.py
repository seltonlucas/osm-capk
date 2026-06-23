# Copyright 2019 Canonical Ltd.
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
import logging
import os
import re
from subprocess import CalledProcessError
import tempfile
import uuid

from juju.client import client
import asyncio

arches = [
    [re.compile(r"amd64|x86_64"), "amd64"],
    [re.compile(r"i?[3-9]86"), "i386"],
    [re.compile(r"(arm$)|(armv.*)"), "armhf"],
    [re.compile(r"aarch64"), "arm64"],
    [re.compile(r"ppc64|ppc64el|ppc64le"), "ppc64el"],
    [re.compile(r"s390x?"), "s390x"],
]


def normalize_arch(rawArch):
    """Normalize the architecture string."""
    for arch in arches:
        if arch[0].match(rawArch):
            return arch[1]


DETECTION_SCRIPT = """#!/bin/bash
set -e
os_id=$(grep '^ID=' /etc/os-release | tr -d '"' | cut -d= -f2)
if [ "$os_id" = 'centos' ] || [ "$os_id" = 'rhel' ] ; then
  os_version=$(grep '^VERSION_ID=' /etc/os-release | tr -d '"' | cut -d= -f2)
  echo "$os_id$os_version"
else
  lsb_release -cs
fi
uname -m
grep MemTotal /proc/meminfo
cat /proc/cpuinfo
"""

INITIALIZE_UBUNTU_SCRIPT = """set -e
(id ubuntu &> /dev/null) || useradd -m ubuntu -s /bin/bash
umask 0077
temp=$(mktemp)
echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > $temp
install -m 0440 $temp /etc/sudoers.d/90-juju-ubuntu
rm $temp
su ubuntu -c '[ -f ~/.ssh/authorized_keys ] || install -D -m 0600 /dev/null ~/.ssh/authorized_keys'
export authorized_keys="{}"
if [ ! -z "$authorized_keys" ]; then
    su ubuntu -c 'echo $authorized_keys >> ~/.ssh/authorized_keys'
fi
"""

IPTABLES_SCRIPT = """#!/bin/bash
set -e
[ -v `which netfilter-persistent` ] && apt update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -yqq iptables-persistent
iptables -t nat -A OUTPUT -p tcp -d {} -j DNAT --to-destination {}
netfilter-persistent save
"""

IPTABLES_SCRIPT_RHEL = """#!/bin/bash
set -e
[ -v `which firewalld` ] && yum install -q -y firewalld
systemctl is-active --quiet firewalld || systemctl start firewalld \
    && firewall-cmd --permanent --zone=public --set-target=ACCEPT
systemctl is-enabled --quiet firewalld || systemctl enable firewalld
firewall-cmd --direct --permanent --add-rule ipv4 nat OUTPUT 0 -d {} -p tcp \
    -j DNAT --to-destination {}
firewall-cmd --reload
"""

CLOUD_INIT_WAIT_SCRIPT = """#!/bin/bash
set -e
cloud-init status --wait
"""


class AsyncSSHProvisioner:
    """Provision a manually created machine via SSH."""

    user = ""
    host = ""
    private_key_path = ""

    def __init__(self, user, host, private_key_path, log=None):
        self.host = host
        self.user = user
        self.private_key_path = private_key_path
        self.log = log if log else logging.getLogger(__name__)

    async def _scp(self, source_file, destination_file):
        """Execute an scp command. Requires a fully qualified source and
        destination.

        :param str source_file: Path to the source file
        :param str destination_file: Path to the destination file
        """
        cmd = [
            "scp",
            "-i",
            os.path.expanduser(self.private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-q",
            "-B",
        ]
        destination = "{}@{}:{}".format(self.user, self.host, destination_file)
        cmd.extend([source_file, destination])
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        if process.returncode != 0:
            raise CalledProcessError(returncode=process.returncode, cmd=cmd)

    async def _ssh(self, command):
        """Run a command remotely via SSH.

        :param str command: The command to execute
        :return: tuple: The stdout and stderr of the command execution
        :raises: :class:`CalledProcessError` if the command fails
        """

        destination = "{}@{}".format(self.user, self.host)
        cmd = [
            "ssh",
            "-i",
            os.path.expanduser(self.private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-q",
            destination,
        ]
        cmd.extend([command])
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            output = stderr.decode("utf-8").strip()
            raise CalledProcessError(
                returncode=process.returncode, cmd=cmd, output=output
            )
        return (stdout.decode("utf-8").strip(), stderr.decode("utf-8").strip())

    async def _init_ubuntu_user(self):
        """Initialize the ubuntu user.

        :return: bool: If the initialization was successful
        :raises: :class:`CalledProcessError` if the _ssh command fails
        """
        retry = 10
        attempts = 0
        delay = 15
        while attempts <= retry:
            try:
                attempts += 1
                # Attempt to establish a SSH connection
                stdout, stderr = await self._ssh("sudo -n true")
                break
            except CalledProcessError as e:
                self.log.debug(
                    "Waiting for VM to boot, sleeping {} seconds".format(delay)
                )
                if attempts > retry:
                    raise e
                else:
                    await asyncio.sleep(delay)
                    # Slowly back off the retry
                    delay += 15

        # Infer the public key
        public_key = None
        public_key_path = "{}.pub".format(self.private_key_path)

        if not os.path.exists(public_key_path):
            raise FileNotFoundError(
                "Public key '{}' doesn't exist.".format(public_key_path)
            )

        with open(public_key_path, "r") as f:
            public_key = f.readline()

        script = INITIALIZE_UBUNTU_SCRIPT.format(public_key)

        stdout, stderr = await self._run_configure_script(script)

        return True

    async def _detect_hardware_and_os(self):
        """Detect the target hardware capabilities and OS series.

        :return: str: A raw string containing OS and hardware information.
        """

        info = {
            "series": "",
            "arch": "",
            "cpu-cores": "",
            "mem": "",
        }

        stdout, stderr = await self._run_configure_script(DETECTION_SCRIPT)

        lines = stdout.split("\n")
        info["series"] = lines[0].strip()
        info["arch"] = normalize_arch(lines[1].strip())

        memKb = re.split(r"\s+", lines[2])[1]

        # Convert megabytes -> kilobytes
        info["mem"] = round(int(memKb) / 1024)

        # Detect available CPUs
        recorded = {}
        for line in lines[3:]:
            physical_id = ""
            print(line)

            if line.find("physical id") == 0:
                physical_id = line.split(":")[1].strip()
            elif line.find("cpu cores") == 0:
                cores = line.split(":")[1].strip()

                if physical_id not in recorded.keys():
                    info["cpu-cores"] += cores
                    recorded[physical_id] = True

        return info

    async def provision_machine(self):
        """Perform the initial provisioning of the target machine.

        :return: bool: The client.AddMachineParams
        """
        params = client.AddMachineParams()

        if await self._init_ubuntu_user():
            hw = await self._detect_hardware_and_os()
            params.series = hw["series"]
            params.instance_id = "manual:{}".format(self.host)
            params.nonce = "manual:{}:{}".format(
                self.host,
                str(uuid.uuid4()),
            )  # a nop for Juju w/manual machines
            params.hardware_characteristics = {
                "arch": hw["arch"],
                "mem": int(hw["mem"]),
                "cpu-cores": int(hw["cpu-cores"]),
            }
            params.addresses = [{"value": self.host, "type": "ipv4", "scope": "public"}]

        return params

    async def install_agent(
        self, connection, nonce, machine_id, proxy=None, series=None
    ):
        """
        :param object connection: Connection to Juju API
        :param str nonce: The nonce machine specification
        :param str machine_id: The id assigned to the machine
        :param str proxy: IP of the API_PROXY
        :param str series: OS name

        :return: bool: If the initialization was successful
        """
        # The path where the Juju agent should be installed.
        data_dir = "/var/lib/juju"

        # Disabling this prevents `apt-get update` from running initially, so
        # charms will fail to deploy
        disable_package_commands = False

        client_facade = client.ClientFacade.from_connection(connection)
        results = await client_facade.ProvisioningScript(
            data_dir=data_dir,
            disable_package_commands=disable_package_commands,
            machine_id=machine_id,
            nonce=nonce,
        )

        """Get the IP of the controller

        Parse the provisioning script, looking for the first apiaddress.

        Example:
            apiaddresses:
            - 10.195.8.2:17070
            - 127.0.0.1:17070
            - '[::1]:17070'
        """
        try:
            # Wait until cloud-init finish
            await self._run_configure_script(CLOUD_INIT_WAIT_SCRIPT)
        except Exception:
            self.log.debug("cloud-init not present in machine {}".format(machine_id))

        if proxy:
            m = re.search(
                r"apiaddresses:\n- (\d+\.\d+\.\d+\.\d+):17070", results.script
            )
            apiaddress = m.group(1)

            """Add IP Table rule

            In order to route the traffic to the private ip of the Juju controller
            we use a DNAT rule to tell the machine that the destination for the
            private address is the public address of the machine where the Juju
            controller is running in LXD. That machine will have a complimentary
            iptables rule, routing traffic to the appropriate LXD container.
            """

            if series and ("centos" in series or "rhel" in series):
                script = IPTABLES_SCRIPT_RHEL.format(apiaddress, proxy)
            else:
                script = IPTABLES_SCRIPT.format(apiaddress, proxy)

            # Run this in a retry loop, because dpkg may be running and cause the
            # script to fail.
            retry = 10
            attempts = 0
            delay = 15

            while attempts <= retry:
                try:
                    attempts += 1
                    stdout, stderr = await self._run_configure_script(script)
                    break
                except Exception as e:
                    self.log.debug(
                        "Waiting for DNAT rules to be applied and saved, "
                        "sleeping {} seconds".format(delay)
                    )
                    if attempts > retry:
                        raise e
                    else:
                        await asyncio.sleep(delay)
                        # Slowly back off the retry
                        delay += 15

        # self.log.debug("Running configure script")
        await self._run_configure_script(results.script)
        # self.log.debug("Configure script finished")

    async def _run_configure_script(self, script, root=True):
        """Run the script to install the Juju agent on the target machine.

        :param str script: The script to be executed
        """
        _, tmpFile = tempfile.mkstemp()
        with open(tmpFile, "w") as f:
            f.write(script)
            f.close()

        # copy the local copy of the script to the remote machine
        await self._scp(tmpFile, tmpFile)

        # run the provisioning script
        return await self._ssh(
            "{} /bin/bash {}".format("sudo" if root else "", tmpFile)
        )
