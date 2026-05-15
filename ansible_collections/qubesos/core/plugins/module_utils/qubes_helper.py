#!/usr/bin/python3
# Copyright (c) 2017 Ansible Project
# Copyright (C) 2018 Kushal Das
# Copyright (C) 2025 Frédéric Pierret (fepitre) <frederic@invisiblethingslab.com>
# Copyright (C) 2026 Guillaume Chinal (guiiix) <guiiix@invisiblethingslab.com>
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

from contextlib import suppress

import asyncio
import time

try:
    import qubesadmin
    import qubesadmin.events.utils
    from qubesadmin.exc import (
        QubesVMNotStartedError,
        QubesTagNotFoundError,
        QubesVMError,
    )
    from qubesadmin.device_protocol import (
        VirtualDevice,
        DeviceAssignment,
        ProtocolError,
    )
except ImportError:
    qubesadmin = None
    QubesVMNotStartedError = None
    QubesTagNotFoundError = None
    QubesVMError = None


VIRT_FAILED = 1
VIRT_SUCCESS = 0
VIRT_UNAVAILABLE = 2

VIRT_STATE_NAME_MAP = {
    0: "running",
    1: "paused",
    4: "shutdown",
    5: "shutdown",
    6: "crashed",
}


class QubesHelper(object):

    def __init__(self, module):
        self.app = qubesadmin.Qubes()
        self.module = module

        if qubesadmin is None:
            module.fail_json("Failed to import the qubesadmin module.")

    def get_device_classes(self):
        """List all available device classes in dom0 (excluding 'testclass')."""
        return [c for c in self.app.list_deviceclass() if c != "testclass"]

    def find_devices_of_class(self, klass):
        """Yield the port IDs of all devices matching a given class in dom0."""
        for dev in self.app.domains["dom0"].devices["pci"]:
            if repr(dev.interfaces[0]).startswith("p" + klass):
                yield f"pci:dom0:{dev.port_id}:{dev.device_id}"

    def get_vm(self, vmname):
        """Retrieve a qube object by its name."""
        self.app.domains.refresh_cache(force=True)
        return self.app.domains[vmname]

    def __get_state(self, vmname):
        """Determine the current power state of a qube."""
        vm = self.app.domains[vmname]
        if vm.is_paused():
            return "paused"
        if vm.is_running():
            return "running"
        if vm.is_halted():
            return "shutdown"
        return None

    def get_states(self):
        """Get the names and states of all qubes."""
        state = []
        for vm in self.app.domains:
            state.append(f"{vm.name} {self.__get_state(vm.name)}")
        return state

    def list_vms(self, state):
        """List all non-dom0 qubes that match a specified state."""
        res = []
        for vm in self.app.domains:
            if vm.name != "dom0" and state == self.__get_state(vm.name):
                res.append(vm.name)
        return res

    def all_vms(self):
        """Group all non-dom0 qubes by their VM class."""
        res = {}
        for vm in self.app.domains:
            if vm.name == "dom0":
                continue
            res.setdefault(vm.klass, []).append(vm.name)
        return res

    def info(self):
        """Gather detailed info (state, network, label) for all non-dom0 qubes."""
        info = {}
        for vm in self.app.domains:
            if vm.name == "dom0":
                continue
            info[vm.name] = {
                "state": self.__get_state(vm.name),
                "provides_network": vm.provides_network,
                "label": vm.label.name,
            }
        return info

    def shutdown(self, vmname, wait=False, force=False):
        """
        Shutdown the specified qube via the given id or name,
        optionally waiting until it halts.

        If ``force`` is True, passes ``force=True`` to
        ``qubesadmin.vm.QubesVM.shutdown`` so the shutdown proceeds
        regardless of connected domains (equivalent to
        ``qvm-shutdown --force``).
        """
        vm = self.get_vm(vmname)
        with suppress(QubesVMNotStartedError):
            vm.shutdown(force=force)

        if wait:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    asyncio.wait_for(
                        qubesadmin.events.utils.wait_for_domain_shutdown([vm]),
                        vm.shutdown_timeout,
                    )
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout: VM {vmname} did not halt within {vm.shutdown_timeout}s"
                )
        return 0

    def restart(self, vmname, wait=False, force=False):
        """
        Restart the specified qube via the given id or name
        by shutting it down (with optional wait) and then starting it.
        """
        try:
            self.shutdown(vmname, wait=wait, force=force)
        except RuntimeError:
            raise
        vm = self.get_vm(vmname)
        vm.start()
        return 0

    def pause(self, vmname):
        """Pause the specified qube via the given id or name."""
        vm = self.get_vm(vmname)
        vm.pause()
        return 0

    def unpause(self, vmname):
        """Unpause the specified qube via the given id or name."""
        vm = self.get_vm(vmname)
        vm.unpause()
        return 0

    def create(
        self,
        vmname,
        vmtype=None,
        label="red",
        template=None,
        netvm="*default*",
    ):
        """Create a new qube of the given type, label, template, and network."""
        vmtype = vmtype or "AppVM"
        template_vm = template or ""
        if netvm == "*default*":
            network_vm = qubesadmin.DEFAULT
        elif not netvm:
            network_vm = None
        else:
            network_vm = self.get_vm(netvm)

        vm = self.app.add_new_vm(vmtype, vmname, label, template=template_vm)
        vm.netvm = network_vm
        return 0

    def create_or_clone(
        self,
        vmname,
        vmtype,
        label="red",
        template=None,
        netvm="*default*",
    ):
        """Create a new qube of the given type, label, template, and network."""
        template_vm = template or ""
        if netvm == "*default*":
            network_vm = qubesadmin.DEFAULT
        elif not netvm:
            network_vm = None
        else:
            network_vm = self.get_vm(netvm)
        if vmtype == "AppVM":
            if template_vm and self.get_vm(template_vm)._klass == vmtype:
                vm = self.app.clone_vm(
                    template_vm, vmname, vmtype, ignore_devices=True
                )
            else:
                vm = self.app.add_new_vm(
                    vmtype, vmname, label, template=template_vm
                )
            vm.netvm = network_vm
        elif vmtype in ["StandaloneVM", "TemplateVM"] and template_vm:
            vm = self.app.clone_vm(
                template_vm, vmname, vmtype, ignore_devices=True
            )
            vm.label = label
        elif vmtype == "DispVM" and template_vm:
            vm = self.app.add_new_vm(
                vmtype, vmname, label, template=template_vm
            )
            vm.netvm = network_vm
        return 0

    def start(self, vmname):
        """Start the specified qube via the given id or name"""
        vm = self.get_vm(vmname)
        vm.start()
        return 0

    def destroy(self, vmname):
        """Immediately kill the specified qube via the given id or name (no graceful shutdown)."""
        vm = self.get_vm(vmname)
        vm.kill()
        return 0

    def properties(self, vmname, prefs):
        """Sets the given properties to the qube"""
        changed = False
        values_changed = []
        vm = self.get_vm(vmname)

        # VM-reference properties
        vm_ref_keys = [
            "audiovm",
            "default_dispvm",
            "default_user",
            "guivm",
            "management_dispvm",
            "netvm",
            "template",
        ]

        for key, val in prefs.items():
            # use of `features` nested in properties is legacy use. Drop by 2030
            if key == "features":
                if self.features(vmname, val):
                    changed = True
                    if "features" not in values_changed:
                        values_changed.append("features")

            elif key == "services":
                for svc in val:
                    feat = f"service.{svc}"
                    if vm.features.get(feat) != "1":
                        vm.features[feat] = "1"
                        changed = True
                if changed and "features" not in values_changed:
                    values_changed.append("features")

            elif key == "volumes":
                for vol in prefs.get("volumes", []):
                    try:
                        volume = vm.volumes[vol["name"]]
                        volume.resize(vol["size"])
                    except Exception:
                        return VIRT_FAILED, {
                            "Failure in updating volume": vol["name"]
                        }
                    changed = True
                    values_changed.append(f"volume:{vol["name"]}")

            else:
                # determine new value or default
                if val in (None, ""):
                    new_val = ""
                elif val == "*default*":
                    new_val = qubesadmin.DEFAULT
                else:
                    new_val = val
                # check and apply change
                if new_val is qubesadmin.DEFAULT:
                    if not vm.property_is_default(key):
                        setattr(vm, key, new_val)
                        changed = True
                        values_changed.append(key)
                else:
                    if getattr(vm, key) != new_val:
                        setattr(vm, key, new_val)
                        changed = True
                        values_changed.append(key)

        return changed, values_changed

    def remove(self, vmname):
        """Destroy and then delete a qube's configuration and disk."""
        try:
            self.destroy(vmname)
        except QubesVMNotStartedError:
            pass
        while True:
            if self.__get_state(vmname) == "shutdown":
                break
            time.sleep(1)
        del self.app.domains[vmname]
        return 0

    def status(self, vmname):
        """
        Return a state suitable for server consumption.  Aka, codes.py values, not XM output.
        """
        return self.__get_state(vmname)

    def parse_device(self, spec):
        """Parse a device specification string into its class and VirtualDevice."""
        parts = spec.split(":", 1)
        if len(parts) != 2:
            self.module.fail_json(msg=f"Invalid spec {spec}")
        devclass, rest = parts
        if devclass not in self.get_device_classes():
            self.module.fail_json(msg=f"Invalid devclass {devclass}")
        try:
            device = VirtualDevice.from_str(rest, devclass, self.app.domains)
            return devclass, device
        except Exception as e:
            self.module.fail_json(msg=f"Cannot parse device {spec}: {e}")
            return None

    def list_assigned_devices(self, vmname, devclass):
        """List currently assigned devices of a given class for a qube."""
        vm = self.get_vm(vmname)
        current = {}
        for ass in vm.devices[devclass].get_assigned_devices():
            # get the VirtualDevice
            d = getattr(ass, "virtual_device", None) or ass.device
            spec = f"{devclass}:{d.backend_domain}:{d.port_id}:{d.device_id}"
            mode = getattr(ass, "mode", None)
            opts = getattr(ass, "options", None) or {}
            current[spec] = (mode, opts)
        return current

    def assign(self, vmname, devclass, device_assignment):
        """Assign a device to the specified qube."""
        vm = self.get_vm(vmname)
        vm.devices[devclass].assign(device_assignment)
        return 0

    def unassign(self, vmname, devclass, device_assignment):
        """Remove an assigned device from the specified qube."""
        vm = self.get_vm(vmname)
        vm.devices[devclass].unassign(device_assignment)
        return 0

    def sync_devices(self, vmname, devclass, desired):
        """Synchronize a qube's device assignments to match the desired configuration."""
        # build desired map: spec -> (vd, per_mode, opts)
        desired_map = {
            f"{devclass}:{vd.backend_domain}:{vd.port_id}:{vd.device_id}": (
                vd,
                per_mode,
                opts or {},
            )
            for vd, per_mode, opts in (desired or [])
        }

        changed = False

        # current assignments: spec -> (mode, opts)
        current_map = self.list_assigned_devices(vmname, devclass)
        current_specs = set(current_map)
        desired_specs = set(desired_map)

        # 1) Unassign anything not in desired
        for spec in current_specs - desired_specs:
            cls, dev = self.parse_device(spec)
            self.unassign(
                vmname,
                cls,
                DeviceAssignment(dev, frontend_domain=self.get_vm(vmname)),
            )
            changed = True

        # 2) Reassign anything whose mode or options differ
        for spec in current_specs & desired_specs:
            existing_mode, existing_opts = current_map[spec]
            vd, per_mode, opts = desired_map[spec]
            # normalize desired_mode
            desired_mode = per_mode or (
                "required" if devclass == "pci" else "auto-attach"
            )
            if existing_mode.value != desired_mode or existing_opts != opts:
                # tear down the old and set up the new
                cls, dev = self.parse_device(spec)
                self.unassign(
                    vmname,
                    cls,
                    DeviceAssignment(dev, frontend_domain=self.get_vm(vmname)),
                )
                self.assign(
                    vmname,
                    devclass,
                    DeviceAssignment(vd, mode=desired_mode, options=opts),
                )
                changed = True

        # 3) Assign any new specs
        for spec in desired_specs - current_specs:
            vd, per_mode, opts = desired_map[spec]
            assign_mode = per_mode or (
                "required" if devclass == "pci" else "auto-attach"
            )
            self.assign(
                vmname,
                devclass,
                DeviceAssignment(vd, mode=assign_mode, options=opts),
            )
            changed = True

        return changed
