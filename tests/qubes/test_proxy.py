import pytest
import shutil
import subprocess
import yaml

from configparser import ConfigParser
from pathlib import Path
from typing import List, Optional

from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.plugins.loader import strategy_loader
from ansible.vars.manager import VariableManager
from ansible import context
from ansible.plugins.strategy.linear import (
    StrategyModule as LinearStrategyModule,
)
from unittest.mock import Mock


PLUGIN_PATH = Path(__file__).parent.parent / "plugins" / "modules"


class ResultsCollectorJSONCallback(CallbackBase):
    """A sample callback plugin used for performing an action as results come in.

    If you want to collect all results into a single object for processing at
    the end of the execution, look into utilizing the ``json`` callback plugin
    or writing your own custom callback plugin.
    """

    def __init__(self, *args, **kwargs):
        super(ResultsCollectorJSONCallback, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        host = result._host
        self.host_unreachable[host.get_name()] = result

    def v2_runner_on_ok(self, result, *args, **kwargs):
        host = result._host
        self.host_ok[host.get_name()] = result

    def v2_runner_on_failed(self, result, *args, **kwargs):
        host = result._host
        self.host_failed[host.get_name()] = result


@pytest.fixture
def run_playbook(tmp_path):

    def _run(
        playbook: dict,
        inventory_format: str = "ini",
        ansible_config: str = "ansible_proxy_strategy",
        inventory: Optional[dict] = None,
        host_vars: Optional[dict] = None,
        group_vars: Optional[dict] = None,
        extra_args: Optional[List[str]] = None,
    ):

        cmd = [
            "ansible-playbook",
            "-M",
            str(PLUGIN_PATH),
        ]

        shutil.copy(
            Path(__file__).parent.parent / f"{ansible_config}.cfg",
            tmp_path / "ansible.cfg",
        )

        if inventory:
            if inventory_format == "ini":
                inventory_path = tmp_path / "inventory"

                inventory_content = ConfigParser(allow_no_value=True)
                for section, section_content in inventory.items():
                    inventory_content.add_section(section)
                    for entry in section_content:
                        inventory_content.set(section, *entry)
                cmd += ["-i", inventory_path]

                with open(inventory_path, "w") as inventory_file:
                    inventory_content.write(
                        inventory_file, space_around_delimiters=False
                    )
            elif inventory_format == "yaml":
                inventory_path = tmp_path / "inventory.yaml"
                with open(inventory_path, "w") as inventory_file:
                    yaml.safe_dump(inventory, inventory_file)
                cmd += ["-i", inventory_path]
        else:
            cmd += ["-i", "localhost"]

        playbook_file = tmp_path / "playbook.yaml"
        playbook_file.write_text(yaml.safe_dump(playbook))

        def _write_inventory_vars(inventory_vars, dir_name):
            if inventory_vars:
                vars_dir = tmp_path / dir_name
                vars_dir.mkdir()

                for file_name, content in inventory_vars.items():
                    (vars_dir / f"{file_name}.yaml").write_text(
                        yaml.safe_dump(content)
                    )

        _write_inventory_vars(host_vars, "host_vars")
        _write_inventory_vars(group_vars, "group_vars")

        if extra_args:
            cmd += extra_args
        cmd += [playbook_file]

        result = subprocess.run(
            cmd,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        return result

    return _run


def test_proxy_with_simple_local_playbook(run_playbook):
    playbook = [{"hosts": "localhost", "tasks": [{"debug": {"msg": "foo"}}]}]
    result = run_playbook(playbook)
    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_with_target_appvm(run_playbook, vm):
    playbook = [{"hosts": vm.name, "tasks": [{"debug": {"msg": "foo"}}]}]

    inventory = {"appvms": [[vm.name]]}

    result = run_playbook(playbook, inventory=inventory)
    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_with_variables(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "tasks": [
                {
                    "fail": {"msg": "undefined var {{ item }}"},
                    "when": "lookup('vars', item) is undefined",
                    "loop": [
                        "host_var_1",
                        "host_var_2",
                        "appvm_var",
                        "my_group_var",
                    ],
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
        "appvms:vars": [["appvm_var", "foo"]],
        "my_group": [[vm.name]],
        "my_group:vars": [["my_group_var", "foo"]],
        "all": [
            [f"{vm.name} host_var_1", "foo"],
            [f"{vm.name} host_var_2", "bar"],
        ],
    }

    result = run_playbook(playbook, inventory=inventory)
    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_with_dynamic_inventory(run_playbook, vm):
    playbook = [
        {
            "hosts": "localhost",
            "tasks": [{"add_host": {"name": vm.name, "group": "my_group"}}],
        },
        {
            "hosts": vm.name,
            "tasks": [
                {
                    "fail": {"msg": "undefined var {{ item }}"},
                    "when": "lookup('vars', item) is undefined",
                    "loop": [
                        "my_group_var",
                    ],
                }
            ],
        },
    ]

    inventory = {
        "appvms": [[vm.name]],
        "appvms:vars": [["appvm_var", "foo"]],
        "my_group": [],
        "my_group:vars": [["my_group_var", "foo"]],
        "all": [
            [f"{vm.name} host_var_1", "foo"],
            [f"{vm.name} host_var_2", "bar"],
        ],
    }

    result = run_playbook(playbook, inventory=inventory)
    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_routing(monkeypatch):
    hosts = ["work", "work2", "localhost", "work3"]
    sources = ",".join(hosts)
    if len(hosts) == 1:
        sources += ","
    context.CLIARGS = ImmutableDict(
        connection="smart",
        module_path=["/to/mymodules", "/usr/share/ansible"],
        forks=10,
        become=None,
        become_method=None,
        become_user=None,
        check=False,
        diff=False,
    )
    loader = DataLoader()
    results_callback = ResultsCollectorJSONCallback()
    inventory = InventoryManager(loader=loader, sources=sources)
    variable_manager = VariableManager(loader=loader, inventory=inventory)
    tqm = TaskQueueManager(
        inventory=inventory,
        variable_manager=variable_manager,
        loader=loader,
        passwords={},
        stdout_callback=results_callback,
        # Use our custom callback instead of the ``default`` callback plugin, which prints to stdout
    )

    play_source = {
        "name": "Simple Play",
        "hosts": hosts,
        "gather_facts": "no",
        "strategy": "qubes_proxy",
        "tasks": [
            {
                "action": {
                    "module": "command",
                    "args": {"cmd": "/usr/bin/uptime"},
                }
            }
        ],
    }

    # required to be set for strategy_loader
    tqm._workers = None
    strategy = strategy_loader.get("qubes_proxy", tqm=tqm)
    assert strategy is not None

    calls = {}

    def fake_proxy_run(iterator, play_context):
        for host in iterator._play.hosts:
            calls.setdefault(str(host), 0)
            calls[str(host)] += 1
        return 0

    strategy.proxy_run = fake_proxy_run
    fake_linear_run = Mock()
    fake_linear_run.return_value = 0
    LinearStrategyModule.run = fake_linear_run

    fake_get_strategy = Mock()
    fake_get_strategy.return_value = strategy
    monkeypatch.setattr(strategy_loader, "get", fake_get_strategy)

    play = Play().load(
        play_source, variable_manager=variable_manager, loader=loader
    )
    tqm.run(play)

    assert calls == {"work": 1, "work2": 1, "work3": 1}

    fake_get_strategy.assert_called_once()
    fake_linear_run.assert_called_once()


def test_proxy_with_mixed_variables_sources(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "tasks": [
                {
                    "fail": {"msg": "undefined var {{ item }}"},
                    "when": "lookup('vars', item) is undefined",
                    "loop": [
                        "var_1",
                        "var_2",
                        "var_3",
                        "var_4",
                        "var_5",
                        "extra_var",
                    ],
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
        "appvms:vars": [["var_1", "foo"]],
        "all": [
            [f"{vm.name} var_2", "foo"],
        ],
    }

    host_vars = {
        vm.name: {"var_3": "foo"},
    }

    group_vars = {
        "appvms": {"var_4": "foo"},
        "all": {"var_5": "foo"},
    }

    result = run_playbook(
        playbook,
        inventory=inventory,
        host_vars=host_vars,
        group_vars=group_vars,
        extra_args=["-e", "extra_var=foo"],
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_yaml_inventory(run_playbook, vm):
    playbook = [
        {
            "hosts": "appvms",
            "tasks": [
                {
                    "fail": {"msg": "undefined var {{ item }}"},
                    "when": "lookup('vars', item) is undefined",
                    "loop": [
                        "host_var",
                        "group_var",
                    ],
                }
            ],
        }
    ]

    inventory = {
        "appvms": {
            "hosts": {vm.name: {"host_var": "foo"}},
            "vars": {"group_var": "foo"},
        }
    }

    result = run_playbook(
        playbook, inventory=inventory, inventory_format="yaml"
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_proxy_with_dict_in_variable(run_playbook, vm):
    playbook = [
        {
            "hosts": "appvms",
            "tasks": [
                {
                    "assert": {
                        "that": "my_dict['my_item']['my_subitem'] == 'foo'"
                    },
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
    }

    group_vars = {"appvms": {"my_dict": {"my_item": {"my_subitem": "foo"}}}}

    result = run_playbook(playbook, inventory=inventory, group_vars=group_vars)

    assert result.returncode == 0, result.stderr
    assert (
        "Could not match supplied host pattern" not in result.stderr
    ), result.stderr


def test_guard_callback_blocking_execution(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "strategy": "linear",
            "connection": "qubes",
            "tasks": [
                {
                    "command": {"args": "whoami"},
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
    }

    result = run_playbook(playbook, inventory=inventory)

    assert result.returncode == 1, result.stderr
    assert "ERROR" in result.stderr
    assert (
        "is considered insecure and may lead to dom0 compromise."
        in result.stderr
    )


def test_guard_callback_warning(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "strategy": "linear",
            "connection": "qubes",
            "tasks": [
                {
                    "command": "whoami",
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
    }

    result = run_playbook(
        playbook, inventory=inventory, ansible_config="ansible_guard_off"
    )

    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stderr
    assert (
        "is considered insecure and may lead to dom0 compromise."
        in result.stderr
    )


def test_guard_callback_quiet(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "strategy": "linear",
            "connection": "qubes",
            "tasks": [
                {
                    "command": "whoami",
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
    }

    result = run_playbook(
        playbook, inventory=inventory, ansible_config="ansible_guard_quiet"
    )

    assert result.returncode == 0, result.stderr
    assert (
        "is considered insecure and may lead to dom0 compromise."
        not in result.stderr
    )


def test_guard_callback_connection_setting_in_hostvars(run_playbook, vm):
    playbook = [
        {
            "hosts": vm.name,
            "strategy": "linear",
            "connection": "ssh",
            "tasks": [
                {
                    "command": "whoami",
                }
            ],
        }
    ]

    inventory = {
        "appvms": [[vm.name]],
    }

    host_vars = {vm.name: {"ansible_connection": "qubes"}}

    result = run_playbook(
        playbook,
        inventory=inventory,
        host_vars=host_vars,
    )

    assert result.returncode == 1, result.stderr
    assert (
        "is considered insecure and may lead to dom0 compromise."
        in result.stderr
    )
