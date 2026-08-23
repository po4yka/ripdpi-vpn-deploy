"""The four provider roots must declare the same legacy listener set."""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("upcloud", "hetzner", "vultr", "scaleway")

# The rotation-sensitive fixed ports inside `legacy_public_listeners`.
# nginx-xhttp's port is a variable on every root and is checked against the
# Ansible default separately.
EXPECTED_FIXED_LISTENERS = [
    ('"xray"', '"tcp"', "443"),
    ('"xray-fallback"', '"tcp"', "2053"),
    ('"public-site-http"', '"tcp"', "80"),
    ('"amneziawg"', '"udp"', "51820"),
    ('"hysteria"', '"udp"', "443"),
]

_ENTRY = re.compile(
    r'\{\s*name\s*=\s*(?P<name>"[^"]+")\s*,\s*protocol\s*=\s*(?P<protocol>"[^"]+")\s*,'
    r"\s*port\s*=\s*(?P<port>\d+)\s*,"
)


def _entries(root: str) -> list[tuple[str, str, str]]:
    return [
        (m.group("name"), m.group("protocol"), m.group("port"))
        for m in _ENTRY.finditer(root)
    ]


def test_provider_roots_declare_identical_fixed_listener_sets() -> None:
    seen: dict[str, list[tuple[str, str, str]]] = {}
    for provider in PROVIDERS:
        source = (REPO_ROOT / f"terraform/providers/{provider}/listeners.tf").read_text()
        seen[provider] = _entries(source)

    reference = seen["upcloud"]
    for provider, entries in seen.items():
        assert entries == reference, (
            f"{provider} listeners.tf drifted from upcloud; rotate the fixed "
            "ports in lockstep across all four roots"
        )
        for expected in EXPECTED_FIXED_LISTENERS:
            assert expected in entries, f"{provider}: missing {expected}"


def test_nginx_xhttp_listener_port_matches_ansible_default() -> None:
    group_vars = {}
    for path in (REPO_ROOT / "ansible/group_vars").glob("*.yml"):
        import yaml

        document = yaml.safe_load(path.read_text()) or {}
        if "nginx_xhttp_public_port" in document:
            group_vars[path.name] = document["nginx_xhttp_public_port"]

    assert group_vars, "nginx_xhttp_public_port disappeared from group_vars"
    # all.yml default 8443; direct-only cohorts override to 443. Anything
    # else would silently desync the four provider roots.
    assert set(group_vars.values()) <= {8443, 443}
