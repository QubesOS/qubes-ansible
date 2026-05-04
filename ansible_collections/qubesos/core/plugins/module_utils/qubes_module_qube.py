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

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.qubesos.core.plugins.module_utils.qubes_helper import (
    QubesHelper,
)

from typing import List, Optional

from dataclasses import dataclass
from qubesadmin.vm import QubesVM

try:
    import qubesadmin
    import qubesadmin.exc
    from qubesadmin.device_protocol import DeviceAssignment, AssignmentMode
except ImportError:
    qubesadmin = None


@dataclass
class QubesWants:
    clone_src: Optional[str]
    devices: Optional[dict | list]
    features: Optional[dict]
    notes: Optional[str]
    properties: Optional[dict]
    services: Optional[list]
    state: str
    tags: Optional[List[str]]
    template: Optional[str]
    klass: Optional[str]
    volumes: Optional[dict]

    def __post_init__(self):
        """Set empty list / dict for a couple of params if their value is None"""
        for attribute in [
            "features",
            "properties",
            "volumes",
        ]:
            if getattr(self, attribute) is None:
                setattr(self, attribute, {})

        for attribute in [
            "tags",
        ]:
            if getattr(self, attribute) is None:
                setattr(self, attribute, [])


class QubeModule:
    def __init__(self, module: AnsibleModule):
        self.module = module
        self.qube_name = module.params.get("name")
        self.changed = False
        self.created = False
        self.deleted = False
        self.diff = {"before": {}, "after": {}}
        self.helper = QubesHelper(module)
        self.qube: QubesVM = self.helper.app.domains.get(self.qube_name)
        self.shutdown_if_required = module.params.get("shutdown_if_required")
        self.devices_set_mode = None

        wanted_state = module.params.get("state")
        # Normalize state to
        # - absent
        # - halted
        # - paused
        # - present
        # - restarted
        # - running
        if wanted_state in ["destroyed", "shutdown"]:
            wanted_state = "halted"
        elif wanted_state == "pause":
            wanted_state = "paused"

        self.wants = QubesWants(
            clone_src=module.params.get("clone_src"),
            devices=module.params.get("devices"),
            features=module.params.get("features"),
            notes=module.params.get("notes"),
            properties=module.params.get("properties"),
            state=wanted_state,
            services=module.params.get("services"),
            tags=module.params.get("tags"),
            template=module.params.get("template"),
            volumes=module.params.get("volumes"),
            klass=module.params.get("klass"),
        )

        if self.wants.properties is None:
            self.wants.properties = {}

        # Sync template var with template key in properties var
        # No template property for TemplateVMs and StandaloneVMs
        if self.wants.klass not in ("TemplateVM", "StandaloneVM"):
            if self.wants.template:
                self.wants.properties["template"] = self.wants.template
            elif "template" in self.wants.properties:
                self.wants.template = self.wants.properties["template"]

    def _shutdown_for_template_update(self):
        """Change the template if required, raise an error if the qube is running and cannot be stopped"""
        if self.wants.klass == "StandaloneVM":
            return

        if (
            self.wants.template is not None
            and self.wants.template != self.qube.template
        ):
            if not self.qube.is_halted():
                # We need to shutdown the qube before updating its template
                # `shutdown_if_required` module params allows us stop it
                # if necessary
                if self.shutdown_if_required:
                    self.helper.shutdown(self.qube_name, wait=True)
                else:
                    self.module.fail_json(
                        msg="Cannot change the template while the qube is running"
                    )

    def enforce_all(self):
        self.enforce_properties()
        self.enforce_volumes()
        self.enforce_devices()
        self.enforce_features()
        self.enforce_notes()
        self.enforce_tags()
        self.enforce_state()

    def _enforce_device_class_strict_mode(self, device_class, wants) -> bool:
        return self.helper.sync_devices(self.qube_name, device_class, wants)

    def _enforce_device_class_append_mode(self, device_class, wants) -> bool:
        current_map = self.helper.list_assigned_devices(
            self.qube_name, device_class
        )
        changed = False
        for vd, per_mode, opts in wants:
            spec = f"{device_class}:{vd.backend_domain}:{vd.port_id}:{vd.device_id}"
            if spec in current_map:
                # already present -> leave it (no mode/options change in append mode)
                continue
            # new device -> assign with its mode/options
            assign_mode = per_mode or (
                "required" if device_class == "pci" else "auto-attach"
            )
            self.helper.assign(
                self.qube_name,
                device_class,
                DeviceAssignment(vd, mode=assign_mode, options=opts),
            )
            changed = True
        return changed

    def _list_all_assigned_devices(self):
        return {
            device_class: self.helper.list_assigned_devices(
                self.qube_name, device_class
            )
            for device_class in self.helper.get_device_classes()
        }

    def enforce_devices(self):
        def compute_devices_list():
            return {
                str(dev_type): {
                    str(dev): (
                        str(dev_conf[0].value)
                        if isinstance(dev_conf[0], AssignmentMode)
                        else str(dev_conf[0])
                    )
                    for dev, dev_conf in dev_list.items()
                }
                for dev_type, dev_list in self._list_all_assigned_devices().items()
            }

        if self.wants.devices is None:
            return

        changed = False
        before_devices = compute_devices_list()

        for device_class in self.helper.get_device_classes():
            # gather only the entries for this class
            wants = [
                (vd, per_mode, opts)
                for (cls, vd, per_mode, opts) in self.wants.devices
                if cls == device_class
            ]
            if self.devices_set_mode == "strict":
                changed |= self._enforce_device_class_strict_mode(
                    device_class, wants
                )
            elif self.devices_set_mode == "append":
                changed |= self._enforce_device_class_append_mode(
                    device_class, wants
                )
        if changed:
            self.changed = True
            self.diff["before"]["devices"] = before_devices
            self.diff["after"]["devices"] = compute_devices_list()

    def enforce_existence(self):
        """Creates or remove the qube"""
        if self.wants.state == "absent":
            if self.qube:
                self.diff["before"][
                    "state"
                ] = self.qube.get_power_state().lower()
                self.diff["after"]["state"] = "absent"
                self.helper.remove(self.qube_name)
                self.changed = True
                self.deleted = True
        else:
            if self.qube:
                self.diff["before"][
                    "state"
                ] = self.qube.get_power_state().lower()
            if not self.qube:
                if self.wants.clone_src:
                    if not self.wants.clone_src in self.helper.app.domains:
                        self.module.fail_json(
                            msg=f"Cannot clone the '{self.wants.clone_src}' because it doesn't exist"
                        )
                    source_vm = self.helper.app.domains[self.wants.clone_src]
                    self.helper.app.clone_vm(
                        src_vm=source_vm,
                        new_name=self.qube_name,
                        new_cls=(self.wants.klass or "AppVM"),
                        ignore_devices=True,
                    )
                else:
                    self.helper.create(
                        vmname=self.qube_name,
                        vmtype=self.wants.klass,
                        template=self.wants.template,
                    )
                self.changed = True
                self.created = True
                self.qube = self.helper.get_vm(self.qube_name)
                self.diff["before"]["state"] = "absent"

    def enforce_features(self):
        for feature_name, feature_val in self.wants.features.items():
            if feature_val is None:
                if feature_name in self.qube.features:
                    self.changed = True
                    self.diff["before"].setdefault("features", {})
                    self.diff["after"].setdefault("features", {})
                    self.diff["before"]["features"][feature_name] = (
                        self.qube.features.get(feature_name)
                    )
                    self.diff["after"]["features"][feature_name] = None
                    del self.qube.features[feature_name]

            elif self.qube.features.get(feature_name) != feature_val:
                self.changed = True
                self.diff["before"].setdefault("features", {})
                self.diff["after"].setdefault("features", {})
                self.diff["before"]["features"][feature_name] = (
                    self.qube.features.get(feature_name)
                )
                self.diff["after"]["features"][feature_name] = feature_val
                self.qube.features[feature_name] = feature_val

    def enforce_notes(self):
        if self.wants.notes is None:
            return

        notes = self.qube.get_notes()
        if notes != self.wants.notes:
            self.changed = True
            self.diff["before"]["notes"] = notes
            self.diff["after"]["notes"] = self.wants.notes
            self.qube.set_notes(self.wants.notes)

    def enforce_properties(self):
        self._shutdown_for_template_update()
        before = {}
        after = {}

        for property_name, property_val in self.wants.properties.items():
            try:
                if self.qube.property_is_default(property_name):
                    if property_val == "*default*":
                        continue
                    before_val = "*default*"
                else:
                    before_val = getattr(self.qube, property_name)

                # Useful for VMs
                if hasattr(before_val, "name"):
                    before_val = before_val.name

                value_to_set = (
                    qubesadmin.DEFAULT
                    if property_val == "*default*"
                    else property_val
                )

                if before_val != value_to_set:
                    setattr(self.qube, property_name, value_to_set)
                    before[property_name] = before_val
                    after[property_name] = property_val
            except qubesadmin.exc.QubesNoSuchPropertyError:
                self.module.fail_json(
                    msg=f"Invalid property: '{property_name}'"
                )
            except qubesadmin.exc.QubesValueError as e:
                self.module.fail_json(
                    msg=f"Invalid property value type for '{property_name}': {e}"
                )
            except qubesadmin.exc.QubesException as e:
                self.module.fail_json(
                    msg=f"Error while setting property '{property_name}': {e}",
                )
        if before or after:
            self.changed = True
            self.diff["before"]["properties"] = before
            self.diff["after"]["properties"] = after

    def enforce_state(self):
        current_status = self.qube.get_power_state().lower()
        if self.wants.state in ["present", "halted"]:
            return

        if current_status == self.wants.state:
            return

        if self.wants.state in ["running", "restarted"]:
            self.changed = True
            if current_status == "paused":
                self.qube.unpause()
            else:
                self.qube.start()

        if self.wants.state == "paused":
            self.changed = True
            self.qube.pause()

    def enforce_tags(self):
        """Add a list of tags to a qube, skipping any already present."""
        if self.wants.tags is None:
            return

        tags_before = list(self.qube.tags)
        tags_after = []
        changed = False
        for tag in self.wants.tags:
            if tag in self.qube.tags:
                continue
            self.qube.tags.add(tag)
            tags_after.append(tag)
            changed = True
        if changed:
            self.changed = True
            self.diff["before"]["tags"] = tags_before
            self.diff["after"]["tags"] = tags_after

    def enforce_volumes(self):
        for volume_name, volume_config in self.wants.volumes.items():
            for property_name, property_value in volume_config.items():
                volume = self.qube.volumes[volume_name]
                if property_name == "size":
                    if volume.size != int(property_value):
                        self.changed = True
                        self.diff["before"].setdefault("volumes", {})
                        self.diff["after"].setdefault("volumes", {})
                        self.diff["before"]["volumes"].setdefault(
                            volume_name, {}
                        )
                        self.diff["after"]["volumes"].setdefault(
                            volume_name, {}
                        )
                        self.diff["before"]["volumes"][volume_name][
                            "size"
                        ] = volume.size
                        self.diff["after"]["volumes"][volume_name]["size"] = (
                            int(property_value)
                        )
                        volume.resize(int(property_value))

                if property_name == "revisions_to_keep":
                    if volume.revisions_to_keep != int(property_value):
                        self.changed = True
                        self.diff["before"].setdefault("volumes", {})
                        self.diff["after"].setdefault("volumes", {})
                        self.diff["before"]["volumes"].setdefault(
                            volume_name, {}
                        )
                        self.diff["after"]["volumes"].setdefault(
                            volume_name, {}
                        )
                        self.diff["before"]["volumes"][volume_name][
                            "revisions_to_keep"
                        ] = volume.revisions_to_keep
                        self.diff["after"]["volumes"][volume_name][
                            "revisions_to_keep"
                        ] = int(property_value)
                        volume.revisions_to_keep = int(property_value)

    def validate_module_parameters(self):
        """Check if the module parameters are valid"""

        # We can't change the class of a Qube
        if self.qube is not None and self.wants.klass is not None:
            if self.wants.klass != self.qube.klass:
                self.module.fail_json(
                    msg=f"Current Qube type is {self.qube.klass} and cannot be "
                    f"changed to {self.wants.klass}"
                )

        self.validate_properties()
        self.validate_volumes()
        self.validate_devices()
        self.validate_services()

    def validate_devices(self):
        """Check and normalize devices parameter"""
        if self.wants.devices is None:
            return

        if isinstance(self.wants.devices, dict):
            unexpected_keys = set(self.wants.devices) - {"strategy", "items"}
            if unexpected_keys:
                self.module.fail_json(
                    msg=f"Unexpected keys in 'devices' parameter: {unexpected_keys}"
                )
            device_specs = self.wants.devices.get("items", [])
            self.devices_set_mode = self.wants.devices.get("strategy", "strict")
            if self.devices_set_mode not in ["strict", "append"]:
                self.module.fail_json(
                    msg=f"Invalid devices strategy: {self.devices_set_mode}"
                )
        elif isinstance(self.wants.devices, list):
            # flat list -> always strict
            device_specs = self.wants.devices
            self.devices_set_mode = "strict"

        else:
            self.module.fail_json(
                msg=f"Invalid devices parameter: {self.wants.devices!r}"
            )

        # Now expand each spec into (class, VirtualDevice, per_mode, options)
        normalized_devices = []
        for entry in device_specs:
            if isinstance(entry, str):
                # simple string spec -> no per-device mode or options
                cls, vd = self.helper.parse_device(entry)
                normalized_devices.append((cls, vd, None, []))
            elif isinstance(entry, dict):
                # dict spec must have a "device" key
                device_str = entry.get("device")
                if not device_str:
                    self.module.fail_json(
                        msg=f"Device entry missing 'device': {entry!r}"
                    )
                cls, vd = self.helper.parse_device(device_str)
                # optional per-device mode (e.g. "required" or "auto-attach")
                per_mode = entry.get("mode")
                # optional options list
                opts = entry.get("options", {})
                normalized_devices.append((cls, vd, per_mode, opts))
            else:
                self.module.fail_json(msg=f"Invalid device entry: {entry!r}")
        self.wants.devices = normalized_devices

    def validate_properties(self):
        # Check VM existence for the following properties

        for property in [
            "audiovm",
            "default_dispvm",
            "management_dispvm",
            "netvm",
        ]:
            value = self.wants.properties.get(property)
            if value in (None, "", "dom0", "*default*", self.qube_name):
                continue

            try:
                vm = self.helper.get_vm(value)
            except KeyError:
                self.module.fail_json(
                    msg=f"Cannot set value '{value}' to property '{property}': the qube doesn't exist",
                )

            # qubes that must provide network
            if property in ["netvm"]:
                if not vm.provides_network:
                    self.module.fail_json(
                        msg=f"Cannot set value '{value}' to property '{property}': the qube must provide network",
                    )

            # qubes that must be templates for dispvms
            if property in ["default_dispvm", "management_dispvm"]:
                if not vm.klass == "AppVM" or not vm.template_for_dispvms:
                    self.module.fail_json(
                        msg=f"Cannot set value '{value}' to property '{property}: the qube is not a template for dispvm",
                    )

    def validate_services(self):
        if self.wants.services is None:
            return

        if not isinstance(self.wants.services, list):
            self.module.fail_json("Service must be provided as a list")

        for service in self.wants.services:
            self.wants.features[f"service.{service}"] = "1"

    def validate_volumes(self):
        """Validates 'volumes' module parameters (variable f"""
        try:
            for volume_name, volume_config in self.wants.volumes.items():
                if volume_name not in ["private", "root"]:
                    self.module.fail_json(
                        msg=f"Unsupported volume name '{volume_name}"
                    )

                if self.wants.klass is not None:
                    vm_type = self.wants.klass
                # If VM Type is not provided to the module, look at the Qube
                elif self.qube:
                    vm_type = self.qube.klass
                # If the Qube doesn't exist currently, it will be created
                # using as an AppVM by default
                else:
                    vm_type = "AppVM"
                if volume_name == "root" and vm_type not in [
                    "TemplateVM",
                    "StandaloneVM",
                ]:
                    self.module.fail_json(
                        msg=f"Cannot change root volume config for '{vm_type}'"
                    )

        except AssertionError as e:
            self.module.fail_json(msg=str(e))

    def run(self):
        # Before doing anything, we want to be sure every module parameters
        # has been set correctly.
        # This is not required for absent state because we'll just have to
        # delete the qube, so we can ignore supplied attributes.
        if self.wants.state != "absent":
            self.validate_module_parameters()

        # Create or delete the qube
        self.enforce_existence()

        # We've deleted the qube so there is no remaining action to do
        # when wanted absent state
        if self.wants.state != "absent":
            # If we need to shutdown the qube, let's do it before enforcing its
            # properties to avoid errors
            if self.wants.state in ["halted", "restarted"]:
                if not self.qube.is_halted():
                    self.changed = True
                    self.helper.shutdown(self.qube_name, wait=True)

            self.enforce_all()

            self.diff["after"]["state"] = self.qube.get_power_state().lower()
            if self.diff["before"]["state"] == self.diff["after"]["state"]:
                del self.diff["before"]["state"]
                del self.diff["after"]["state"]

            if self.created:
                self.diff["before"] = {}

            if self.deleted:
                self.diff["after"] = {}

        self.module.exit_json(
            changed=self.changed,
            diff=self.diff,
            created=self.created,
            deleted=self.deleted,
        )


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="str", aliases=["guest"], required=True),
            state=dict(
                type="str",
                choices=[
                    "absent",
                    "destroyed",
                    "halted",
                    "pause",
                    "paused",
                    "present",
                    "restarted",
                    "running",
                    "shutdown",
                ],
                required=True,
            ),
            clone_src=dict(type="str", default=None),
            devices=dict(type="raw", default=None),
            features=dict(type="dict", default=None),
            notes=dict(type="str", default=None),
            properties=dict(type="dict", default=None),
            services=dict(type="list", default=None),
            shutdown_if_required=dict(type="bool", default=False),
            tags=dict(type="list", default=[]),
            template=dict(type="str", default=None),
            klass=dict(type="str", default="AppVM", aliases=["vmtype"]),
            volumes=dict(type="dict", default=None),
        ),
    )

    return QubeModule(module).run()


if __name__ == "__main__":
    main()
