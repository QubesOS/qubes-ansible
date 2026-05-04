import os
import pytest
import time

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_qube import (
    QubeModule,
)
from tests.qubes.conftest import qubes, vmname, Module, ModuleExitWithError


def test_lifecycle_full_create_start_shutdown_remove(qubes, vmname, request):

    request.node.mark_vm_created(vmname)

    # Create
    fake_module = Module({"state": "present", "name": vmname, "klass": "AppVM"})
    QubeModule(fake_module).run()

    assert fake_module.returned_data.get("changed")
    assert vmname in qubes.domains
    assert qubes.domains[vmname].is_halted()
    assert fake_module.returned_data["created"]

    fake_module = Module({"state": "running", "name": vmname})
    QubeModule(fake_module).run()
    assert qubes.domains[vmname].is_running()
    assert fake_module.returned_data.get("changed")

    # Shutdown
    fake_module = Module({"state": "halted", "name": vmname})
    QubeModule(fake_module).run()
    assert qubes.domains[vmname].is_halted()
    assert fake_module.returned_data.get("changed")

    # Remove
    fake_module = Module({"state": "absent", "name": vmname})
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains
    assert fake_module.returned_data.get("changed")


def test_lifecycle_create_and_absent(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    fake_module = Module({"state": "present", "name": vmname})
    QubeModule(fake_module).run()
    assert fake_module.returned_data.get("changed")
    assert vmname in qubes.domains

    # Absent
    fake_module = Module({"state": "absent", "name": vmname})
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert vmname not in qubes.domains
    assert fake_module.returned_data.get("changed")


def test_lifecycle_create_running_vm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Create
    fake_module = Module(
        {"state": "running", "name": vmname, "tags": ["a", "b"]}
    )
    QubeModule(fake_module).run()
    assert fake_module.returned_data.get("changed")
    assert vmname in qubes.domains
    vm = qubes.domains[vmname]
    assert vm.is_running()
    assert "a" in vm.tags
    assert "b" in vm.tags


def test_lifecycle_pause_and_resume(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # create and start
    fake_module = Module({"state": "running", "name": vmname})
    QubeModule(fake_module).run()
    assert fake_module.returned_data.get("changed")
    assert vmname in qubes.domains
    vm = qubes.domains[vmname]
    assert vm.get_power_state() == "Running"

    fake_module = Module({"state": "paused", "name": vmname})
    QubeModule(fake_module).run()
    assert fake_module.returned_data.get("changed")
    vm = qubes.domains[vmname]
    assert vm.get_power_state() == "Paused"

    fake_module = Module({"state": "running", "name": vmname})
    QubeModule(fake_module).run()
    assert fake_module.returned_data.get("changed")
    vm = qubes.domains[vmname]
    assert vm.get_power_state() == "Running"


def test_create_clone_vmtype_combinations(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    appvm_clone_name = f"{vmname}-appcln"
    appvm_clone_name_2 = f"{vmname}-appcln2"
    template_clone_name = f"{vmname}-tplcln"
    standalone_clone_name_1 = f"{vmname}-std"
    standalone_clone_name_2 = f"{vmname}-std-2"
    request.node.mark_vm_created(appvm_clone_name)
    request.node.mark_vm_created(appvm_clone_name_2)
    request.node.mark_vm_created(template_clone_name)
    request.node.mark_vm_created(standalone_clone_name_1)
    request.node.mark_vm_created(standalone_clone_name_2)

    # 1- create an AppVM
    fake_module = Module({"state": "present", "name": vmname, "klass": "AppVM"})
    QubeModule(fake_module).run()
    assert fake_module.returned_data["created"]

    # 2- Clone this AppVM
    fake_module = Module(
        {
            "state": "present",
            "name": appvm_clone_name,
            "klass": "AppVM",
            "clone_src": vmname,
        }
    )
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert fake_module.returned_data["created"]
    assert appvm_clone_name in qubes.domains
    assert qubes.domains[appvm_clone_name].klass == "AppVM"

    # 3- Clone a template
    fake_module = Module(
        {
            "state": "present",
            "name": template_clone_name,
            "klass": "TemplateVM",
            "clone_src": qubes.default_template,
        }
    )
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert fake_module.returned_data["created"]
    assert template_clone_name in qubes.domains
    assert qubes.domains[template_clone_name].klass == "TemplateVM"

    # 4- Create a Standalone VM from that template
    fake_module = Module(
        {
            "state": "present",
            "name": standalone_clone_name_1,
            "klass": "StandaloneVM",
            "clone_src": template_clone_name,
        }
    )
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert fake_module.returned_data["created"]
    assert standalone_clone_name_1 in qubes.domains
    assert qubes.domains[standalone_clone_name_1].klass == "StandaloneVM"

    # 5- Clone this StandaloneVM
    fake_module = Module(
        {
            "state": "present",
            "name": standalone_clone_name_2,
            "klass": "StandaloneVM",
            "clone_src": standalone_clone_name_1,
        }
    )
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert fake_module.returned_data["created"]
    assert standalone_clone_name_2 in qubes.domains
    assert qubes.domains[standalone_clone_name_2].klass == "StandaloneVM"

    # 6- Last check, we want to clone an AppVM (to the data on the private
    #    volume for example, but we want to use another template)
    fake_module = Module(
        {
            "state": "present",
            "name": appvm_clone_name_2,
            "klass": "AppVM",
            "clone_src": appvm_clone_name,
            "template": template_clone_name,
        }
    )
    QubeModule(fake_module).run()
    qubes.domains.refresh_cache(force=True)
    assert fake_module.returned_data["created"]
    assert appvm_clone_name_2 in qubes.domains
    vm = qubes.domains[appvm_clone_name_2]
    assert vm.template == qubes.domains[template_clone_name]
    assert vm.template != qubes.domains[appvm_clone_name].template


def test_volumes_list_for_standalonevm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "klass": "StandaloneVM",
            "clone_src": qubes.default_template,
            "volumes": {
                "root": {"size": 32212254720},
                "private": {"size": 10737418240, "revisions_to_keep": 123},
            },
        }
    )
    QubeModule(fake_module).run()

    vm = qubes.domains[vmname]
    assert vm.klass == "StandaloneVM"
    assert vm.volumes["root"].size == 32212254720
    assert vm.volumes["private"].size == 10737418240
    assert vm.volumes["private"].revisions_to_keep == 123

    # Resize root
    # Change revisions to keep
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "volumes": {
                "root": {
                    "size": 42949672960,
                },
                "private": {"revisions_to_keep": 2},
            },
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["diff"] == {
        "before": {
            "volumes": {
                "root": {"size": 32212254720},
                "private": {"revisions_to_keep": 123},
            }
        },
        "after": {
            "volumes": {
                "root": {"size": 42949672960},
                "private": {"revisions_to_keep": 2},
            }
        },
    }

    assert vm.volumes["root"].size == 42949672960
    assert vm.volumes["private"].revisions_to_keep == 2


def test_properties_and_features_set_and_tag_vm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"autostart": True, "debug": True, "memory": 256}
    feats = {"life": "Going on", "dummy_feature": None}
    tags = ["tag1", "tag2"]
    params = {
        "state": "present",
        "name": vmname,
        "properties": props,
        "features": feats,
        "tags": tags,
        "notes": "For your eyes only",
    }
    fake_module = Module(params)
    QubeModule(fake_module).run()

    vm = qubes.domains[vmname]
    props_new_values = fake_module.returned_data["diff"]["after"]["properties"]
    feats_new_values = fake_module.returned_data["diff"]["after"]["features"]
    tags_new_values = fake_module.returned_data["diff"]["after"]["tags"]

    assert vm.autostart is True
    assert props_new_values["autostart"] is True

    assert vm.memory is 256
    assert props_new_values["memory"] == 256

    assert vm.debug is True
    assert props_new_values["debug"] is True

    for feat, value in feats.items():
        assert vm.features.get(feat, None) == value
    assert feats_new_values["life"] == "Going on"
    assert "dummy_feature" not in feats_new_values

    for t in tags:
        assert t in vm.tags
        assert t in tags_new_values

    assert vm.get_notes() == "For your eyes only"
    assert (
        fake_module.returned_data["diff"]["after"]["notes"]
        == "For your eyes only"
    )

    # test if updating tags work
    tags = ["tag3", "tag4"]
    params = {
        "state": "present",
        "name": vmname,
        "tags": tags,
    }
    fake_module = Module(params)
    QubeModule(fake_module).run()
    for t in tags:
        assert t in qubes.domains[vmname].tags
        assert t not in fake_module.returned_data["diff"]["before"]["tags"]
        assert t in fake_module.returned_data["diff"]["after"]["tags"]

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "features": {
                "life": None,
                "dummy_feature": "set",
            },
        }
    )
    QubeModule(fake_module).run()
    assert vm.features.get("life") is None
    assert vm.features.get("dummy_feature") == "set"
    assert fake_module.returned_data["diff"]["before"]["features"] == {
        "life": "Going on",
        "dummy_feature": None,
    }
    assert fake_module.returned_data["diff"]["after"]["features"] == {
        "life": None,
        "dummy_feature": "set",
    }


def test_features_vm(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    feats = {"life": "Going on", "dummy_feature": None}
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "features": feats,
        }
    )
    QubeModule(fake_module).run()
    feats_values = fake_module.returned_data["diff"]["after"]["features"]
    assert "life" in feats_values
    assert "dummy_feature" not in feats_values
    for feat, value in feats.items():
        assert qubes.domains[vmname].features.get(feat, None) == value


def test_properties_invalid_key(qubes):
    # Unknown property should fail
    fake_module = Module(
        {
            "state": "present",
            "name": "dom0",
            "properties": {"titi": "toto"},
        }
    )

    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert "Invalid property" in fake_module.returned_data["msg"]
    else:
        pytest.fail("Module should have raised an error")


def test_properties_invalid_type(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    # Wrong type for memory
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"memory": "toto"},
        }
    )
    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert (
            "Failed to parse property value as int"
            in fake_module.returned_data["msg"]
        )
    else:
        pytest.fail("Module should have raised an error")


def test_properties_missing_netvm(qubes, vmname):
    # netvm does not exist
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"netvm": "toto"},
        }
    )
    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert (
            "Cannot set value 'toto' to property 'netvm': the qube doesn't exist"
            in fake_module.returned_data["msg"]
        )

        # Error should be raised before trying to create the qube
        assert vmname not in qubes.domains
    else:
        pytest.fail("Module should have raised an error")


def test_properties_reset_to_default_netvm(qubes, vm, netvm):
    """
    Able to reset back to default netvm without needing to mention it by name
    """
    default_netvm = vm.netvm

    # Change to non-default netvm
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"netvm": netvm.name},
        }
    )
    QubeModule(fake_module).run()

    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["netvm"]
        == "*default*"
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["netvm"]
        == netvm.name
    )

    # Ability to reset back to default netvm, whichever it is
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"netvm": "*default*"},
        }
    )
    QubeModule(fake_module).run()

    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["netvm"]
        == netvm.name
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["netvm"]
        == "*default*"
    )
    assert default_netvm != netvm

    qubes.domains.refresh_cache(force=True)
    assert qubes.domains[vm.name].netvm == default_netvm
    assert qubes.domains[vm.name].property_is_default("netvm")


def test_properties_reset_to_default_mac(qubes, vm, request):
    """
    Able to reset back to default mac
    """
    default_mac = vm.mac

    mac = "11:22:33:44:55:66"

    # Change to non-default mac
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"mac": mac},
        }
    )
    QubeModule(fake_module).run()

    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["mac"]
        == "*default*"
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["mac"] == mac
    )

    # Ability to reset back to default mac, whatever it is
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"mac": "*default*"},
        }
    )
    QubeModule(fake_module).run()

    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["mac"] == mac
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["mac"]
        == "*default*"
    )
    assert default_mac != mac

    qubes.domains.refresh_cache(force=True)
    assert qubes.domains[vm.name].mac == default_mac


def test_properties_missing_default_dispvm(qubes):
    # default_dispvm does not exist
    fake_module = Module(
        {
            "state": "present",
            "name": "dom0",
            "properties": {"default_dispvm": "toto"},
        }
    )
    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert (
            "Cannot set value 'toto' to property 'default_dispvm': the qube doesn't exist"
            in fake_module.returned_data["msg"]
        )
    else:
        pytest.fail("Module should have raised an error")


def test_properties_invalid_volume_name_for_appvm(qubes, vmname, request):
    # volume name not allowed for AppVM
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "volumes": {"root": {"size": 10}},
        }
    )
    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert (
            "Cannot change root volume config for 'AppVM"
            in fake_module.returned_data["msg"]
        )
    else:
        pytest.fail("Module should have raised an error")


def test_notes(qubes, vmname, request):
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "notes": "For your eyes only",
        }
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vmname].get_notes() == "For your eyes only"
    assert (
        fake_module.returned_data["diff"]["after"]["notes"]
        == "For your eyes only"
    )

    # The 2nd call should not change the notes
    QubeModule(fake_module).run()
    assert not fake_module.returned_data["changed"]


def test_services_aliased_to_features_only(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    services = ["clocksync", "minimal-netvm"]
    fake_module = Module(
        {"state": "present", "name": vmname, "services": services}
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["changed"]

    # And the VM should now have service.<svc> = 1 for each
    qube = qubes.domains[vmname]
    for svc in services:
        key = f"service.{svc}"
        assert key in qube.features
        assert qube.features[key] == "1"


def test_devices_strict_single_pci_assignment(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Create VM in strict mode with only one PCI device
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [port],
        }
    )
    QubeModule(fake_module).run()

    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in assigned
    ]
    assert ports_assigned == [port]


def test_devices_explicit_strict_assignment(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Create VM in strict mode with only one PCI device
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": {"strategy": "strict", "items": [port]},
        }
    )
    QubeModule(fake_module).run()

    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in assigned
    ]
    assert ports_assigned == [port]


def test_devices_strict_multiple_with_block(
    qubes, vmname, request, latest_net_ports, block_device
):
    request.node.mark_vm_created(vmname)
    # Use both PCI net devices plus the block device
    devices = [latest_net_ports[-2], latest_net_ports[-1], block_device]

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": devices,
        }
    )
    QubeModule(fake_module).run()

    qubes.domains.refresh_cache(force=True)
    pci_assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    blk_assigned = qubes.domains[vmname].devices["block"].get_assigned_devices()

    pci_ports = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in pci_assigned
    ]
    blk_ports = [
        f"block:dom0:{d.device.port_id}" if hasattr(d, "device") else d.port_id
        for d in blk_assigned
    ]
    assert set(pci_ports) == set(latest_net_ports[-2:]), "PCI ports mismatch"
    assert blk_ports == [block_device], "Block device not assigned correctly"


def test_devices_append_strategy_adds_without_removal(
    qubes, vmname, request, latest_net_ports, block_device
):
    request.node.mark_vm_created(vmname)
    first_port = latest_net_ports[-2]
    second_port = latest_net_ports[-1]

    # Initial create with first PCI port
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [first_port],
        }
    )
    QubeModule(fake_module).run()

    # Re-run with append strategy: add second PCI and block, keep first
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": {
                "strategy": "append",
                "items": [second_port, block_device],
            },
        }
    )
    QubeModule(fake_module).run()

    qubes.domains.refresh_cache(force=True)
    pci_ports = [
        (
            f"pci:dom0:{d.virtual_device.port_id}"
            if hasattr(d, "virtual_device")
            else d.port_id
        )
        for d in qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ]
    blk_ports = [
        f"block:dom0:{d.device.port_id}" if hasattr(d, "device") else d.port_id
        for d in qubes.domains[vmname].devices["block"].get_assigned_devices()
    ]

    # All three must now be present
    assert set(pci_ports) == {first_port, second_port}
    assert blk_ports == [block_device]


def test_devices_per_device_mode_and_options(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Use dict format to specify a custom mode and options
    entry = {
        "device": port,
        "mode": "required",
        "options": {"no-strict-reset": True},
    }

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [entry],
        }
    )
    QubeModule(fake_module).run()

    qubes.domains.refresh_cache(force=True)
    assigned = list(qubes.domains[vmname].devices["pci"].get_assigned_devices())
    assert len(assigned) == 1

    mode = assigned[0].mode.value
    opts = sorted(assigned[0].options or [])
    assert mode == "required"
    assert "no-strict-reset" in opts


def test_devices_strict_idempotent_sync(
    qubes, vmname, request, latest_net_ports
):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Initial assignment of a single PCI port
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [port],
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["changed"]

    # Re-run with the same device list (strict mode) — should be a no-op
    QubeModule(fake_module).run()

    # No changes on the second sync
    assert not fake_module.returned_data["changed"]

    # Verify still exactly that one port is assigned
    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        f"pci:dom0:{(d.virtual_device.port_id if hasattr(d, 'virtual_device') else d.port_id)}"
        for d in assigned
    ]
    assert ports_assigned == [port]


def test_devices_strict_unassign_all(qubes, vmname, request, latest_net_ports):
    request.node.mark_vm_created(vmname)
    ports = latest_net_ports[-2:]

    # Assign two PCI ports initially
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": ports,
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["changed"]

    qubes.domains.refresh_cache(force=True)

    # Confirm both are there
    initial = {
        f"pci:dom0:{(d.virtual_device.port_id if hasattr(d, 'virtual_device') else d.port_id)}"
        for d in qubes.domains[vmname].devices["pci"].get_assigned_devices()
    }
    assert initial == set(ports)

    # Now sync to an empty list (strict default) to remove all devices
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [],  # strict empty
        }
    )
    QubeModule(fake_module).run()

    # Should report that it changed by removing devices
    assert fake_module.returned_data["changed"]
    assert (
        len(fake_module.returned_data["diff"]["before"]["devices"]["pci"]) == 2
    )
    assert fake_module.returned_data["diff"]["after"]["devices"]["pci"] == {}

    # After removal, no PCI devices should remain assigned
    qubes.domains.refresh_cache(force=True)
    assert (
        list(qubes.domains[vmname].devices["pci"].get_assigned_devices()) == []
    )

    # And a second empty-sync is a no-op
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [],
        }
    )

    QubeModule(fake_module).run()

    assert not fake_module.returned_data["changed"]


def test_devices_unchanged(qubes, vmname, request, latest_net_ports):
    request.node.mark_vm_created(vmname)
    port = latest_net_ports[-1]

    # Initial assignment of a single PCI port
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [port],
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["changed"]

    # Re-run without devices, should not change anything
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "devices": [port],
        }
    )
    QubeModule(fake_module).run()
    # No changes on the second sync
    assert not fake_module.returned_data["changed"]

    # Verify still exactly that one port is assigned
    qubes.domains.refresh_cache(force=True)
    assigned = qubes.domains[vmname].devices["pci"].get_assigned_devices()
    ports_assigned = [
        f"pci:dom0:{(d.virtual_device.port_id if hasattr(d, 'virtual_device') else d.port_id)}"
        for d in assigned
    ]
    assert ports_assigned == [port]


def test_services_and_explicit_features_combined(qubes, vmname, request):
    request.node.mark_vm_created(vmname)

    # Predefine an arbitrary feature
    features = {"foo": "bar"}
    services = ["audio", "net"]

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "features": features,
            "services": services,
        }
    )
    QubeModule(fake_module).run()

    # The module should report 'features' was updated
    assert fake_module.returned_data["diff"]["after"]["features"] == {
        "foo": "bar",
        "service.audio": "1",
        "service.net": "1",
    }

    # VM should have both the explicit feature and the aliased ones
    qube = qubes.domains[vmname]
    # features stays intact
    assert qube.features.get("foo") == "bar"
    # services get aliased
    for svc in services:
        key = f"service.{svc}"
        assert key in qube.features
        assert qube.features[key] == "1"


def test_properties_set_kernelopts(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"kernelopts": "swiotlb=4096 foo=bar"}
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": props,
        }
    )
    QubeModule(fake_module).run()
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["kernelopts"]
        == "swiotlb=4096 foo=bar"
    )
    assert qubes.domains[vmname].kernelopts == "swiotlb=4096 foo=bar"


def test_properties_set_timeouts(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {"qrexec_timeout": 123, "shutdown_timeout": 456}
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": props,
        }
    )
    QubeModule(fake_module).run()
    assert fake_module.returned_data["diff"]["after"]["properties"] == {
        "qrexec_timeout": 123,
        "shutdown_timeout": 456,
    }
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.qrexec_timeout == 123
    assert vm.shutdown_timeout == 456


def test_properties_set_ip_ip6_and_mac(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    props = {
        "ip": "10.1.2.3",
        "ip6": "fe80::1",
        "mac": "00:11:22:33:44:55",
    }
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": props,
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["diff"]["after"]["properties"] == {
        "ip": "10.1.2.3",
        "ip6": "fe80::1",
        "mac": "00:11:22:33:44:55",
    }
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.ip == "10.1.2.3"
    assert vm.ip6 == "fe80::1"
    assert vm.mac == "00:11:22:33:44:55"


def test_properties_set_management_dispvm_and_audiovm(
    qubes, vmname, managementdvm, audiovm, request
):
    request.node.mark_vm_created(vmname)
    props = {"management_dispvm": managementdvm.name, "audiovm": audiovm.name}
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": props,
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["diff"]["after"]["properties"] == {
        "management_dispvm": managementdvm.name,
        "audiovm": audiovm.name,
    }
    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.management_dispvm == managementdvm
    assert vm.audiovm == audiovm


def test_properties_set_default_user_and_guivm(qubes, vmname, guivm, request):
    request.node.mark_vm_created(vmname)
    props = {"default_user": "alice", "guivm": guivm.name}
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": props,
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["diff"]["after"]["properties"] == {
        "default_user": "alice",
        "guivm": guivm.name,
    }

    qubes.domains.refresh_cache(force=True)
    vm = qubes.domains[vmname]
    assert vm.default_user == "alice"
    assert vm.guivm == guivm.name


def test_properties_invalid_type_for_new_properties(qubes, vmname, request):
    request.node.mark_vm_created(vmname)
    # ip must be str, not int
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"ip": 12345},
        }
    )

    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert "Invalid property value type" in fake_module.returned_data["msg"]
    else:
        pytest.fail("Module should have raised an error")

    # qrexec_timeout must be int, not str
    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"qrexec_timeout": "sixty"},
        }
    )
    try:
        QubeModule(fake_module).run()
    except ModuleExitWithError:
        assert "Invalid property value type" in fake_module.returned_data["msg"]
    else:
        pytest.fail("Module should have raised an error")


def test_change_properties_should_occur_only_when_necessary(
    vm, vmname, request
):
    request.node.mark_vm_created(vmname)
    vm.template_for_dispvms = True

    properties = {
        "audiovm": "sys-net",
        "autostart": True,
        "bootmode": "foo",
        "debug": True,
        "default_dispvm": vm.name,
        "default_user": "root",
        "kernelopts": "swiotlb=1024",
        "keyboard_layout": "es+oss+",
        "label": "blue",
        "mac": "de:ad:be:ef:ca:fe",
        "management_dispvm": vm.name,
        "maxmem": 600,
        "memory": 500,
        "netvm": "sys-net",
        "qrexec_timeout": 180,
        "shutdown_timeout": 180,
        "template_for_dispvms": True,
        "vcpus": 3,
    }

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
        }
    )
    QubeModule(fake_module).run()
    assert fake_module.returned_data["created"]

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": properties,
        }
    )
    QubeModule(fake_module).run()

    assert fake_module.returned_data["changed"]
    assert fake_module.returned_data["diff"]["before"]["properties"]
    assert fake_module.returned_data["diff"]["after"]["properties"]

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": properties,
        }
    )
    QubeModule(fake_module).run()

    assert not fake_module.returned_data["diff"]["before"]
    assert not fake_module.returned_data["diff"]["after"]

    fake_module = Module(
        {
            "state": "absent",
            "name": vmname,
        }
    )
    QubeModule(fake_module).run()


def test_set_property_to_empty_string(vm, qubes):
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"netvm": "sys-net"},
        }
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vm.name].netvm == "sys-net"

    fake_module = Module(
        {"state": "present", "name": vm.name, "properties": {"netvm": ""}}
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vm.name].netvm == None


def test_set_property_to_none(vm, qubes):
    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"netvm": "sys-net"},
        }
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vm.name].netvm == "sys-net"

    fake_module = Module(
        {"state": "present", "name": vm.name, "properties": {"netvm": None}}
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vm.name].netvm == None


def test_create_vm_which_is_its_self_dispvm(vmname, request, qubes):
    request.node.mark_vm_created(vmname)

    fake_module = Module(
        {
            "state": "present",
            "name": vmname,
            "properties": {"default_dispvm": vmname},
        }
    )
    QubeModule(fake_module).run()
    assert qubes.domains[vmname].default_dispvm == vmname


def test_setting_qube_value_to_the_same_value_than_default(vm):
    assert vm.property_is_default("autostart")
    assert vm.autostart == False

    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"autostart": False},
        }
    )
    QubeModule(fake_module).run()
    assert fake_module.returned_data["changed"]
    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["autostart"]
        == "*default*"
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["autostart"]
        == False
    )
    assert vm.autostart == False
    assert not vm.property_is_default("autostart")

    # Idempotence
    QubeModule(fake_module).run()
    assert not fake_module.returned_data["changed"]

    fake_module = Module(
        {
            "state": "present",
            "name": vm.name,
            "properties": {"autostart": "*default*"},
        }
    )
    QubeModule(fake_module).run()
    assert fake_module.returned_data["changed"]
    assert (
        fake_module.returned_data["diff"]["before"]["properties"]["autostart"]
        == False
    )
    assert (
        fake_module.returned_data["diff"]["after"]["properties"]["autostart"]
        == "*default*"
    )
    assert vm.autostart == False
    assert vm.property_is_default("autostart")
