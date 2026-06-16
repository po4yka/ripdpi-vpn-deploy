"""Minimal pyinfra inventory for the read-only audit pilot.

The existing rendered Ansible inventory is INI plus Ansible-specific group_vars. This pilot intentionally avoids translating that contract until pyinfra has a clearer role in the project. Provide targets explicitly through PYINFRA_HOSTS.
"""

from __future__ import annotations

import os


def _host_data() -> dict[str, int | str]:
    data: dict[str, int | str] = {}
    if ssh_user := os.environ.get("PYINFRA_SSH_USER"):
        data["ssh_user"] = ssh_user
    if ssh_key := os.environ.get("PYINFRA_SSH_KEY"):
        data["ssh_key"] = os.path.expanduser(ssh_key)
    if ssh_port := os.environ.get("PYINFRA_SSH_PORT"):
        data["ssh_port"] = int(ssh_port)
    return data


hosts = [host.strip() for host in os.environ.get("PYINFRA_HOSTS", "").split(",") if host.strip()]
if not hosts:
    raise SystemExit("PYINFRA_HOSTS is required, for example: PYINFRA_HOSTS=203.0.113.10 make pyinfra-audit")

host_data = _host_data()
vpn = [(host, host_data.copy()) if host_data else host for host in hosts]
