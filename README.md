# Ansible Connection and Module for QubesOS

This project provides an Ansible connection plugin to interact with [Qubes OS](https://qubes-os.org) virtual machines called `qubes` and an Ansible module to manage the state of your qubes.
The `qubesos` module is under active development, so the syntax and keywords may change in future releases.

## Qubes OS Management and RPC policies setup

This guide explains how to leverage Qubes OS management and RPC policies by using a dedicated management qube (hereafter referred to as `mgmtvm`).
This setup enables you to run playbooks that create and manage new qubes.

### 1. Install required package

- Ensure that the template used for `mgmtvm` has the `qubes-core-admin-client` and `qubes-ansible` packages installed.
- Set up your dedicated management qube (`mgmtvm`) and configure it as needed.

### 2. Create and customize the management qube

Create your management qube (`mgmtvm`) and customize it according to your preferences.

### 3. Define RPC policies

Create a policy file at `/etc/qubes/policy.d/30-ansible.policy` with the following content:
```
admin.vm.Create.AppVM        * mgmtvm dom0                   allow
admin.vm.Create.StandaloneVM * mgmtvm dom0                   allow
admin.vm.Create.TemplateVM   * mgmtvm dom0                   allow
admin.vm.Remove              * mgmtvm @tag:created-by-mgmtvm allow target=dom0

qubes.Filecopy       * mgmtvm @tag:created-by-mgmtvm allow
qubes.WaitForSession * mgmtvm @tag:created-by-mgmtvm allow
qubes.VMShell        * mgmtvm @tag:created-by-mgmtvm allow
qubes.VMRootShell    * mgmtvm @tag:created-by-mgmtvm allow user=root
```

### 4. Update Admin Local Read-Write policy

Append the following lines to `/etc/qubes/policy.d/include/admin-local-rwx`:
```
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

### 5. Update Admin Global Read-Only policy

Append the following lines to `/etc/qubes/policy.d/include/admin-global-ro`:
```
mgmtvm @adminvm               allow target=dom0
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

### Important notes

- The suffix number `30` in the policy file name (`30-ansible.policy`) is arbitrary. You can use a different number as long as it does not conflict with existing files.
- The `created-by-*` tag pattern is used internally to identify which management qube (other than `dom0`) created a qube.

## Examples

See the [examples](EXAMPLES.md) for sample playbooks and role tasks demonstrating common usage scenarios.

## License

This project is licensed under the GPLv3+ license. Please see the [LICENSE](LICENSE) file for the full license text.
