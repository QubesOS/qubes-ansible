import os
import time

import pytest

from tests.qubes.ansible_test_utils import (
    AnsibleFailJson,
    run_module_qubesos_core_command as run_module,
)

from tests.qubes.conftest import qubes, vmname


def test_unrecognized_command():
    # Create
    with pytest.raises(AnsibleFailJson) as exc:
        run_module({"command": "foo"})
    assert "value of command must be one of" in exc.value.args[0]["msg"]


def test_lifecycle_full_create_start_shutdown_remove(qubes, vmname, request):

    request.node.mark_vm_created(vmname)

    # Create
    res = run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    assert res["created"] == vmname
    assert vmname in qubes.domains

    # Start
    run_module({"command": "start", "name": vmname})
    vm = qubes.domains[vmname]
    assert vm.is_running()

    # Shutdown
    run_module({"command": "shutdown", "name": vmname})
    time.sleep(5)
    assert vm.is_halted()

    # Remove
    run_module({"command": "remove", "name": vmname})
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains


def test_lifecycle_create_and_absent(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    assert vmname in qubes.domains

    # Absent
    run_module({"command": "remove", "name": vmname})
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains


def test_lifecycle_pause_and_resume(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    run_module({"command": "start", "name": vmname})
    time.sleep(1)

    run_module({"command": "pause", "name": vmname})
    assert qubes.domains[vmname].is_paused()

    run_module({"command": "unpause", "name": vmname})
    assert qubes.domains[vmname].is_running()

    # Clean up
    run_module({"command": "destroy", "name": vmname})
    run_module({"command": "remove", "name": vmname})


def test_lifecycle_status_reporting(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    status_params = {"command": "status", "name": vmname}

    run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    res = run_module(status_params)
    assert res["status"] == "shutdown"

    run_module({"command": "start", "name": vmname})
    res = run_module(status_params)
    assert res["status"] == "running"

    run_module({"command": "destroy", "name": vmname})
    res = run_module(status_params)
    assert res["status"] == "shutdown"
    assert qubes.domains[vmname].get_power_state() == "Halted"

    run_module({"command": "remove", "name": vmname})


def test_create_clone_vmtype_combinations(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    request.node.mark_vm_created(f"{vmname}-clone-appvm")
    # request.node.mark_vm_created(f"{vmname}-clone-templatevm")
    # request.node.mark_vm_created(f"{vmname}-clone-standalonevm")

    # Test creating / cloning from AppVM
    run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    run_module(
        {
            "command": "create",
            "name": f"{vmname}-clone-appvm",
            "template": vmname,
            "vmtype": "AppVM",
        }
    )

    assert f"{vmname}-clone-appvm" in qubes.domains

    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-templatevm", "template": vmname, "vmtype": "TemplateVM"})
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-templatevm" in qubes.domains

    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-standalonevm", "template": vmname, "vmtype": "StandaloneVM"})
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-standalonevm" in qubes.domains

    # Test creating / cloning from TemplateVM
    run_module({"command": "create", "name": vmname, "vmtype": "TemplateVM"})
    run_module(
        {
            "command": "create",
            "name": f"{vmname}-clone-appvm",
            "template": vmname,
            "vmtype": "AppVM",
        }
    )

    assert f"{vmname}-clone-appvm" in qubes.domains
    #
    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-templatevm", "template": vmname, "vmtype": "TemplateVM"})
    #
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-templatevm" in qubes.domains
    #
    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-standalonevm", "template": vmname, "vmtype": "StandaloneVM"})
    #
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-standalonevm" in qubes.domains
    #
    # # Test creating / cloning from StandaloneVM
    # run_module({"command": "create", "name": vmname, "vmtype": "StandaloneVM"})
    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-appvm", "template": vmname, "vmtype": "AppVM"})
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-appvm" in qubes.domains
    #
    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-templatevm", "template": vmname, "vmtype": "TemplateVM"})
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-templatevm" in qubes.domains
    #
    # rc, _ = run_module({"command": "create", "name": f"{vmname}-clone-standalonevm", "template": vmname, "vmtype": "StandaloneVM"})
    # assert rc == VIRT_SUCCESS
    # assert f"{vmname}-clone-standalonevm" in qubes.domains
    #
    # Cleanup
    run_module({"command": "remove", "name": f"{vmname}-clone-appvm"})
    # run_module({"state": "absent", "name": f"{vmname}-clone-templatevm"})
    # run_module({"state": "absent", "name": f"{vmname}-clone-standalonevm"})
    run_module({"command": "remove", "name": vmname})


def test_inventory_generation_and_grouping(tmp_path, qubes):
    # Use a temporary directory for inventory
    os.chdir(tmp_path)

    # Create a standalone VM (by default we don't have any)
    run_module(
        {
            "command": "create",
            "name": "teststandalone",
            "vmtype": "StandaloneVM",
            "template": "debian-13-xfce",
        }
    )

    # Collect expected VMs by class
    expected = {}
    for vm in qubes.domains.values():
        if vm.name == "dom0":
            continue
        expected.setdefault(vm.klass, []).append(vm.name)

    # Run createinventory
    res = run_module({"command": "createinventory"})
    assert res["status"] == "successful"

    inv_file = tmp_path / "inventory"
    assert inv_file.exists()
    lines = inv_file.read_text().splitlines()

    # Helper to extract section values
    def section(name):
        start = lines.index(f"[{name}]") + 1
        # find next section header
        for i, line in enumerate(lines[start:], start=start):
            if line.startswith("["):
                end = i
                break
        else:
            end = len(lines)
        return [l for l in lines[start:end] if l.strip()]

    appvms = section("appvms")
    templatevms = section("templatevms")
    standalonevms = section("standalonevms")

    assert set(appvms) == set(expected.get("AppVM", []))
    assert set(templatevms) == set(expected.get("TemplateVM", []))
    assert set(standalonevms) == set(expected.get("StandaloneVM", []))


@pytest.mark.xfail(reason="Module sets a default value for tags")
def test_removetags_errors_if_no_tags_present(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    run_module({"command": "create", "name": vmname, "vmtype": "AppVM"})
    assert vmname in qubes.domains

    # Remove tags
    with pytest.raises(AnsibleFailJson) as exc:
        run_module({"command": "removetags", "name": vmname})
    assert (
        exc.value.args[0]["msg"] == "Expected 'tags' parameter to be specified"
    )


def test_list_vms_command(vm):
    res = run_module({"command": "list_vms", "state": "shutdown"})
    assert vm.name in res["list_vms"]


def test_get_states_command(vm):
    res = run_module({"command": "get_states"})
    assert f"{vm.name} shutdown" in res["states"]
