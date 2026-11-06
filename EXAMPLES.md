# Example tasks

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
ansible_connection=qubesos.core.qubes

[templatevms]
fedora-demo

[templatevms:vars]
ansible_connection=qubesos.core.qubes
```

Once the inventory file is created, you can execute Ansible playbooks using:

```bash
ansible-playbook -i inventory my_playbook.yaml
```

To create an inventory file that automatically includes all Qubes, run the following command:

```bash
ansible localhost -m qubesos.core.command -a 'command=createinventory'
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
        qubesos.core.qube:
          name: testqube
          state: present
          template: "debian-12-xfce"
```

> Remark: Only `name` and `state` parameter are mandatory. By default, 
> the module uses the system default TemplateVM and NetVM, and the default 
> label color is **red**.

## Creating multiple qubes with custom properties and tags

The following example demonstrates creating multiple qubes with specific labels,
templates, properties, and a policy file for inter-qube communication. Notice that the 'label' of the qube is now set as a property - in earlier versions it was a parameter.

```yaml
---
- hosts: local
  connection: local
  tasks:
      - name: Create vault-demo with custom properties
        qubesos.core.qube:
          name: vault-demo
          state: present
          template: "fedora-41-xfce"
          properties:
            label: black
            memory: 600
            maxmem: 800
            netvm: ""

      - name: Create work-demo qube using a template
        qubesos.core.qube:
          name: work-demo
          state: present
          template: "fedora-41-xfce"
          properties:
            label: blue


      - name: Create project-demo qube using a template
        qubesos.core.qube:
          name: project-demo
          state: present
          template: "fedora-41-xfce"
          properties:
            label: orange


      - name: Create policy file for qube communications
        ansible.builtin.copy:
          dest: /etc/qubes/policy.d/10-demo.policy
          content: |
            qubes.Gpg * work-demo vault-demo allow
            project.Service1 * work-demo @default allow target=project-demo
          mode: '0755'
          owner: root
          group: qubes
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
            volumes:
              - name: "private"
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
