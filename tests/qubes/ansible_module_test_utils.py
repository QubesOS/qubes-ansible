"""Compatibility helpers for testing Ansible modules."""

import contextlib
import json

try:
    from ansible.module_utils.testing import patch_module_args
except ImportError:
    from ansible.module_utils import basic
    from ansible.module_utils.common.text.converters import to_bytes

    @contextlib.contextmanager
    def patch_module_args(args=None):
        """Expose module arguments while testing older Ansible cores."""
        if not isinstance(args, (dict, type(None))):
            raise TypeError("The `args` arg must be a dict or None.")

        previous_args = basic._ANSIBLE_ARGS
        profile_present = hasattr(basic, "_ANSIBLE_PROFILE")
        previous_profile = getattr(basic, "_ANSIBLE_PROFILE", None)
        basic._ANSIBLE_ARGS = to_bytes(
            json.dumps({"ANSIBLE_MODULE_ARGS": args or {}})
        )
        if profile_present:
            basic._ANSIBLE_PROFILE = "legacy"

        try:
            yield
        finally:
            basic._ANSIBLE_ARGS = previous_args
            if profile_present:
                basic._ANSIBLE_PROFILE = previous_profile
