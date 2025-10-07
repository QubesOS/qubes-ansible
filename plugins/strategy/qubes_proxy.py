# Copyright (C) 2025 Guillaume Chinal <guiiix@invisiblethingslab.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import fcntl
import multiprocessing
import os
import re
import shutil
import tarfile
import tempfile
import traceback
import time

from contextlib import suppress
from pathlib import Path

import qubesadmin
import yaml

from ansible import context
from ansible.executor.play_iterator import PlayIterator
from ansible.plugins.strategy.linear import (
    StrategyModule as LinearStrategyModule,
)
from ansible.utils.display import Display
from ansible.plugins.vars.host_group_vars import VarsModule
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.dumper import AnsibleDumper


display = Display()

RPC_SYS_POLICY_FILES = (
    Path("/etc/qubes/policy.d/include/admin-local-rwx"),
    Path("/etc/qubes/policy.d/include/admin-global-ro"),
)
RPC_INCLUDE_POL_FILE = Path("/etc/qubes/policy.d/include/qubes-ansible")
RPC_ANSIBLE_POL_FILE = Path("/etc/qubes/policy.d/30-qubes-ansible.policy")
DISPVM_NAME_MAXLEN = 31


def run_play_executor(iterator, play_context):
    return QubesPlayExecutor(iterator, play_context).run()


def filter_control_chars(text: bytes):
    """Filter control chars from bytes, keep only foreground colors"""
    new_buff = b""
    while len(text) > 0:
        # Allow SGR Reset
        if text[:4] == b"\x1b[0m":
            new_buff += text[:4]
            text = text[4:]
            continue

        # Allow setting foreground colors
        if (
            # starts with ESC [ ends with m
            text[:2] == b"\x1b["
            and text[6:7] == b"m"
            and
            # normal (0), bold (1)
            text[2] in (0x30, 0x31)
            and
            # comma
            text[3] == 0x3B
            and
            # 30-37
            text[4] == 0x33
            and 0x30 <= text[5] <= 0x37
        ):
            new_buff += text[:7]
            text = text[7:]
            continue

        # Filter other control chars
        current_byte = text[:1]
        if b"\040" <= current_byte <= b"\176" or current_byte in (
            b"\a",
            b"\b",
            b"\n",
            b"\r",
            b"\t",
        ):
            new_buff += current_byte
        else:
            new_buff += b"_"
        text = text[1:]
    return new_buff


class QubesPlayExecutor:
    """Run plays on a given host through its management disposable VM"""

    def __init__(self, iterator, play_context):
        self.app = qubesadmin.Qubes()
        self.host = iterator._play.hosts[0]
        self.loader = play_context._loader
        if self.loader == None:
            self.loader = DataLoader()
        self.inventory = iterator._variable_manager._inventory
        self.iterator = iterator
        self.play = iterator._play
        self.play_context = play_context
        self.variable_manager = iterator._variable_manager
        self.variable_manager._loader = self.loader

        self.dispvm_initially_running = False

        if hasattr(self.host.name, "_strip_unsafe"):
            self.host_name = self.host.name._strip_unsafe()
        else:
            self.host_name = self.host.name
        self.temp_dir = Path(
            tempfile.TemporaryDirectory(prefix="qubes-ansible-").name
        )
        self.vars_plugin = VarsModule()
        self.vm = None

    @property
    def dispvm_mgmt_name(self):
        return f"disp-mgmt-{self.host_name}"[:DISPVM_NAME_MAXLEN]

    def _add_host_vars(self):
        """Build host variables files

        We're building a file in host_vars/<host>.yaml containing current
        host variables merged from all sources (inventory, group_vars,
        host_vars, extra_vars...). This is done using the variable manager.
        """
        host_vars_dir = self.temp_dir / "host_vars"
        host_vars_dir.mkdir()
        host_vars_file_path = host_vars_dir / f"{self.host_name}.yaml"

        # We get all variable associated to the current host/play
        # merged from all sources
        all_vars = self.variable_manager.get_vars(
            play=self.play, host=self.host, include_hostvars=True
        )

        # In those vars, we got magic vars. This should not be problematic
        # as Ansible is supposed to ignore them, but we will try to remove
        # them
        # https://docs.ansible.com/ansible/latest/reference_appendices/special_variables.html
        filtered_vars = set(
            self.variable_manager._get_magic_variables(
                play=self.play, host=self.host, task=None, include_hostvars=True
            ).keys()
        ) | {
            "ansible_check_mode",
            "ansible_collection_name",
            "ansible_config_file",
            "ansible_dependent_role_names",
            "ansible_diff_mode",
            "ansible_facts",
            "ansible_forks",
            "ansible_index_var",
            "ansible_inventory_sources",
            "ansible_limit",
            "ansible_loop",
            "ansible_loop_var",
            "ansible_parent_role_names",
            "ansible_parent_role_paths",
            "ansible_play_batch",
            "ansible_play_hosts",
            "ansible_play_hosts_all",
            "ansible_play_name",
            "ansible_play_role_names",
            "ansible_playbook_python",
            "ansible_role_name",
            "ansible_role_names",
            "ansible_run_tags",
            "ansible_search_path",
            "ansible_skip_tags",
            "ansible_verbosity",
            "ansible_version",
            "group_names",
            "groups",
            "hostvars",
            "inventory_dir",
            "inventory_hostname",
            "inventory_hostname_short",
            "inventory_file",
            "omit",
            "play_hosts",
            "playbook_dir",
            "role_name",
            "role_names",
            "role_path",
            "vars",
        }

        target_vars_names = set(all_vars.keys()) - filtered_vars
        target_vars = {name: all_vars[name] for name in target_vars_names}

        if target_vars:
            with open(host_vars_file_path, "w") as host_vars_file:
                yaml.dump(
                    target_vars,
                    host_vars_file,
                    Dumper=AnsibleDumper,
                    default_flow_style=False,
                )

    def _add_play(self, play):
        """Builds the playbook that will be executed on DispVM

        :param play: current Play object

        We need to build a YAML file containing only the current play that
        will be passed to the disposable VM.

        `get_path` method from Ansible Play object is very useful for
        our needs as this returns the path to the file containing the play
        and the line at which it is declared.

        We just have to parse this YAML file starting from that line to get
        the list of remaining plays and keep only the next one (i.e. first
        of the list).
        """
        play_yaml = self._get_first_play_yaml(*play.get_path().split(":"))
        play_yaml["hosts"] = [str(self.host_name)]
        play_yaml["strategy"] = "linear"
        playbook_chunk_path = self.temp_dir / "playbook.yaml"
        with playbook_chunk_path.open("w") as playbook_chunk_file:
            yaml.dump(
                [play_yaml],
                playbook_chunk_file,
                Dumper=AnsibleDumper,
                default_flow_style=False,
            )

    def _add_inventory(self):
        """Build pseudo inventory for DispVM

        This allows to use the correct group assignments from group_vars in the DispVM
        """

        inventory_data = ""
        default_ansible_groups = ["all", "ungrouped"]

        for group in self.host.get_groups():
            if group.name in default_ansible_groups:
                continue

            # create Inventory entry per group (other vars from inventory are not supported yet)
            inventory_data += f"[{group.name}]\n{self.host}\n\n[{group.name}:vars]\nansible_connection=qubes\n\n"

        # if no group assignment, fallback to default appvms
        if not inventory_data:
            inventory_data = f"[appvms]\n{self.host}\n\n[appvms:vars]\nansible_connection=qubes\n\n"

        with open(self.temp_dir / "inventory", "w") as inventory_file:
            inventory_file.write(inventory_data)

    def _add_roles(self, play):
        """Adds play role

        :param play: current Play object

        We are using `get_roles` method from Ansible internal Play object
        to check if there are associated roles to the current play.
        If so, we can get the path to every roles directory using
        `get_role_path` method.

        Then, we just have to copy every role in a destination "roles"
        folder
        """
        dest_roles_path = self.temp_dir / "roles"
        dest_roles_path.mkdir()

        for role in play.get_roles():
            role_path = Path(role.get_role_path())
            shutil.copytree(role_path, dest_roles_path / role_path.name)

    def _add_rpc_policies(self):
        src = self.dispvm_mgmt_name
        dst = self.vm.name

        while True:
            with RPC_INCLUDE_POL_FILE.open("a+") as pol_file:
                fcntl.lockf(pol_file.fileno(), fcntl.LOCK_EX)
                try:
                    if os.fstat(pol_file.fileno()) != os.stat(
                        RPC_INCLUDE_POL_FILE
                    ):
                        continue
                except FileNotFoundError:
                    continue

                pol_file.write(f"{src} {dst} allow target=dom0\n")
                try:
                    shutil.chown(RPC_INCLUDE_POL_FILE, group="qubes")
                except PermissionError:
                    pass
            break

        while True:
            with RPC_ANSIBLE_POL_FILE.open("a+") as pol_file:
                fcntl.lockf(pol_file.fileno(), fcntl.LOCK_EX)
                try:
                    if os.fstat(pol_file.fileno()) != os.stat(
                        RPC_ANSIBLE_POL_FILE
                    ):
                        continue
                except FileNotFoundError:
                    continue

                pol_file.write(
                    f"qubes.Filecopy       * {src} {dst} allow\n"
                    f"qubes.WaitForSession * {src} {dst} allow\n"
                    f"qubes.VMShell        * {src} {dst} allow\n"
                    f"qubes.VMRootShell    * {src} {dst} allow\n"
                    f"admin.vm.List        * {src} dom0  allow\n"
                )
                try:
                    shutil.chown(RPC_ANSIBLE_POL_FILE, group="qubes")
                except PermissionError:
                    pass
            break

    @staticmethod
    def _build_ansible_args():
        args = []
        current_args = context.CLIARGS

        verbosity = current_args.get("verbosity")
        if verbosity:
            args.append(f"-{'v'*display.verbosity}")

        tags = current_args.get("tags")
        if tags:
            for tag in tags:
                args += ["-t", tag]

        skip_tags = current_args.get("skip_tags")
        if skip_tags:
            for tag in skip_tags:
                args += ["--skip-tags", tag]

        for boolean_arg in ["check", "diff", "force_handlers", "flush_cache"]:
            if current_args.get(boolean_arg):
                args.append(f"--{boolean_arg.replace('_', '-')}")

        return args

    def _build_tar(self):
        tar_file_path = self.temp_dir.parent / f"{self.temp_dir.name}.tar"
        old_path = os.getcwd()
        os.chdir(self.temp_dir)
        with tarfile.open(tar_file_path, "w") as tar_file:
            tar_file.add(".", recursive=True)
        os.chdir(old_path)
        return tar_file_path

    @staticmethod
    def _get_first_play_yaml(path, start_line):
        with open(path, "r") as playbook_file:
            return yaml.safe_load(
                "".join(playbook_file.readlines()[int(start_line) - 1 :])
            )[0]

    def _remove_rpc_policies(self):
        src = self.dispvm_mgmt_name
        dst = self.vm.name

        with RPC_INCLUDE_POL_FILE.open("a+") as pol_file:
            fcntl.lockf(pol_file.fileno(), fcntl.LOCK_EX)
            with suppress(FileNotFoundError):
                os.stat(RPC_INCLUDE_POL_FILE)
                pol_file.seek(0)
                new_file_lines = [
                    line
                    for line in pol_file.readlines()
                    if not re.match(
                        rf"^\s*{re.escape(src)}\s+{re.escape(dst)}\s+",
                        line,
                    )
                ]
            pol_file.seek(0)
            pol_file.truncate()
            pol_file.write("".join(new_file_lines))
            pol_file.flush()

        with RPC_ANSIBLE_POL_FILE.open("a+") as pol_file:
            fcntl.lockf(pol_file.fileno(), fcntl.LOCK_EX)
            with suppress(FileNotFoundError):
                pol_file.seek(0)
                os.stat(RPC_ANSIBLE_POL_FILE)
                new_file_lines = [
                    line
                    for line in pol_file.readlines()
                    if not re.match(
                        rf"^\s*\S+\s+\S+\s+{re.escape(src)}\s+",
                        line,
                    )
                ]
                pol_file.seek(0)
                pol_file.truncate()
                pol_file.write("".join(new_file_lines))
                pol_file.flush()

    def _start_mgmt_disp_vm(self):
        self.vvv("Lookup for dispvm_mgmt")
        dispvm = self.app.domains.get(self.dispvm_mgmt_name)
        self.vvv(f"Found dispvm: {dispvm}")
        if dispvm is None:
            self.vvv(f"Creating dispvm {self.dispvm_mgmt_name}")
            dispvm = self.app.add_new_vm(
                "DispVM",
                template=self.vm.management_dispvm,
                label=self.vm.management_dispvm.label,
                name=self.dispvm_mgmt_name,
            )
            dispvm.features["internal"] = True
            dispvm.features["gui"] = False
            dispvm.netvm = None
            dispvm.auto_cleanup = True
        self._dispvm_initially_running = self.vm.is_running()
        if not dispvm.is_running():
            dispvm.start()
        return dispvm

    def run(self):
        """Runs the given play on the mgmt dispvm of the host"""
        self.vvv(f"Running play {self.play}")
        self.vm = self.app.domains.get(self.host_name)
        if not self.vm:
            raise KeyError(f"Host {self.host.name} not found")
        self.vvv(f"Found VM {self.vm}")

        dispvm = self._start_mgmt_disp_vm()

        self._add_rpc_policies()
        self.temp_dir.mkdir()

        try:
            self._add_play(self.play)
            self._add_roles(self.play)
            self._add_host_vars()
            self._add_inventory()
            tar_file_path = self._build_tar()
            ansible_args = self._build_ansible_args()

            self.vvv(f"Copying {tar_file_path} to {self.vm}")
            dispvm.run_service(
                "qubes.Filecopy",
                localcmd="/usr/lib/qubes/qfile-dom0-agent {}".format(
                    tar_file_path
                ),
            ).wait()

            self.vvv(f"Running qubes.AnsibleVM on {self.vm}")
            p = dispvm.run_service("qubes.AnsibleVM")
            rpc_args = (
                tar_file_path.name
                + "\n"
                + self.host_name
                + "\n"
                + "\n".join(ansible_args)
                + "\n"
            ).encode()
            self.vvvv(f"RPC args: {rpc_args}")
            (untrusted_stdout, untrusted_stderr) = p.communicate(rpc_args)
            self.vvvv(f"stdout: {untrusted_stdout}")
            self.vvvv(f"stderr: {untrusted_stderr}")
            self.vvvv(f"return code: {p.returncode}")
            return (
                self.host,
                p.returncode,
                filter_control_chars(untrusted_stdout).decode("utf-8"),
                filter_control_chars(untrusted_stderr).decode("utf-8"),
                self.dispvm_mgmt_name,
                self.play.name,
            )

        finally:
            self._remove_rpc_policies()
            shutil.rmtree(self.temp_dir)
            if not self.dispvm_initially_running:
                dispvm.shutdown()
                while dispvm.is_running():
                    time.sleep(1)
                time.sleep(2)

    def _verbose(self, msg: str, level: int):
        getattr(display, "v" * level)(f"<{self.host_name}> {msg}")

    def v(self, msg):
        self._verbose(msg, 1)

    def vv(self, msg):
        self._verbose(msg, 2)

    def vvv(self, msg):
        self._verbose(msg, 3)

    def vvvv(self, msg):
        self._verbose(msg, 4)

    def vvvvv(self, msg):
        self._verbose(msg, 5)

    def vvvvvv(self, msg):
        self._verbose(msg, 6)


class StrategyModule(LinearStrategyModule):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_rpc_policies()

    def _new_play_iterator_with_hosts(self, iterator, play_context, hosts):
        new_play = iterator._play.copy()
        new_play.hosts = hosts
        return PlayIterator(
            inventory=self._inventory,
            play=new_play,
            play_context=play_context,
            variable_manager=self._variable_manager,
            all_vars=self._variable_manager.get_vars(play=new_play),
            start_at_done=self._tqm._start_at_done,
        )

    @staticmethod
    def _setup_rpc_policies():
        Path(RPC_INCLUDE_POL_FILE).touch()
        for policy_file in RPC_SYS_POLICY_FILES:
            policy_lines = [
                line.strip() for line in policy_file.read_text().split("\n")
            ]
            if "!include include/qubes-ansible" not in policy_lines:
                with policy_file.open("a") as policy_fd:
                    policy_fd.write("!include include/qubes-ansible\n")

    @staticmethod
    def collect_error(error):
        display.display(f"[ERROR]: {str(error)}", "red")
        display.display(
            "".join(
                traceback.format_exception(None, error, error.__traceback__)
            ),
            "red",
        )

    def collect_result(self, result_tuple):
        host, retcode, stdout, stderr, dispvm, play_name = result_tuple
        display.banner(f"QUBESOS [{dispvm}: PLAY {play_name}]")
        if stderr:
            display.display(str(stderr), "red")
        if stdout:
            display.display(str(stdout), "bright blue")
        self.qubes_results[host] = retcode

    def proxy_run(self, iterator, play_context):
        play = iterator._play
        display.vvv(
            f"<QubesOS> Running play {play} " f"with {self._tqm._forks} forks"
        )
        pool = multiprocessing.Pool(self._tqm._forks)

        self.qubes_results = {}
        for host in self._inventory.get_hosts(play.hosts):
            self.qubes_results[host] = 255

            new_iterator = self._new_play_iterator_with_hosts(
                iterator, play_context, [host]
            )
            pool.apply_async(
                run_play_executor,
                (new_iterator, play_context),
                callback=self.collect_result,
                error_callback=self.collect_error,
            )
        pool.close()
        pool.join()

        stats = self._tqm._stats
        for host, result in self.qubes_results.items():
            if result == 0:
                stats.increment("ok", host.name)
            else:
                stats.increment("failures", host.name)

        return max(self.qubes_results.values())

    def run(self, iterator, play_context):
        play = iterator._play

        target_hosts = self._inventory.get_hosts(play.hosts)
        local_hosts = [
            host for host in target_hosts if host.name == "localhost"
        ]
        retval_local_exec = self._tqm.RUN_OK

        remote_hosts = [
            host for host in target_hosts if host.name != "localhost"
        ]
        retval_remote_exec = self._tqm.RUN_OK

        if local_hosts:
            retval_local_exec = super().run(
                self._new_play_iterator_with_hosts(
                    iterator, play_context, local_hosts
                ),
                play_context,
            )

        # For other host, we need to start a disp mgmt and run the play inside
        if remote_hosts:
            retval_remote_exec = self.proxy_run(
                self._new_play_iterator_with_hosts(
                    iterator, play_context, remote_hosts
                ),
                play_context,
            )

        return max(retval_local_exec, retval_remote_exec)
