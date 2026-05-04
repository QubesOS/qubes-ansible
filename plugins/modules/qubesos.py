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

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = """
---
module: qubesos
short_description: Manage Qubes OS virtual machines
description:
    - This module manages Qubes OS virtual machines using the qubesadmin API.
    - It supports VM creation, state management, and various operations such as starting, pausing, shutting down, and more.
    - For definitions of Qubes OS terminology (e.g. AppVM, TemplateVM, StandaloneVM, DispVM), please refer to the Qubes OS Glossary at https://www.qubes-os.org/doc/glossary/.
version_added: "2.8"
options:
  name:
    description:
      - Name of the Qubes OS virtual machine to manage.
      - This parameter is required for operations targeting a specific VM. It can also be specified as C(guest).
  state:
    description:
      - Desired state of the VM.
      - When set to C(present), ensures the VM is defined.
      - When set to C(running), ensures the VM is started.
      - When set to C(shutdown), ensures the VM is stopped.
      - When set to C(destroyed), forces the VM to shut down.
      - When set to C(restarted), shuts the VM down then starts it again.
      - When set to C(pause), pauses a running VM.
      - When set to C(absent), removes the VM definition.
    choices: [ present, running, shutdown, destroyed, restarted, pause, absent ]
  wait:
    description:
      - If C(true), block until the VM has fully halted before returning.
      - Only applies to C(shutdown) and C(restarted) states.
    type: bool
    default: false
  command:
    description:
      - Non-idempotent command to execute on the VM.
      - "Available commands include:"
      - " - C(create): Create a new VM."
      - " - C(destroy): Force shutdown of a VM."
      - " - C(pause): Pause a running VM."
      - " - C(shutdown): Gracefully shut down a VM."
      - " - C(status): Retrieve the current state of a VM."
      - " - C(start): Start a VM."
      - " - C(stop): Stop a VM."
      - " - C(unpause): Resume a paused VM."
      - " - C(removetags): Remove specified tags from a VM."
      - " - C(info): Retrieve information about all VMs."
      - " - C(list_vms): List VMs filtered by state."
      - " - C(get_states): Get the states of all VMs."
      - " - C(createinventory): Generate an inventory file for Qubes OS VMs."
  label:
    description:
      - Label (or color) assigned to the VM. For more details, see the Qubes OS Glossary.
    default: "red"
  vmtype:
    description:
      - The type of VM to manage.
      - Typical values include C(AppVM), C(StandaloneVM), C(TemplateVM) and C(DispVM).
      - Refer to the Qubes OS Glossary for definitions of these terms.
    default: "AppVM"
  template:
    description:
      - Name of the template VM to use when creating or cloning a VM.
      - For AppVMs, this is the base TemplateVM from which the VM is derived.
    default: "default"
  properties:
    description:
      - A dictionary of VM properties to set.
      - "Valid keys include:"
      - " - autostart (bool)"
      - " - debug (bool)"
      - " - include_in_backups (bool)"
      - " - kernel (str)"
      - " - kernelopts (str)"
      - " - label (str)"
      - " - maxmem (int)"
      - " - memory (int)"
      - " - provides_network (bool)"
      - " - netvm (str)"
      - " - default_dispvm (str)"
      - " - management_dispvm (str)"
      - " - default_user (str)"
      - " - guivm (str)"
      - " - audiovm (str)"
      - " - ip (str)"
      - " - ip6 (str)"
      - " - mac (str)"
      - " - qrexec_timeout (int)"
      - " - shutdown_timeout (int)"
      - " - template (str)"
      - " - template_for_dispvms (bool)"
      - " - vcpus (int)"
      - " - virt_mode (str)"
      - " - features (dict)"
      - " - services (list)"
      - " - volumes (list of dict that must include both 'name' and 'size')"
    default: {}
  features:
    description:
      - A dictionary of VM features to set (or remove). No value for removing.
  tags:
    description:
      - A list of tags to apply to the VM.
      - Tags are used within Qubes OS for VM categorization.
    type: list
    default: []
  devices:
    description:
      - Device assignment configuration for the VM.
      - "Supported usage patterns:"
      - "1. A list (default _strict_ mode) device specs (strings or dicts). The VM's assigned devices will be exactly those listed, removing any others."
      - "2. A dictionary:"
      - " - strategy (str): assignment strategy to use.  "
      - "    - C(strict) (default): enforce exact match of assigned devices to C(items).  "
      - "    - C(append): add only new devices in C(items), leaving existing assignments intact."
      - " - items (list): list of device specs (strings or dicts) to apply under the chosen strategy."
      - "Device spec formats:"
      - " - string: `<devclass>:<backend_domain>:<port_id>[:<dev_id>]` (e.g. C(pci:dom0:5), C(block:dom0:vdb))"
      - " - dict:"
      - "    - device (str, required): the string spec as above."
      - "    - mode (str, optional):"
      - "       - For PCI devices defaults to C(required)."
      - "       - For other classes defaults to C(auto-attach)."
      - "    - options (dict, optional): extra Qubes device flags to pass when attaching."
    type: raw
    default: []
  notes:
    description:
      - Notes and comments (up to 256KB of clear text), For user reference only

requirements:
  - python >= 3.12
  - qubesadmin
  - jinja2
author:
  - Kushal Das
  - Frédéric Pierret
"""

from ansible_collections.qubesos.core.plugins.module_utils.qubes_helper import (
    QubesHelper,
    VIRT_FAILED,
    VIRT_SUCCESS,
)

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_host_devices_facts import (
    core as module_host_devices_facts,
)

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_qube import (
    QubeModule,
)
from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_command import (
    core as module_command,
)


import traceback


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


from jinja2 import Template
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native


ALL_COMMANDS = []
VM_COMMANDS = [
    "create",
    "destroy",
    "pause",
    "shutdown",
    "remove",
    "status",
    "start",
    "stop",
    "unpause",
    "removetags",
]
HOST_COMMANDS = ["info", "list_vms", "get_states", "createinventory"]
ALL_COMMANDS.extend(VM_COMMANDS)
ALL_COMMANDS.extend(HOST_COMMANDS)

PROPS = {
    "autostart": bool,
    "debug": bool,
    "include_in_backups": bool,
    "kernel": str,
    "kernelopts": str,
    "label": str,
    "maxmem": int,
    "memory": int,
    "provides_network": bool,
    "template": str,
    "template_for_dispvms": bool,
    "vcpus": int,
    "virt_mode": str,
    "default_dispvm": str,
    "management_dispvm": str,
    "default_user": str,
    "guivm": str,
    "audiovm": str,
    "netvm": str,
    "ip": str,
    "ip6": str,
    "mac": str,
    "qrexec_timeout": int,
    "shutdown_timeout": int,
    "features": dict,
    "services": list,
    "volumes": list,
}


class ModuleExitWithError(Exception):
    def __init__(self, reasons):
        self.reasons = reasons


class ValidationFailure(ValueError):
    """Exception raised for errors when validating module input"""

    def __init__(self, reasons):
        self.reasons = reasons


# Use the same wrapper class as tests to call new module and catch errors
class FakeModule:
    def __init__(self, params):
        self.params = params
        self.returned_data = None

    def fail_json(self, **kwargs):
        self.returned_data = kwargs
        raise ModuleExitWithError(kwargs)

    def exit_json(self, **kwargs):
        self.returned_data = kwargs


def _run_module_host_devices_facts():
    fake_module = FakeModule({})
    module_host_devices_facts(fake_module)
    return fake_module


def _run_module_qube(params):
    fake_module = FakeModule(params)
    QubeModule(fake_module).run()
    return fake_module


def _run_module_command(params):
    fake_module = FakeModule(params)
    module_command(fake_module)
    return fake_module


def create_inventory(result):
    """
    Creates the inventory file dynamically for QubesOS
    """
    template_str = """[local]
dom0
localhost

[local:vars]
ansible_connection=local

{% if result.AppVM %}
[appvms]
{% for item in result.AppVM %}
{{ item -}}
{% endfor %}

[appvms:vars]
ansible_connection=qubes
{% endif %}

{% if result.TemplateVM %}
[templatevms]
{% for item in result.TemplateVM %}
{{ item -}}
{% endfor %}

[templatevms:vars]
ansible_connection=qubes
{% endif %}

{% if result.StandaloneVM %}
[standalonevms]
{% for item in result.StandaloneVM %}
{{ item -}}
{% endfor %}

[standalonevms:vars]
ansible_connection=qubes
{% endif %}
"""
    template = Template(template_str)
    res = template.render(result=result)
    with open("inventory", "w") as fobj:
        fobj.write(res)


def _validate_properties(guest, helper, properties, vmtype):
    # properties will only work with state=present
    # Check properties exist (PROPS)
    # Check netvm exist
    # Check volume properties
    # This is only verification: should be conserved as format is different from
    # qubesos.core.qube
    if properties:
        for key, val in properties.items():
            if key not in PROPS:
                raise ValidationFailure({"Invalid property": key})
            if val is not None and type(val) != PROPS[key]:
                raise ValidationFailure({"Invalid property value type": key})

            # Make sure that the netvm exists
            if key == "netvm" and val not in [
                "*default*",
                "",
                "none",
                "None",
                None,
                guest,
            ]:
                try:
                    vm = helper.get_vm(val)
                except KeyError:
                    raise ValidationFailure({"Missing netvm": val})
                # Also the vm should provide network
                if not vm.provides_network:
                    raise ValidationFailure({"Missing netvm capability": val})
                netvm = vm

            # Make sure volume has both name and value
            if key == "volumes":
                if not isinstance(val, list):
                    raise ValidationFailure({"Invalid volumes provided": val})
                for vol in val:
                    try:
                        if "name" not in vol:
                            raise ValidationFailure(
                                {"Missing name for the volume": vol}
                            )
                        if "size" not in vol:
                            raise ValidationFailure(
                                {"Missing size for the volume": vol}
                            )
                        if not vol["name"] in ["root", "private"]:
                            raise ValidationFailure(
                                {"Wrong volume name": vol["name"]}
                            )
                        if vol["name"] == "root" and vmtype not in [
                            "TemplateVM",
                            "StandaloneVM",
                        ]:
                            raise ValidationFailure(
                                {
                                    f"Cannot change root volume size for '{vmtype}'"
                                }
                            )
                    except KeyError:
                        raise ValidationFailure(
                            {"Invalid volume provided": vol}
                        )

            # Make sure that the default_dispvm exists
            if key == "default_dispvm" and val != guest:
                try:
                    vm = helper.get_vm(val)
                except KeyError:
                    raise ValidationFailure({"Missing default_dispvm": val})
                # Also the vm should provide network
                if not vm.template_for_dispvms:
                    raise ValidationFailure({"Missing dispvm capability": val})


def core(module):
    state = module.params.get("state", None)
    guest = module.params.get("name", None)
    command = module.params.get("command", None)
    vmtype = module.params.get("vmtype", None)
    label = module.params.get("label", None)
    template = module.params.get("template", None)
    properties = module.params.get("properties", {})
    features = module.params.get("features", {})
    tags = module.params.get("tags", [])
    devices = module.params.get("devices", None)
    notes = module.params.get("notes", None)

    v = QubesHelper(module)

    if module.params.get("wait") == False:
        module.warn(
            f"usage of 'wait' parameter in qubesos module is no more supported."
        )

    if state == "present" and guest:
        try:
            vm = v.get_vm(guest)
            vmtype = vm.klass
        except KeyError:
            # Set default vmtype to AppVM if vmtype is not provided
            vmtype = vmtype or "AppVM"

    # Validation
    try:
        _validate_properties(guest, v, properties, vmtype)
    except ValidationFailure as e:
        return VIRT_FAILED, e.reasons

    # gather device facts
    # here, we just need to call the relevant module and retrieve the facts
    if module.params.get("gather_device_facts", False):
        fake_module = _run_module_host_devices_facts()
        return VIRT_SUCCESS, {
            "changed": False,
            "ansible_facts": fake_module.returned_data["ansible_facts"],
        }

    # Okay, we have a state and a target, we'll have to call qubesos.core.qube
    # Let's re-arrange the args to make him happy
    if state == "present" and guest:
        # Process conversion from legacy module format to new module format

        # template / clone_src
        # Legacy module was cloning VMs in those cases
        if (
            vmtype == "AppVM"
            and template
            and v.get_vm(template)._klass == "AppVM"
        ):
            # Clone VM when specifying
            clone_src = template

            # Don't mange the template, will be set automatically when cloning
            template = None
        elif vmtype in ["StandaloneVM", "TemplateVM"] and template:
            clone_src = template
            template = None
        else:
            clone_src = None

        # properties / features / services / volumes
        volumes = None
        services = None
        if properties:
            # Features
            # extract features from the properties key
            properties_feature = properties.pop("features", {})
            if properties_feature or features:
                if features is None:
                    features = {}

                for feat_item, feat_val in properties_feature.items():
                    # In legacy module, features from high level feature key
                    # were enforced after features in set in sub element of
                    # properties
                    if feat_item not in features:
                        features[feat_item] = feat_val

            # Services
            # just extract the key from properties. No modification is needed
            services = properties.pop("services", None)

            # Volumes
            properties_volumes = properties.pop("volumes", [])
            if properties_volumes:
                volumes = {}
                for vol in properties_volumes:
                    volumes[vol["name"]] = {"size": vol["size"]}

        # Label is not a module param for the new module
        if label:
            if not properties:
                properties = {}
            properties["label"] = label

        # Call the module
        try:
            fake_module = _run_module_qube(
                {
                    "clone_src": clone_src,
                    "devices": devices,
                    "features": features,
                    "klass": vmtype,
                    "name": guest,
                    "notes": notes,
                    "properties": {
                        prop_name: None if prop_val == "None" else prop_val
                        for prop_name, prop_val in properties.items()
                    },
                    "services": services,
                    "shutdown_if_required": False,
                    "state": state,
                    "tags": tags,
                    "template": template,
                    "volumes": volumes,
                }
            )

            # Now, try to translate new returned data to legacy ones
            res_properties_updates = []
            returned_data = fake_module.returned_data

            # Tags
            tags_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("tags")
            )
            if tags_updates:
                returned_data["Tags updated"] = tags_updates

            # Features
            features_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("features")
            )
            if features_updates:
                returned_data["Features updated"] = list(
                    features_updates.keys()
                )
                res_properties_updates.append("features")

            # Volumes (properties)
            volume_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("volumes")
            )
            if volume_updates:
                res_properties_updates += [
                    f"volume:{volume}" for volume in volume_updates
                ]

            # Properties
            properties_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("properties")
            )
            if properties_updates:
                res_properties_updates += list(properties_updates.keys())
            if res_properties_updates:
                returned_data["Properties updated"] = res_properties_updates

            # Devices
            devices_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("devices")
            )
            if devices_updates:
                returned_data["Devices updated"] = True

            notes_updates = (
                fake_module.returned_data.get("diff", {})
                .get("after", {})
                .get("notes")
            )
            if notes:
                returned_data["Notes updated"] = True
            return VIRT_SUCCESS, fake_module.returned_data

        except ModuleExitWithError as e:
            return VIRT_FAILED, e.reasons

    # Commands
    if command:
        try:
            fake_module = _run_module_command(module.params)
            return VIRT_SUCCESS, fake_module.returned_data
        except ModuleExitWithError as e:
            return VIRT_FAILED, e.reasons

    if state:
        if not guest:
            module.fail_json(msg="State change requires a guest specified")

        try:
            fake_module = _run_module_qube(
                {
                    "name": guest,
                    "state": state,
                }
            )
            return VIRT_SUCCESS, fake_module.returned_data
        except RuntimeError as e:
            module.fail_json(msg=str(e))
        except ModuleExitWithError as e:
            return VIRT_FAILED, e.reasons

    module.fail_json(msg="Expected state or command parameter to be specified")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="str", aliases=["guest"]),
            state=dict(
                type="str",
                choices=[
                    "destroyed",
                    "pause",
                    "running",
                    "shutdown",
                    "restarted",
                    "absent",
                    "present",
                ],
            ),
            wait=dict(type="bool", default=True),
            command=dict(type="str", choices=ALL_COMMANDS),
            label=dict(type="str", default=None),
            vmtype=dict(type="str", default="AppVM"),
            template=dict(type="str", default=None),
            properties=dict(type="dict", default={}),
            features=dict(type="dict", default={}),
            tags=dict(type="list", default=[]),
            devices=dict(type="raw", default=None),
            notes=dict(type="str", default=None),
            gather_device_facts=dict(type="bool", default=False),
        ),
    )

    module.deprecate(
        "Usage of this module is deprecated and support will be dropped in a "
        "future release. Consider switching to qubes.core.qubes module instead.",
    )

    if not qubesadmin:
        module.fail_json(
            msg="The `qubesos` module is not importable. Check the requirements."
        )

    result = None
    rc = VIRT_SUCCESS
    try:
        rc, result = core(module)
    except Exception as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    if rc != 0:  # something went wrong emit the msg
        module.fail_json(rc=rc, msg=result)
    else:
        module.exit_json(**result)


if __name__ == "__main__":
    main()
