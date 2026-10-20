"""The AWG role must not replace the host resolver that baseline manages."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "amneziawg"


def _apt_packages(tasks):
    for task in tasks:
        for nested in ("block", "rescue", "always"):
            yield from _apt_packages(task.get(nested) or [])
        module = task.get("ansible.builtin.apt") or task.get("apt") or {}
        names = module.get("name") or module.get("pkg") or []
        yield from [names] if isinstance(names, str) else names


def test_role_never_installs_resolvconf():
    # On Debian 13, systemd-resolved conflicts with resolvconf: apt removes the
    # resolver that baseline configures and host DNS stops working.
    for path in sorted((ROLE / "tasks").glob("*.yml")):
        tasks = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        assert "resolvconf" not in set(_apt_packages(tasks)), path.name


def test_server_interfaces_never_request_awg_quick_dns():
    # awg-quick calls resolvconf only for DNS= in the interface it brings up.
    for template in ROLE.glob("templates/*.conf.j2"):
        lines = template.read_text(encoding="utf-8").splitlines()
        assert not [line for line in lines if line.replace(" ", "").startswith("DNS=")]
