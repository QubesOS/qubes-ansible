VERSION := $(shell cat version)

install-common:
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/connection
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/modules
	install -m 644 plugins/modules/qubesos.py $(DESTDIR)/usr/share/ansible/plugins/modules/qubesos.py
	install -m 644 plugins/connection/qubes.py $(DESTDIR)/usr/share/ansible/plugins/connection/qubes.py

install-dom0:
	mkdir -p $(DESTDIR)/usr/lib/qubes/
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/callback
	mkdir -p $(DESTDIR)/usr/share/ansible/plugins/strategy
	install -m 644 plugins/callback/qubesos_strategy_guard.py $(DESTDIR)/usr/share/ansible/plugins/callback/qubesos_strategy_guard.py
	install -m 644 plugins/strategy/qubes_proxy.py $(DESTDIR)/usr/share/ansible/plugins/strategy/qubes_proxy.py
	install -m 755 update-ansible-default-strategy $(DESTDIR)/usr/lib/qubes/update-ansible-default-strategy

install-tests:
	mkdir -p $(DESTDIR)/usr/share/ansible/tests/qubes
	install -m 644 tests/qubes/*.py $(DESTDIR)/usr/share/ansible/tests/qubes/
	install -m 644 tests/*.cfg $(DESTDIR)/usr/share/ansible/tests/

install-vm:
	mkdir -p $(DESTDIR)/etc/qubes-rpc/
	install -m 755 qubes-rpc/qubes.AnsibleVM $(DESTDIR)/etc/qubes-rpc/qubes.AnsibleVM

install-all: install-common install-dom0 install-tests install-vm
