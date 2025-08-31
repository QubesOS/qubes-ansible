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

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'qubesos_strategy_guard'

    def v2_playbook_on_play_start(self, play):
        self._play = play

    def v2_runner_on_start(self, host, task):
        if self._play.strategy == "qubes_proxy":
            return

        if task._variable_manager is None:
            return

        task_connection = task._variable_manager.get_vars(
                play=self._play,
                host=host,
                task=task,
                include_hostvars=True,
                include_delegate_to=True
        ).get('ansible_connection')

        if task_connection == "qubes":
            self._display.warning(
                "Using qubes connection plugin without qubes_proxy strategy is "
                "considered insecure and may lead to dom0 compromise. Continue "
                "at your own risk.")
