# Ansible plugins for QubesOS

This project provides Ansible plugins to interact and manage your [Qubes OS](https://qubes-os.org) virtual machines (called `qubes`).
Those plugins are under active development, so the syntax and keywords may change in future releases. Contributions and feedback are welcome!

## Plugins description

### ``qubesos`` module

This module may be used to interact with the QubesOS API to manage the state 
of your qubes. You can use it to create, update, remove, restart your qubes as
well as change their properties.

### ``qubes`` connection plugin

This connection plugin allows Ansible to connect to your qubes using the
[QubesOS qrexec framework](https://www.qubes-os.org/doc/qrexec/).

### ``qubes_proxy`` strategy plugin

This strategy plugin must be used when Ansible is running on dom0 to prevent any
security issue. The plugin acts as a router which will proxify play execution for a 
given qube into its management disposable VM.

Technically, the plugin builds an extract of the running playbook, extract host variables and roles
and run `ansible-playbook` on the management disposable.


Using this plugin ensures dom0 isolation from untrusted Ansible data (see https://github.com/QubesOS/qubes-issues/issues/10030).

__NOTE__ - this strategy is set as the default on dom0. Switching to another strategy 
will raise an error and interrupt Ansible execution.

## Installation

### AdminVM (dom0)

Install the following package: ``qubes-ansible-dom0``

### Management DVM

The package ``qubes-ansible-vm`` (``qubes-ansible`` for Debian and Archlinux) must be installed 
on templates used by your qubes management DVM (``default-mgmt-dvm`` by default).

## Usage

``qubes`` and ``qubes_proxy`` plugins work out of the box when installed using 
RPM. The strategy plugin will read the value of the ``hosts`` field 
in your playbooks and:
  - run the play locally when ``localhost`` is present in the list (dom0 management / ``qubesos`` module usage)
  - proxify play execution through the target disposable management VM that will automatically use the ``qubes`` connection plugin to run the tasks on the target

Using a custom `ansible.cfg` file may override Ansible strategy to `linear` would be detected 
by the `qubesos_strategy_guard` callback and would cause Ansible to stop. If using such file, 
add the following setting to ensure `qubes_proxy` strategy is used:
```
[defaults]
strategy=qubes_proxy
```

You can also put this line in your Play declaration:
```
strategy: qubes_proxy
```

If extra files need to be present on the disposable VM to execute the playbook, you will need
to place those files in a role and call the role in your play using the `roles` keyword:
```
- hosts: work
  connection: qubes
  strategy: qubes_proxy
  roles:
  - my_role_which_will_copy_files_to_work
```

The repository structure should look the following:

```
ansible
|    playbook.yml
|    inventory
└─── roles
     └─── my_role_which_will_copy_files_to_work
          └── tasks
              └── main.yml
          └── files
              └── file_to_copy_to_work.txt    
```


See the [examples](EXAMPLES.md) for sample playbooks and role tasks demonstrating common usage scenarios.

## Limitations

The proxy plugin may modify the behaviour of your playbooks. Please notice the following indications and 
limitations:
* **Access to facts and variables from other hosts is not possible**: the proxy strategy builds a single
  host vars file containing a merged view of the target's host variables (i.e., variables issued from command line, group vars, host vars, inventory...).
  Therefore, attempting to access a variable not directly associated with that host will not work as it will
  not be present in the merged view.
* **Extra files may not be copied to the disposable VM**: the proxy plugin does not parse playbooks tasks so
  it has no idea which file needs to be copied to the disposable. However, play roles are copied to the dispvm.
* **Tasks executions are not synchronous but Play execution are**: behavious should be almost the same as the [free strategy](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/free_strategy.html).
* **Disposables output is not parsed**:
  * Play recap will reflect the number of plays ran for each host instead of the number of tasks
  * Only plain text output is supported

## Management VM

Usage of this module with a Management VM is not yet supported. However, the 
following policies may be added if doing so:

Append the following lines to `/etc/qubes/policy.d/include/admin-local-rwx`:
```
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

Append the following lines to `/etc/qubes/policy.d/include/admin-global-ro`:
```
mgmtvm @adminvm               allow target=dom0
mgmtvm @tag:created-by-mgmtvm allow target=dom0
mgmtvm mgmtvm                 allow target=dom0
```

Create a policy file at `/etc/qubes/policy.d/30-ansible.policy` with the 
following content:
```
admin.vm.Create.AppVM        * mgmtvm dom0                   allow
admin.vm.Create.StandaloneVM * mgmtvm dom0                   allow
admin.vm.Create.TemplateVM   * mgmtvm dom0                   allow
admin.vm.Remove              * mgmtvm @tag:created-by-mgmtvm allow target=dom0
```

## License

This project is licensed under the GPLv3+ license. Please see the [LICENSE](LICENSE) file for the full license text.
