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


import sys

from ansible.plugins.callback import CallbackBase


DOCUMENTATION = r"""
name: qubesos_strategy_guard
type: aggregate
short_description: Ensures qubes_proxy is used in conjunction with qubes connection
description:
  - Stops the execution of the playbook when qubes_proxy is not used with qubes connection.
options:
  qubes_allow_insecure:
    description: Do not block playbook execution when qubes connection is used without qubes_proxy
    type: bool
    default: false
    ini:
      - section: qubesos_strategy_guard
        key: qubes_allow_insecure
    env:
      - name: QUBES_ALLOW_INSECURE
    vars:
      - name: qubes_allow_insecure
  qubes_insecure_quiet:
    description: Do not print any warning message when qubes_allow_insecure is enabled
    type: bool
    default: false
    ini:
      - section: qubesos_strategy_guard
        key: qubes_insecure_quiet
    env:
      - name: QUBES_INSECURE_QUIET
    vars:
      - name: qubes_insecure_quiet
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "qubesos_strategy_guard"

    def v2_playbook_on_play_start(self, play):
        self._play = play
        self._variable_manager = play.get_variable_manager()

    def v2_runner_on_start(self, host, task):
        if self._play.strategy == "qubes_proxy":
            return

        qubes_allow_insecure = self.get_option("qubes_allow_insecure")
        qubes_insecure_quiet = self.get_option("qubes_insecure_quiet")
        if qubes_allow_insecure and qubes_insecure_quiet:
            return

        if self._variable_manager is None:
            self._display.vvv(
                f"{self.CALLBACK_NAME}: Unable to retrieve VariableManager..."
            )
            return

        # see TaskExecutor._execute()
        current_connection = self._variable_manager.get_vars(
            play=self._play,
            host=host,
            task=task,
            include_hostvars=True,
            include_delegate_to=True,
        ).get("ansible_connection", task.connection)

        if current_connection == "qubes":
            msg = (
                '\033[22mUsing "qubes" connection plugin without "qubes_proxy" '
                "strategy is considered insecure and may lead to dom0 "
                "compromise.\n"
                "\033[22mTo fix this issue, you can add "
                "\033[1mstrategy: qubes_proxy\033[22m in your play or add the "
                'following setting in your "ansible.cfg" file:\n'
                "\033[1m[defaults]\n\033[1mstrategy=qubes_proxy\033[22m"
            )
            if self.get_option("qubes_allow_insecure"):
                self._display.warning(
                    msg + "\n\033[22mContinue at your own risk.", formatted=True
                )
            else:
                self._display.error(msg, wrap_text=False)
                sys.exit(1)
