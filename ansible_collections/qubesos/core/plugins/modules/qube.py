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


DOCUMENTATION = r"""
---
module: qube

short_description: Everything related to the management of your QubesOS qubes.

description:
    - Create and delete qubes.
    - Control your qubes state (start, stop, pause...) .
    - Manage their attributes (features, properties, label, notes, assigned devices...).

version_added: "1.0.0"

options:
    name:
        description: The name of the qube you want to manage.
        required: true
        type: str

    state:
        description: The qubes desired state.
        required: true
        type: str
        choices:
            - absent
            - present
            - halted
            - pause
            - present
            - restarted
            - running
            - shutdown

    clone_src:
        description:
            - Create a new qube using the specified qube as source.
            - You can specify different types in O(clone_src) and O(klass).
            - For example, specifying a O(clone_src=my-template-qube) and
              O(klass=StandaloneVM) will create a StandaloneVM from a TemplateVM.

        type: str

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
            - A list of strings representing the devices to assign to the qube.
            - Use facts module M(qubesos.core.host_devices_facts) to retrieve the list of available devices.

    features:
        description:
            - Configure the features of the qube.
            - You have to provide a dict with features name as dict key and the desired value as dict value.
        type: dict

    force:
        description:
            - If C(true), shut down the target VM regardless of whether other
              VMs are connected to it (e.g. AppVMs using it as a netvm).
            - Equivalent to C(qvm-shutdown --force) on the CLI. The target still
              halts gracefully; only the "connected domains" precondition is
              skipped. Dependent VMs keep running but lose their uplink until
              the netvm is started again.
            - For a hard-kill (equivalent to C(qvm-kill) / SIGKILL of the Xen
              domain, no graceful shutdown), use C(state=destroyed) instead.
            - Only applies to C(shutdown) and C(restarted) states.
        type: bool
        default: false

    notes:
        description:    
            - Set the qube notes.
        type: str

    properties:
        description:
            - Manage the qube properties as with the qvm-prefs command.
            - The module doesn't check if the property exists and performs a very simple validation
              for a couple of properties (for example, if you set the V(netvm) property, it will check if
              the VM exists).
            - With the exception of these few properties, it will let the qubesd service
              handles errors and will fail during execution.
            - As for features, the module expects a dict with properties name as key and their expected value as dict value.
        type: dict

    services:
        description:
            - Enables the provided services on a qube.
            - Provided services names are translated into the feature format
            - (service.myservice=1) and added to the list of expected features.
            - If a service is specified both in the O(features) and O(services) options,
            - the value in O(services) is kept.
        type: list
        elements: str

    shutdown_if_required:
        description:
            - Allow Ansible to shutdown the qube if an operation requires it.
            - This option currently applies only when changing the qube's template.
        type: bool
        default: false

    tags:
        description:
            - Add the provided tags to the qube.
        type: list
        elements: str

    template:
        description:
            - Set the qube template.
        type: str

    klass:
        description:
            - Set the qube type.
            - Trying to change the type of an existing qube will raise an error.
            - This option is used when creating or cloning a VM.
        aliases:
            - vmtype
        type: str

    volumes:
        description:
            - Change the settings of the qube volumes.
            - Volume name must be specified as dict key and volume settings as subelements.
        suboptions:
            size:
                description:
                    - The volume size.
            revisions_to_keep:
                description:
                    - Set the number of revisions to keep.

requirements:
  - qubesadmin
"""

EXAMPLES = r"""
- name: Create an AppVM using the system default template
  qubesos.core.qube:
        name: my-app-vm
        klass: AppVM
        state: present


- name: Start a qube
  qubesos.core.qube:
    name: my-app-vm
    state: running

- name: Stop a qube
  qubesos.core.qube:
    name: my-app-vm
    state: halted

- name: Remove a qube
  qubesos.core.qube:
    name: my-app-vm
    state: absent

- name: Ensure my-app-vm is running and has the following attributes
  qubesos.core.qube:
    name: my-app-vm
    klass: AppVM
    state: running
    features:
        menu-items: "xfce4-terminal.desktop thunar.desktop firefox-esr.desktop xfce-settings-manager.desktop"
    properties:
        autostart: true
        qrexec_timeout: 600
        provides_network: true
    tags:
        - my-tag
    label: yellow
    notes: Notes about my qube

- name: Create an AppVM using an old template
  qubesos.core.qube:
    name: my-app-vm
    klass: AppVM
    state: present
    template: my-old-template
- name: Now, update to a new template
  qubesos.core.qube:
    name: my-app-vm
    klass: AppVM
    state: present
    template: my-new-template
    shutdown_if_required: true

- name: Create a StandaloneVM
  qubesos.core.qube:
    name: my-standalone-vm
    klass: StandaloneVM
    clone_src: debian-13-xfce
    state: present
    volumes:
        private:
            size: 32212254720
"""

RETURN = r"""
changed:
    description: Indicates if the qube was changed by the module
    type: bool
    returned: always

created:
    description: Indicated if the qube was created by the module
    type: bool
    returned: always

deleted:
    description: Indicated if the qube was created by the module
    type: bool
    returned: always

diff:
    description: Contains the state of changed resource before and after the modification
    type: dict
    returned: always
    contains:
        before:
            description: The qube properties before the modification.
            type: dict
        after:
            description: The qube properties after the modification.
            type: dict
"""

from ansible_collections.qubesos.core.plugins.module_utils.qubes_module_qube import (
    main,
)

if __name__ == "__main__":
    main()
