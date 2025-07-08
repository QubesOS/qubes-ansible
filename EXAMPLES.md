# Example tasks

The **qubesos** module is under active development, and its syntax and available options may evolve.
Refer to the examples below to learn more about managing Qubes OS qubes.

## Creating an inventory file for Ansible

To set up an inventory file, create a file with content similar to the following:
```ini
[local]
localhost

[local:vars]
ansible_connection=local

[appvms]
vault-demo
work-demo
admin-demo
project-demo

[appvms:vars]
ansible_connection=qubes

[templatevms]
fedora-demo

[templatevms:vars]
ansible_connection=qubes
```

Once the inventory file is created, you can execute Ansible playbooks using:

```bash
ansible-playbook -i inventory my_playbook.yaml
```

To create an inventory file that automatically includes all Qubes, run the following command:

```bash
ansible localhost -m qubesos -a 'command=createinventory'
```

> Warning: This command **overwrites** the existing inventory file in the local directory.

If the `[standalonevms]` section is empty in the generated `inventory` file, delete that section along with its connection details to maintain a clean and organized file.

## Ensuring a qube is present

This is the preferred method to create a new qube if it is not already present.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Create a test qube
        qubesos:
          guest: testqube
          label: blue
          state: present
          template: "debian-12-xfce"
```

> Remark: Only the *guest* parameter is mandatory. By default, the module uses the system default TemplateVM and NetVM, and the default label color is **red**.

## Creating multiple qubes with custom properties and tags

The following example demonstrates creating multiple qubes with specific labels, templates, properties, and a policy file for inter-qube communication.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Create vault-demo with custom properties
        qubesos:
          guest: vault-demo
          label: black
          state: present
          template: "fedora-41-xfce"
          properties:
            memory: 600
            maxmem: 800
            netvm: ""

      - name: Create work-demo qube using a template
        qubesos:
          guest: work-demo
          label: blue
          state: present
          template: "fedora-41-xfce"

      - name: Create project-demo qube using a template
        qubesos:
          guest: project-demo
          label: orange
          state: present
          template: "fedora-41-xfce"

      - name: Create policy file for qube communications
        copy:
          dest: /etc/qubes/policy.d/10-demo.policy
          content: |
            qubes.Gpg * work-demo vault-demo allow
            project.Service1 * work-demo @default allow target=project-demo
          mode: '0755'
```

### Available properties

The following properties and their types are supported:

- **autostart**: `bool`
- **debug**: `bool`
- **include_in_backups**: `bool`
- **kernel**: `str`
- **label**: `str`
- **maxmem**: `int`
- **memory**: `int`
- **provides_network**: `bool`
- **template**: `str`
- **template_for_dispvms**: `bool`
- **vcpus**: `int`
- **virt_mode**: `str`
- **default_dispvm**: `str`
- **netvm**: `str`
- **features**: `dict[str, str]`
- **volume**: `dict[str, str]`

To modify an existing qube's properties, first shut it down and then apply the new properties with state `present`.

## Setting different property values for a qube

Properties can be applied during qube creation or to an existing (but shut down) qube.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Set properties for social qube
        qubesos:
          guest: social
          state: present
          properties:
            memory: 1200
            maxmem: 2400
            netvm: 'sys-whonix'
            default_dispvm: 'fedora-41-dvm'
            label: "yellow"

      - name: Ensure the social qube is defined
        qubesos:
          guest: social
          state: present

      - name: Start the social qube
        qubesos:
          guest: social
          state: running
```

> Remark: Change the state to `running` to power on the qube.

## Resizing a qube's volume

A qube's volume can be resized using the *volume* property.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Resize volume for social qube
        qubesos:
          guest: social
          state: present
          properties:
            memory: 1200
            maxmem: 2400
            netvm: 'sys-whonix'
            label: "yellow"
            volume:
              name: "private"
              size: "5368709120"
```

## Adding tags to a qube

Tags (a list of strings) can be assigned to a qube for categorization.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Assign tags to social qube
        qubesos:
          guest: social
          state: present
          tags:
            - "Linux"
            - "IRC"
            - "Chat"
```

## Different available states

The module supports the following states:

- **destroyed**
- **pause**
- **running**
- **shutdown**
- **absent**
- **present**

**Warning:** The `absent` state will remove the qube and all associated data. Use with caution.

## Different available commands

### **shutdown**

Gracefully shut down the qube.

```bash
ansible localhost -m qubesos -a 'guest=social command=shutdown'
```

### **destroy**

Forcefully shut down the qube immediately.

```bash
ansible localhost -m qubesos -a 'guest=social command=destroy'
```

### **removetags**

Remove specified tags from a qube.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Remove tags from social qube
        qubesos:
          guest: social
          command: removetags
          tags:
            - "Linux"
            - "IRC"
            - "Chat"
```

## Find qubes by state

List all qubes with a particular state (e.g., running):

```bash
ansible localhost -m qubesos -a 'state=running command=list_vms'
```

## Run a command in every running qube

```yaml
---
- hosts: localhost
  connection: local
  tasks:
      - name: Retrieve list of running qubes
        qubesos:
          command: list_vms
          state: running
        register: rhosts

- hosts: "{{ hostvars['localhost']['rhosts']['list_vms'] }}"
  connection: qubes
  tasks:
      - name: Get hostname of each qube
        command: hostname
```

## Shutdown all qubes except system qubes

```yaml
---
- hosts: localhost
  connection: local
  tasks:
      - name: Retrieve running qubes
        qubesos:
          command: list_vms
          state: running
        register: rhosts

      - name: Shutdown each non-system qube
        qubesos:
          command: destroy
          guest: "{{ item }}"
        with_items: "{{ rhosts.list_vms }}"
        when: not item.startswith("sys-")
```

Run the above playbook using:

```bash
ansible-playbook -i inventory -b shutdown_all.yaml
```

## Clone qubes that don't have the `created-by-mgmtvm` tag ("unmanaged" qubes)

Users commonly need to clone qubes that don't have the `created-by-mgmtvm` tag, like templates they install through `qvm-template`, ("unmanaged" qubes). However, `mgmtvm` didn't create these qubes, so `mgmtvm` shouldn't be able to modify them.

The `90-admin-default` policy doesn't allow source qubes to clone target qubes through `include/admin-local-ro`. This include file also allows more RPCs than strictly necessary to clone target qubes.

The same policy, `90-admin-default`, allows source qubes to clone target qubes through `include/admin-global-rwx`, but it also allows sources to modify targets.

Instead of adding unmanaged qubes to `include/admin-local-rwx` (literally or by setting the `created-by-mgmtvm` tag on them), create a new policy file to allow the exact set of RPCs that source qubes need to clone target qubes.

First, create a new include file at `/etc/qubes/policy.d/include/admin-clone` that lists the qubes that `mgmtvm` should be able to clone, but not modify:
```
# This is just an example. List any qubes you want to clone as targets.
mgmtvm fedora-41-minimal allow target=dom0
mgmtvm fedora-41-xfce    allow target=dom0
mgmtvm debian-12-minimal allow target=dom0
mgmtvm debian-12-xfce    allow target=dom0
```

Users can use any target qube specifier in the include file. However, if users add `@tag:TemplateVM` as a target to this list, `mgmtvm` could clone any template on the system, including templates that were cloned manually or by another management qube. It's safest to use literal qube names or custom tags (`@tag:cloneable-by-mgmtvm`, for example) as target specifiers in the include file.

Create a new policy file at `/etc/qubes/policy.d/30-admin-clone.policy`:
```
!include-service admin.vm.List               * include/admin-clone
!include-service admin.vm.volume.List        * include/admin-clone
!include-service admin.vm.volume.Info        * include/admin-clone
!include-service admin.vm.property.List      * include/admin-clone
!include-service admin.vm.property.Get       * include/admin-clone
!include-service admin.vm.property.GetAll    * include/admin-clone
!include-service admin.vm.tag.List           * include/admin-clone
!include-service admin.volume.CloneFrom      * include/admin-clone
!include-service admin.feature.List          * include/admin-clone
!include-service admin.feature.Get           * include/admin-clone
!include-service admin.firewall.Get          * include/admin-clone
!include-service admin.device.block.List     * include/admin-clone
!include-service admin.device.mic.List       * include/admin-clone
!include-service admin.device.pci.List       * include/admin-clone
!include-service admin.device.testclass.List * include/admin-clone
```

This clones the `template` qube to the `guest` qube as a TemplateVM:
```yaml
---
- hosts: localhost
  connection: local
  tasks:
      - name: Clone fedora-41-xfce template
        qubesos:
          guest: fedora-41-xfce-clone
          vmtype: "TemplateVM"
          state: present
          template: "fedora-41-xfce"
```

This creates `guest` as a standalone qube from the `template`:
```yaml
---
- hosts: localhost
  connection: local
  tasks:
      - name: Clone fedora-41-xfce template
        qubesos:
          guest: fedora-41-xfce-standalone
          vmtype: "StandaloneVM"
          state: present
          template: "fedora-41-xfce"
```

The resulting qubes will not have appmenu entries since the [Admin API doesn't support it](https://github.com/QubesOS/qubes-issues/issues/4809). Users can generate appmenus entries manually from `dom0` or the qube settings GUI.
