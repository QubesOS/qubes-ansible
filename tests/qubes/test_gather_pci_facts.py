from tests.qubes.ansible_test_utils import (
    run_module_qubesos_core_host_devices_facts as run_module,
)
from tests.qubes.conftest import qubes


def test_devices_pci_facts_match_actual(qubes):
    # Gather PCI facts from the module
    res = run_module({})

    facts = res["ansible_facts"]
    assert "pci_net" in facts
    assert "pci_usb" in facts
    assert "pci_audio" in facts

    # Compute the lists directly from qubes.domains["dom0"]
    net_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p02")
    ]
    usb_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p0c03")
    ]
    audio_actual = [
        f"pci:dom0:{dev.port_id}:{dev.device_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p0401")
        or repr(dev.interfaces[0]).startswith("p0403")
    ]

    # Compare sets
    assert set(facts["pci_net"]) == set(net_actual)
    assert set(facts["pci_usb"]) == set(usb_actual)
    assert set(facts["pci_audio"]) == set(audio_actual)
