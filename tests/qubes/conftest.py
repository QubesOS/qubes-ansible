import uuid

import pytest
import qubesadmin

from plugins.modules.qubesos import core


# Helper to run the module core function
class Module:
    def __init__(self, params):
        self.params = params

    def fail_json(self, **kwargs):
        pytest.fail(f"Module failed: {kwargs}")

    def exit_json(self, **kwargs):
        return


@pytest.fixture(scope="function")
def qubes():
    """Return a Qubes app instance"""
    try:
        return qubesadmin.Qubes()
    except Exception as e:
        pytest.skip(f"Qubes API not available: {e}")


@pytest.fixture(scope="function")
def vmname():
    """Generate a random VM name for testing"""
    return f"test-vm-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def vm(qubes, request):
    """Generate a VM with default configurations"""
    vmname = f"test-vm-{uuid.uuid4().hex[:8]}"
    core(Module({"state": "present", "name": vmname}))
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def minimalvm(qubes, request):
    vmname = f"test-minimalvm-{uuid.uuid4().hex[:8]}"
    props = {"template": "debian-12-minimal"}
    core(Module({"state": "present", "name": vmname, "properties": props}))
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(scope="function")
def netvm(qubes, request):
    vmname = f"test-netvm-{uuid.uuid4().hex[:8]}"
    props = {"provides_network": True}
    core(Module({"state": "present", "name": vmname, "properties": props}))
    request.node.mark_vm_created(vmname)

    qubes.domains.refresh_cache(force=True)
    return qubes.domains[vmname]


@pytest.fixture(autouse=True)
def cleanup_vm(qubes, request):
    """Ensure any test VM is removed after test"""
    created = []

    def mark(name):
        created.append(name)

    request.node.mark_vm_created = mark
    yield
    # Teardown (remove VMs)
    for name in created:
        try:
            core(Module({"command": "remove", "name": name}))
        except Exception:
            pass


@pytest.fixture
def latest_net_ports(qubes):
    # Collect all net‐class PCI port_ids from dom0
    # See fepitre/qubes-g2g-continuous-integration
    ports = [
        f"pci:dom0:{dev.port_id}"
        for dev in qubes.domains["dom0"].devices["pci"]
        if repr(dev.interfaces[0]).startswith("p02")
    ]
    assert len(ports) >= 2, "Need at least two PCI net devices for these tests"
    return ports


@pytest.fixture
def block_device():
    # Assume the block device under test is always present
    # See fepitre/qubes-g2g-continuous-integration
    return "block:dom0:vdb"
