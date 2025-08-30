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

Using this plugin ensures dom0 isolation from untrusted Ansible data (see https://github.com/QubesOS/qubes-issues/issues/10030).

__NOTE__ - this strategy is set as the default on dom0.

## Installation

### AdminVM (dom0)

Install the following package: ``qubes-ansible-dom0``

### Management DVM

The package ``qubes-ansible-vm`` must be installed on templates used by your qubes management DVM 
(``default-mgmt-dvm`` by default).

## Usage

``qubes`` and ``qubes_proxy`` plugins work out of the box when installed using 
RPM. The strategy plugin will read the value of the ``hosts`` field 
in your playbooks and:
  - run the play locally when ``localhost`` is present in the list (dom0 management / ``qubesos`` module usage)
  - proxify play execution through the target disposable management VM that will automatically use the ``qubes`` connection plugin to run the tasks on the target

See the [examples](EXAMPLES.md) for sample playbooks and role tasks demonstrating common usage scenarios.

## License

This project is licensed under the GPLv3+ license. Please see the [LICENSE](LICENSE) file for the full license text.
