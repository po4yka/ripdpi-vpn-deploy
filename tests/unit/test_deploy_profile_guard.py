"""Tests for scripts/check-deploy-profile.py — the role-tier deploy guard.

Verifies the live repo is clean and that every violation class the guard
exists to catch (research role in a family profile, inherited-from-all.yml
enable, missing allowlist opt-in, forbidden override in a family profile,
manifest drift, unknown toggle) produces a finding.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-deploy-profile.py"

_spec = importlib.util.spec_from_file_location("check_deploy_profile", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


# ---------------------------------------------------------------------------
# Live repo
# ---------------------------------------------------------------------------

def test_live_repo_is_clean():
    assert guard.check(REPO_ROOT) == []


def test_live_manifest_covers_every_role():
    tiers = yaml.safe_load((REPO_ROOT / "ansible" / "role-tiers.yml").read_text())["tiers"]
    on_disk = {p.name for p in (REPO_ROOT / "ansible" / "roles").iterdir() if p.is_dir()}
    assert set(tiers) == on_disk


def test_live_family_profile_list_includes_explicit_profiles():
    manifest = yaml.safe_load((REPO_ROOT / "ansible" / "role-tiers.yml").read_text())
    family_profiles = set(manifest["family_profiles"])
    assert {
        "group_vars/vpn-p0-minimal.yml",
        "group_vars/vpn-family-standard.yml",
        "group_vars/vpn-device-full.yml",
        "group_vars/vpn-p1-web.yml",
        "group_vars/vpn-p2-udp.yml",
        "group_vars/vpn-p0.yml",
        "group_vars/vpn-p1p2.yml",
        "group_vars/vpn-fullstack.yml",
    }.issubset(family_profiles)
    assert "group_vars/vpn-lab.yml" not in family_profiles


def test_live_explicit_profile_surfaces_are_locked():
    group_vars = REPO_ROOT / "ansible" / "group_vars"
    minimal = yaml.safe_load((group_vars / "vpn-p0-minimal.yml").read_text())["vpn"]
    standard = yaml.safe_load((group_vars / "vpn-family-standard.yml").read_text())["vpn"]
    device_full = yaml.safe_load((group_vars / "vpn-device-full.yml").read_text())["vpn"]
    p1_web_data = yaml.safe_load((group_vars / "vpn-p1-web.yml").read_text())
    p1_web = p1_web_data["vpn"]
    p2_udp = yaml.safe_load((group_vars / "vpn-p2-udp.yml").read_text())["vpn"]
    lab = yaml.safe_load((group_vars / "vpn-lab.yml").read_text())

    assert minimal["enable_xray_reality"] is True
    assert minimal["enable_nginx_xhttp"] is False
    assert minimal["enable_hysteria"] is False
    assert minimal["enable_amneziawg"] is False

    assert standard["enable_xray_reality"] is True
    assert standard["enable_nginx_xhttp"] is True
    assert standard["enable_hysteria"] is True
    assert standard["enable_amneziawg"] is False

    assert device_full["enable_xray_reality"] is True
    assert device_full["enable_nginx_xhttp"] is True
    assert device_full["enable_hysteria"] is True
    assert device_full["enable_amneziawg"] is True

    assert p1_web["enable_xray_reality"] is False
    assert p1_web["enable_nginx_xhttp"] is True
    assert p1_web["enable_hysteria"] is False
    assert p1_web["enable_amneziawg"] is False
    assert p1_web_data["nginx_xhttp_public_port"] == 443

    assert p2_udp["enable_xray_reality"] is False
    assert p2_udp["enable_nginx_xhttp"] is False
    assert p2_udp["enable_hysteria"] is True
    assert p2_udp["enable_amneziawg"] is True

    assert lab["allow_research_roles"] == []
    assert lab["vpn"]["enable_split_hop_egress"] is False
    assert lab["vpn"]["enable_hysteria_realm"] is False
    assert lab["vpn"]["enable_dns_morph_bridge"] is False


# ---------------------------------------------------------------------------
# Synthetic repo harness
# ---------------------------------------------------------------------------

MANIFEST = {
    "tiers": {
        "baseline": "core",
        "xray": "core",
        "honeypot": "tactical",
        "split-hop-egress": "research",
        "hysteria-realm": "research",
        "cascade-ingress": "exception",
    },
    "toggle_role_map": {
        "enable_xray_reality": "xray",
        "enable_honeypot": "honeypot",
        "enable_split_hop_egress": "split-hop-egress",
        "enable_hysteria_realm": "hysteria-realm",
        "enable_cascade_ingress": "cascade-ingress",
    },
    "family_profiles": [
        "group_vars/all.yml",
        "group_vars/vpn-p0-minimal.yml",
        "group_vars/vpn-family-standard.yml",
        "group_vars/vpn-device-full.yml",
        "group_vars/vpn-fullstack.yml",
    ],
}

ALL_OFF = {
    "enable_xray_reality": True,
    "enable_honeypot": False,
    "enable_split_hop_egress": False,
    "enable_hysteria_realm": False,
    "enable_cascade_ingress": False,
}


def _make_repo(tmp_path: Path, *, manifest=None, all_yml=None, extra=None) -> Path:
    """Build a minimal ansible/ tree. `extra` maps rel-path -> yaml dict."""
    ans = tmp_path / "ansible"
    (ans / "roles").mkdir(parents=True)
    for role in (manifest or MANIFEST)["tiers"]:
        (ans / "roles" / role).mkdir()
    (ans / "role-tiers.yml").write_text(yaml.safe_dump(manifest or MANIFEST))
    gv = ans / "group_vars"
    gv.mkdir()
    for rel in (manifest or MANIFEST)["family_profiles"]:
        p = ans / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump({"vpn": all_yml or ALL_OFF}))
    for rel, data in (extra or {}).items():
        p = ans / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(data))
    return tmp_path


def test_clean_synthetic_repo_passes(tmp_path):
    assert guard.check(_make_repo(tmp_path)) == []


def test_security_controls_do_not_participate_in_role_tier_guard(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-fullstack.yml": {
            "vpn": ALL_OFF,
            "security_controls": {
                "ssh_strict": True,
                "ssh_prune_moduli": True,
                "fail2ban": False,
            },
        },
    })
    assert guard.check(root) == []


def test_research_role_enabled_in_family_profile_fails(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-fullstack.yml": {"vpn": {**ALL_OFF, "enable_split_hop_egress": True}},
    })
    findings = guard.check(root)
    assert any("split-hop-egress" in f and "family profile" in f for f in findings)


def test_research_enabled_via_all_yml_inheritance_fails(tmp_path):
    # all.yml turns it on; vpn-fullstack.yml does not restate it -> inherits true.
    root = _make_repo(tmp_path, all_yml={**ALL_OFF, "enable_hysteria_realm": True})
    findings = guard.check(root)
    # Flagged in BOTH all.yml and the inheriting profile.
    assert sum("hysteria-realm" in f for f in findings) >= 2


def test_research_in_lab_profile_without_allowlist_fails(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-lab.yml": {"vpn": {**ALL_OFF, "enable_split_hop_egress": True}},
    })
    findings = guard.check(root)
    assert any("split-hop-egress" in f and "allow_research_roles" in f for f in findings)


def test_research_in_lab_profile_with_allowlist_passes(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-lab.yml": {
            "vpn": {**ALL_OFF, "enable_split_hop_egress": True},
            "allow_research_roles": ["split-hop-egress"],
        },
    })
    assert guard.check(root) == []


def test_exception_enabled_without_per_host_allowlist_fails(tmp_path):
    root = _make_repo(tmp_path, extra={
        "host_vars/candidate-a.yml": {"vpn": {"enable_cascade_ingress": True}},
    })

    findings = guard.check(root)

    assert any("cascade-ingress" in finding and "allow_exception_roles" in finding for finding in findings)


def test_exception_enabled_with_exact_per_host_allowlist_passes(tmp_path):
    root = _make_repo(tmp_path, extra={
        "host_vars/candidate-a.yml": {
            "vpn": {"enable_cascade_ingress": True},
            "allow_exception_roles": ["cascade-ingress"],
        },
    })

    assert guard.check(root) == []


def test_exception_group_allowlist_cannot_replace_per_host_authorization(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-lab.yml": {
            "vpn": {**ALL_OFF, "enable_cascade_ingress": True},
            "allow_exception_roles": ["cascade-ingress"],
        },
    })

    findings = guard.check(root)

    assert any("only in host_vars" in finding for finding in findings)


def test_bare_exception_group_allowlist_is_forbidden(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-lab.yml": {
            "vpn": ALL_OFF,
            "allow_exception_roles": ["cascade-ingress"],
        },
    })

    findings = guard.check(root)

    assert any("group-scoped jurisdiction authorization is forbidden" in finding for finding in findings)


def test_exception_role_and_allowlist_are_forbidden_in_family_profile(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-fullstack.yml": {
            "vpn": {**ALL_OFF, "enable_cascade_ingress": True},
            "allow_exception_roles": ["cascade-ingress"],
        },
    })

    findings = guard.check(root)

    assert any("EXCEPTION role 'cascade-ingress'" in finding and "family profile" in finding for finding in findings)
    assert any("must not set allow_exception_roles" in finding for finding in findings)


def test_allowlist_does_not_cover_a_second_research_role(tmp_path):
    # Allowlisting one research role must not implicitly allow another.
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-lab.yml": {
            "vpn": {**ALL_OFF, "enable_split_hop_egress": True, "enable_hysteria_realm": True},
            "allow_research_roles": ["split-hop-egress"],
        },
    })
    findings = guard.check(root)
    assert any("hysteria-realm" in f for f in findings)
    assert not any("split-hop-egress" in f for f in findings)


def test_override_forbidden_in_family_profile(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-fullstack.yml": {
            "vpn": ALL_OFF,
            "allow_research_roles": ["split-hop-egress"],
        },
    })
    findings = guard.check(root)
    assert any("must not set allow_research_roles" in f for f in findings)


def test_host_vars_research_enable_is_scanned(tmp_path):
    root = _make_repo(tmp_path, extra={
        "host_vars/node-b.yml": {"vpn": {"enable_split_hop_egress": True}},
    })
    findings = guard.check(root)
    assert any("split-hop-egress" in f and "host_vars" in f for f in findings)


def test_manifest_missing_tier_for_ondisk_role_fails(tmp_path):
    # Build the full repo (creates the honeypot role dir), then rewrite the
    # manifest to drop honeypot's tier — leaving an orphaned role dir.
    root = _make_repo(tmp_path)
    bad = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in MANIFEST.items()}
    bad["tiers"] = {k: v for k, v in MANIFEST["tiers"].items() if k != "honeypot"}
    (root / "ansible" / "role-tiers.yml").write_text(yaml.safe_dump(bad))
    findings = guard.check(root)
    assert any("honeypot" in f and "no tier" in f for f in findings)


def test_unknown_toggle_fails(tmp_path):
    root = _make_repo(tmp_path, extra={
        "group_vars/vpn-fullstack.yml": {"vpn": {**ALL_OFF, "enable_quantum_tunnel": True}},
    })
    findings = guard.check(root)
    assert any("enable_quantum_tunnel" in f for f in findings)


def test_invalid_tier_value_fails(tmp_path):
    bad = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in MANIFEST.items()}
    bad["tiers"] = {**MANIFEST["tiers"], "xray": "kore"}
    root = _make_repo(tmp_path, manifest=bad)
    findings = guard.check(root)
    assert any("invalid tier" in f for f in findings)
