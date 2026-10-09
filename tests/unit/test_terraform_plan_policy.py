"""Real Conftest policy and evaluator regression coverage."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/terraform-plan-policy.py"
SPEC = importlib.util.spec_from_file_location("terraform_plan_policy", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _plan(kind: str, after: dict) -> dict:
    return {
        "variables": {
            "ssh_port": {"value": 2222},
            "allowed_ssh_cidrs": {"value": ["192.0.2.0/24"]},
            "additional_public_ip": {"value": False},
        },
        "resource_changes": [{
            "address": f"{kind}.test", "type": kind,
            "change": {"actions": ["create"], "after": after},
        }],
    }


def _run(tmp_path: Path, doc: dict) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    return subprocess.run(
        ["python3", str(SCRIPT), str(path)], text=True, capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("family", ["0.0.0.0/0", "::/0", "192.0.2.1/0"])
@pytest.mark.parametrize("selector", ["2222", "2200-2300", "2222-2300", "2200-2222"])
def test_world_ssh_singletons_and_inclusive_ranges_fail(tmp_path: Path, family: str, selector: str) -> None:
    result = _run(tmp_path, _plan("hcloud_firewall", {"rule": [{
        "direction": "in", "protocol": "tcp", "port": selector,
        "source_ips": [family],
    }]}))
    assert result.returncode == 1
    assert "terraform.policy.admin_port" in result.stderr


@pytest.mark.parametrize("kind,after", [
    ("upcloud_firewall_rules", {"firewall_rule": [{
        "direction": "in", "action": "accept", "protocol": "tcp",
        "destination_port_start": "2200", "destination_port_end": "2300",
        "source_address_start": "", "source_address_end": "",
    }]}),
    ("vultr_firewall_rule", {
        "protocol": "tcp", "port": "2200:2300", "subnet": "::", "subnet_size": 0,
    }),
    ("scaleway_instance_security_group", {"inbound_rule": [{
        "action": "accept", "protocol": "TCP", "port_range": "2200-2300",
        "ip_range": "::/0",
    }]}),
])
def test_each_provider_range_shape_rejects_world_ssh(tmp_path: Path, kind: str, after: dict) -> None:
    result = _run(tmp_path, _plan(kind, after))
    assert result.returncode == 1
    assert "terraform.policy.admin_port" in result.stderr
    assert "terraform.policy.ssh_cidrs" in result.stderr


@pytest.mark.parametrize("selector,protocol,source", [
    ("2200-2300", "tcp", "192.0.2.0/24"),
    ("2200-2221", "tcp", "0.0.0.0/0"),
    ("2223-2300", "tcp", "::/0"),
    ("2222", "udp", "::/0"),
])
def test_restricted_and_adjacent_ranges_and_udp_pass(tmp_path: Path, selector: str, protocol: str, source: str) -> None:
    result = _run(tmp_path, _plan("hcloud_firewall", {"rule": [{
        "direction": "in", "protocol": protocol, "port": selector,
        "source_ips": [source],
    }]}))
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_primary_dual_stack_passes_without_secondary_opt_in(tmp_path: Path) -> None:
    result = _run(tmp_path, _plan("upcloud_server", {"network_interface": [
        {"type": "public", "ip_address_family": "IPv4"},
        {"type": "public", "ip_address_family": "IPv6"},
        {"type": "utility"},
    ]}))
    assert result.returncode == 0, result.stderr


def test_extra_ipv4_still_requires_opt_in(tmp_path: Path) -> None:
    doc = _plan("upcloud_server", {"network_interface": [
        {"type": "public", "ip_address_family": "IPv4"},
        {"type": "public", "ip_address_family": "IPv4"},
        {"type": "public", "ip_address_family": "IPv6"},
    ]})
    assert _run(tmp_path, doc).returncode == 1
    doc["variables"]["additional_public_ip"]["value"] = True
    assert _run(tmp_path, doc).returncode == 0


def test_rejection_does_not_print_plan_content(tmp_path: Path) -> None:
    marker = "synthetic-private-value"
    result = _run(tmp_path, _plan("upcloud_server", {"user_data": f"token: {marker}"}))
    assert result.returncode == 1
    assert "no_secrets_in_user_data" in result.stderr
    assert marker not in result.stdout + result.stderr


@pytest.mark.parametrize("kind,after", [
    ("upcloud_firewall_rules", {"firewall_rule": [{
        "direction": "in", "action": "accept", "protocol": "tcp",
        "destination_port_start": "", "destination_port_end": "",
        "source_address_start": "", "source_address_end": "",
    }]}),
    ("scaleway_instance_security_group", {"inbound_rule": [{
        "action": "accept", "protocol": "ANY", "port": None,
        "port_range": None, "ip_range": "0.0.0.0/0",
    }]}),
    ("scaleway_instance_security_group", {"inbound_rule": [{
        "action": "accept", "protocol": "TCP", "port": 0,
        "port_range": "", "ip_range": None,
    }]}),
    ("hcloud_firewall", {"rule": [{
        "direction": "in", "protocol": "tcp", "port": "any",
        "source_ips": [],
    }]}),
    ("vultr_firewall_rule", {
        "protocol": "tcp", "port": "", "subnet": "0.0.0.0", "subnet_size": 0,
    }),
    ("hcloud_firewall", {"rule": [{
        "direction": "in", "protocol": "tcp", "port": "not-a-selector",
        "source_ips": ["::/0"],
    }]}),
])
def test_omitted_all_port_and_uncertain_selectors_refuse(tmp_path: Path, kind: str, after: dict) -> None:
    result = _run(tmp_path, _plan(kind, after))
    assert result.returncode == 1
    assert "terraform.policy.admin_port" in result.stderr


@pytest.mark.parametrize("end,expected", [("192.0.2.255", 0), ("255.255.255.255", 1)])
def test_upcloud_entire_source_interval_must_be_allowed(tmp_path: Path, end: str, expected: int) -> None:
    result = _run(tmp_path, _plan("upcloud_firewall_rules", {"firewall_rule": [{
        "direction": "in", "action": "accept", "protocol": "tcp",
        "destination_port_start": "2222", "destination_port_end": "2222",
        "source_address_start": "192.0.2.0", "source_address_end": end,
    }]}))
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize("stdout,code", [
    ("[]", 0), ("not-json", 0), ("{}", 0),
    ('[{"namespace":"terraform.policy.test","successes":0}]', 0),
    ('[{"namespace":"terraform.policy.test","successes":true}]', 0),
    ('[{"namespace":"terraform.policy.test","successes":1,"failures":{}}]', 0),
    ('[{"namespace":"terraform.policy.test","successes":1}]', 2),
    ('[{"namespace":"terraform.policy.test","successes":1,"exceptions":[{"msg":"failed"}]}]', 0),
])
def test_invalid_empty_and_failed_evaluation_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: str, code: int) -> None:
    monkeypatch.setattr(MODULE.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], code, stdout, "synthetic-private-value"))
    assert MODULE.evaluate(tmp_path / "plan.json") == 1
