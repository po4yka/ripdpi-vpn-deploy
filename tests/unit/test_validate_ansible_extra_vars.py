"""Fail-closed coverage for live Ansible override files."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate-ansible-extra-vars.py"

spec = importlib.util.spec_from_file_location("validate_ansible_extra_vars", SCRIPT)
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def write_yaml(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "extra-vars.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_accepts_management_path_and_forwarding_overrides(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "ansible_host": "management.example.invalid",
            "ansible_port": 22,
            "firewall_forward_interface_contract": [
                {
                    "name": "real-vps-awg-evidence",
                    "input_interface": "awg-evidence0",
                    "output_interface": "eth0",
                }
            ],
        },
    )

    validator.validate(path)


@pytest.mark.parametrize('policy,accepted', [
    ({}, True),
    ({'address': '100.64.0.2', 'sources': ['100.64.0.3']}, True),
    ({'address': '100.64.0.2', 'sources': ['0.0.0.0/0']}, False),
    ({'address': '192.0.2.2', 'sources': ['100.64.0.3']}, False),
    ({'address': '100.64.0.2', 'sources': []}, False),
    ({'address': '100.64.0.2', 'sources': ['100.64.0.3'] * 2}, False),
    ({'address': '100.64.0.2', 'sources': ['100.64.0.3'], 'port': 443}, False),
    ('100.64.0.2', False),
])
def test_collector_override_uses_bounded_private_contract(tmp_path, policy, accepted):
    path = write_yaml(tmp_path, {'firewall_tailnet_collector_ingress': policy})
    if accepted:
        validator.validate(path)
    else:
        with pytest.raises(ValueError, match='collector-invalid-tailnet-ingress'):
            validator.validate(path)


@pytest.mark.parametrize('root,snapshot,accepted', [
    ('/run/vpn-acme-restore-a1b2c3d4', 'a'*64, True),
    ('/etc', 'a'*64, False), ('/run/vpn-acme-restore-a1b2c3d4/../other', 'a'*64, False),
    ('/run/vpn-acme-restore-a1b2c3d4', 'short-id', False),
    (None, 'a'*64, False), ('/run/vpn-acme-restore-a1b2c3d4', None, False),
])
def test_native_cache_recovery_has_one_bounded_source_and_exact_snapshot(tmp_path, root, snapshot, accepted):
    path = write_yaml(tmp_path, {'hysteria_acme_restore_root': root, 'hysteria_acme_restore_snapshot_id': snapshot})
    if accepted:
        validator.validate(path)
    else:
        with pytest.raises(ValueError, match='native ACME recovery'):
            validator.validate(path)


@pytest.mark.parametrize(
    "key",
    [
        "vpn_service_address",
        "xray",
        "vpn",
        "xray_probe_client",
        "observability_agent",
    ],
)
def test_rejects_data_plane_and_protocol_overrides(tmp_path: Path, key: str) -> None:
    path = write_yaml(tmp_path, {key: "untrusted.example.invalid"})

    with pytest.raises(ValueError, match="non-allowlisted"):
        validator.validate(path)


def test_accepts_owned_public_site_and_detects_content_changes(tmp_path):
    site = tmp_path / "site"
    site.mkdir(mode=0o700)
    (site / "404.html").write_bytes(b"ordinary missing page")
    (site / "index.html").write_bytes(b"public article")
    validator.validate(write_yaml(tmp_path, {"nginx_xhttp_public_site_dir": str(site)}))
    entries, before = validator.read_site(str(site))
    assert entries["index.html"] == b"public article"
    (site / "index.html").write_bytes(b"changed article")
    assert validator.read_site(str(site))[1] != before


@pytest.mark.parametrize("fault", ["relative", "missing-404", "root-link", "parent-link",
                                  "file-link", "hardlink", "fifo", "writable", "hidden"])
def test_rejects_unsafe_public_site_tree(tmp_path, fault):
    site = tmp_path / "site"
    site.mkdir(mode=0o700)
    error = site / "404.html"
    error.write_bytes(b"missing page")
    if fault == "relative":
        value = "relative-site"
    elif fault == "missing-404":
        error.unlink()
        value = str(site)
    elif fault in {"root-link", "parent-link"}:
        link = tmp_path / "link"
        link.symlink_to(site if fault == "root-link" else tmp_path, target_is_directory=True)
        value = str(link if fault == "root-link" else link / "site")
    else:
        value = str(site)
        if fault == "file-link":
            (site / "article.html").symlink_to(error)
        elif fault == "hardlink":
            os.link(error, site / "article.html")
        elif fault == "fifo":
            os.mkfifo(site / "pipe")
        elif fault == "writable":
            error.chmod(0o666)
        elif fault == "hidden":
            (site / ".env").write_bytes(b"private data")
    with pytest.raises(ValueError, match="public site"):
        validator.validate(write_yaml(tmp_path, {"nginx_xhttp_public_site_dir": value}))


def test_rejects_foreign_owned_public_site(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir(mode=0o700)
    (site / "404.html").write_bytes(b"missing page")
    uid = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: uid + 1)
    with pytest.raises(ValueError, match="public site"):
        validator.read_site(str(site))


def test_rejects_oversized_public_site_file(tmp_path):
    site = tmp_path / "site"
    site.mkdir(mode=0o700)
    with (site / "404.html").open("wb") as stream:
        stream.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="public site"):
        validator.read_site(str(site))


@pytest.mark.parametrize("limit", ["entries", "depth", "total-bytes"])
def test_public_site_tree_limits_are_enforced(tmp_path, limit):
    site = tmp_path / "site"
    site.mkdir(mode=0o700)
    (site / "404.html").write_bytes(b"missing page")
    if limit == "entries":
        for i in range(1024):
            (site / f"page-{i}.html").write_bytes(b"page")
    elif limit == "depth":
        child = site
        for _ in range(17):
            child = child / "nested"
            child.mkdir(mode=0o700)
    else:
        for i in range(4):
            with (site / f"asset-{i}").open("wb") as stream:
                stream.truncate(4 * 1024 * 1024)
    with pytest.raises(ValueError, match="limit"):
        validator.read_site(str(site))


@pytest.mark.parametrize("document", [{}, [], None])
def test_rejects_empty_or_non_mapping_documents(
    tmp_path: Path, document: object
) -> None:
    path = write_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="non-empty mapping"):
        validator.validate(path)


@pytest.mark.parametrize(
    "entry",
    [
        {
            "name": "real-vps-awg-evidence",
            "input_interface": 'awg0"; flush ruleset #',
            "output_interface": "eth0",
        },
        {
            "name": "real-vps-awg-evidence\nflush ruleset",
            "input_interface": "awg0",
            "output_interface": "eth0",
        },
        {
            "name": "real-vps-awg-evidence",
            "input_interface": "awg0",
        },
        {
            "name": "real-vps-awg-evidence",
            "input_interface": "awg0",
            "output_interface": "eth0",
            "unexpected": "value",
        },
    ],
)
def test_rejects_unsafe_or_malformed_forwarding_entries(
    tmp_path: Path, entry: dict[str, str]
) -> None:
    path = write_yaml(tmp_path, {"firewall_forward_interface_contract": [entry]})

    with pytest.raises(ValueError):
        validator.validate(path)


@pytest.mark.parametrize(
    "value",
    [
        "https://decoy-site.example",
        "https://edge.decoy-site.example",
    ],
)
def test_accepts_https_origin_decoy_overrides(tmp_path: Path, value: str) -> None:
    validator.validate(write_yaml(tmp_path, {"public_site_canonical_url": value}))


@pytest.mark.parametrize(
    "value",
    [
        "http://decoy-site.example",
        "decoy-site.example",
        "https://decoy-site.example/",
        "https://decoy-site.example/about.html",
        "https://decoy site.example",
        443,
    ],
)
def test_rejects_malformed_decoy_overrides(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValueError):
        validator.validate(write_yaml(tmp_path, {"public_site_canonical_url": value}))


def exposure_config(tmp_path: Path, *, mode: str = "canary") -> dict[str, object]:
    return {"mode": mode, "artifact": str(tmp_path / "reviewed-policy.json"),
            "trusted_key": str(tmp_path / "reviewed-key.pem"),
            "trusted_key_sha256": "a" * 64, "source_id": "reviewed-source",
            "promotion_approved": mode in {"canary", "enforce"},
            "promotion_digest": "b" * 64 if mode in {"canary", "enforce"} else "",
            "authorized_hosts": ["node-one"] if mode in {"canary", "enforce"} else []}


@pytest.mark.parametrize("mode", ["log_only", "canary", "enforce"])
def test_accepts_typed_network_exposure_override(tmp_path: Path, mode: str) -> None:
    validator.validate(write_yaml(tmp_path, {
        "network_exposure_gate": exposure_config(tmp_path, mode=mode)}))


@pytest.mark.parametrize("field,value", [
    ("mode", "observe"), ("artifact", "relative.json"), ("trusted_key", "relative.pem"),
    ("trusted_key_sha256", "A" * 64), ("source_id", "Invalid Source"),
    ("promotion_approved", 1), ("promotion_digest", "short"),
    ("authorized_hosts", ["node-*"]),
])
def test_rejects_malformed_network_exposure_override(
        tmp_path: Path, field: str, value: object) -> None:
    config = exposure_config(tmp_path)
    config[field] = value
    with pytest.raises(ValueError, match="network_exposure_gate"):
        validator.validate(write_yaml(tmp_path, {"network_exposure_gate": config}))


def test_disabled_network_exposure_override_contains_no_external_inputs(tmp_path: Path) -> None:
    config = exposure_config(tmp_path, mode="canary")
    config.update(mode="disabled", artifact="", trusted_key="", trusted_key_sha256="",
                  source_id="", promotion_approved=False, promotion_digest="",
                  authorized_hosts=[])
    validator.validate(write_yaml(tmp_path, {"network_exposure_gate": config}))


def test_rejects_duplicate_network_exposure_fields(tmp_path: Path) -> None:
    path = tmp_path / "extra-vars.yml"
    path.write_text(
        "network_exposure_gate:\n  mode: log_only\n  mode: enforce\n"
        "  artifact: /private/artifact.json\n  trusted_key: /private/key.pem\n"
        f"  trusted_key_sha256: {'a' * 64}\n  source_id: reviewed-source\n"
        "  promotion_approved: false\n  promotion_digest: ''\n  authorized_hosts: []\n")
    with pytest.raises(ValueError, match="duplicate"):
        validator.validate(path)


@pytest.mark.parametrize('changes', [{}, {'intent_sha256': 'invalid'}, {'operation_id': 'INVALID'}, {'extra': True}])
def test_revocation_intent_is_strictly_typed(tmp_path, changes):
    value = {'operation_id': '11111111-1111-4111-8111-111111111111', 'intent_sha256': 'a'*64}
    value.update(changes)
    path = write_yaml(tmp_path, {'vpn_device_revocation': value})
    if changes:
        with pytest.raises(ValueError, match='exact operation'):
            validator.validate(path)
    else:
        validator.validate(path)


@pytest.mark.parametrize('value', [False, 'true', 1, None])
def test_retained_publisher_override_rejects_untyped_flag(tmp_path, value):
    with pytest.raises(ValueError, match='retained publisher'):
        validator.validate(write_yaml(tmp_path, {'vpn_device_retained_publisher': value}))


def test_retained_publisher_override_requires_revocation(tmp_path):
    with pytest.raises(ValueError, match='revocation authority'):
        validator.validate(write_yaml(tmp_path, {'vpn_device_retained_publisher': True}))
    validator.validate(write_yaml(tmp_path, {'vpn_device_retained_publisher': True,
        'vpn_device_revocation': {'operation_id': '11111111-1111-4111-8111-111111111111', 'intent_sha256': 'a'*64}}))
