"""Local checks of the field-analytics staging acceptance harness.

The staging and device run itself needs operator authority; these tests run
the block script against stub terraform and ssh binaries and the evidence
checker against saved artifacts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BLOCK = ROOT / "scripts/field-analytics-block.sh"
EVIDENCE = ROOT / "scripts/field-analytics-evidence.py"
SSH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$SSH_LOG"
cat > "$SSH_LOG.stdin"
"""


def _block(tmp_path: Path, verb: str, **env: str) -> subprocess.CompletedProcess:
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    (stubs / "ssh").write_text(SSH_STUB)
    (stubs / "ssh").chmod(0o755)
    environment = {**os.environ, "PATH": f"{stubs}:{ROOT / 'tests/stubs/bin'}:{os.environ['PATH']}",
                   "SSH_LOG": str(tmp_path / "ssh.log"), "HOME": str(tmp_path),
                   "AUDIT_LOG_FILE": str(tmp_path / "audit.log.age"), "ENV": "staging", **env}
    return subprocess.run(["bash", str(BLOCK), verb], env=environment, capture_output=True, text=True, timeout=30,
                          check=False)


@pytest.mark.parametrize(("env", "rule"), [
    ({"L4": "tcp", "PORT": "443", "MODE": "drop"}, "    tcp dport 443 counter drop\n"),
    ({"L4": "udp", "PORT": "8443", "MODE": "drop", "SOURCE": "203.0.113.7"},
     "    ip saddr 203.0.113.7 udp dport 8443 counter drop\n"),
    ({"L4": "tcp", "PORT": "443", "MODE": "rst", "SOURCE": "2001:db8::/64"},
     "    ip6 saddr 2001:db8::/64 tcp dport 443 counter reject with tcp reset\n"),
])
def test_plan_renders_one_rule_in_the_private_table(tmp_path, env, rule):
    result = _block(tmp_path, "plan", **env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "table inet ripdpi_acceptance\ndelete table inet ripdpi_acceptance\n"
        "table inet ripdpi_acceptance {\n  chain input {\n    type filter hook input priority -10; policy accept;\n"
        + rule + "  }\n}\n")
    assert not (tmp_path / "ssh.log").exists()


@pytest.mark.parametrize("env", [
    {"L4": "udp", "PORT": "443", "MODE": "rst"},
    {"L4": "tcp", "PORT": "22", "MODE": "drop"},
    {"L4": "tcp", "PORT": "70000", "MODE": "drop"},
    {"L4": "icmp", "PORT": "443", "MODE": "drop"},
    {"L4": "tcp", "PORT": "443", "MODE": "drop", "SOURCE": "203.0.113.7; flush ruleset"},
    {"L4": "tcp", "PORT": "443", "MODE": "drop", "ENV": "prod"},
])
def test_unsafe_or_malformed_inputs_refuse_before_any_contact(tmp_path, env):
    result = _block(tmp_path, "block", APPLY="1", **env)
    assert result.returncode == 2
    assert not (tmp_path / "ssh.log").exists()


def test_block_without_apply_contacts_nothing(tmp_path):
    result = _block(tmp_path, "block", L4="tcp", PORT="443", MODE="drop")
    assert result.returncode == 0 and "plan only" in result.stdout
    assert not (tmp_path / "ssh.log").exists()


def test_apply_sends_the_planned_ruleset_and_unblock_deletes_the_whole_table(tmp_path):
    plan = _block(tmp_path, "plan", L4="tcp", PORT="443", MODE="rst").stdout
    block = _block(tmp_path, "block", APPLY="1", L4="tcp", PORT="443", MODE="rst")
    assert block.returncode == 0, block.stderr
    assert (tmp_path / "ssh.log.stdin").read_text() == plan.rstrip("\n")
    assert (tmp_path / "ssh.log").read_text().splitlines()[-1].endswith("deploy@198.51.100.10 sudo nft -f -")
    unblock = _block(tmp_path, "unblock", APPLY="1")
    assert unblock.returncode == 0, unblock.stderr
    remote = (tmp_path / "ssh.log").read_text().splitlines()[-1]
    assert "sudo nft delete table inet ripdpi_acceptance" in remote
    assert "! sudo nft list table inet ripdpi_acceptance" in remote


def _evidence(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EVIDENCE), *args], capture_output=True, text=True, timeout=30,
                          check=False)


@pytest.mark.parametrize(("server_ref", "at", "code"), [
    ("p2-hysteria2-upcloud-prod", "2026-11-19T11:05:00Z", 0),
    # Health observed at 11:00 with a 600-second TTL is unknown from 11:10.
    ("p2-hysteria2-upcloud-prod", "2026-11-19T11:10:00Z", 1),
    ("p0-reality-upcloud-prod", "2026-11-19T11:05:00Z", 1),
    ("missing-endpoint", "2026-11-19T11:05:00Z", 1),
])
def test_bundle_evidence_needs_fresh_degraded_or_down_health(server_ref, at, code):
    result = _evidence("bundle", str(ROOT / "contract/ripdpi-bundle.health-expired.json"),
                       "--server-ref", server_ref, "--at", at)
    assert result.returncode == code, result.stdout + result.stderr


def _vector(*metrics: dict, value: str = "12") -> dict:
    return {"status": "success", "data": {"resultType": "vector",
                                          "result": [{"metric": metric, "value": [1795000000, value]} for metric in metrics]}}


SERIES = {"__name__": "vpn_field_report_failures_total", "environment": "staging", "node": "vpn-sub",
          "protocol": "xhttp", "failure_stage": "tcp_reset", "network": "as64500"}


@pytest.mark.parametrize(("document", "code"), [
    (_vector(SERIES), 0),
    (_vector(SERIES, value="0"), 1),
    (_vector({**SERIES, "failure_stage": "tls_handshake"}), 1),
    (_vector({**SERIES, "node": ""}), 1),
    # An address in any label, or a label outside the contract, fails the privacy claim.
    (_vector(SERIES, {**SERIES, "failure_stage": "tls_handshake", "network": "198.51.100.23"}), 1),
    (_vector({**SERIES, "device": "phone-1"}), 1),
    ({"data": []}, 2),
])
def test_ingest_evidence_checks_the_series_and_its_privacy(tmp_path, document, code):
    path = tmp_path / "query.json"
    path.write_text(json.dumps(document))
    result = _evidence("ingest", str(path), "--protocol", "xhttp", "--stage", "tcp_reset")
    assert result.returncode == code, result.stdout + result.stderr


@pytest.mark.parametrize(("state", "network", "code"), [("active", "as64500", 0), ("suppressed", "as64500", 1),
                                                   ("active", "as64501", 1)])
def test_alert_evidence_needs_the_active_block_alert(tmp_path, state, network, code):
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps([{"labels": {"alertname": "FieldReportNetworkBlocked", "protocol": "xhttp",
                                            "network": network, "country": "ZZ"}, "status": {"state": state}}]))
    result = _evidence("alert", str(path), "--protocol", "xhttp", "--network", "as64500")
    assert result.returncode == code, result.stdout + result.stderr
    assert ("PASS" in result.stdout) is (code == 0)


@pytest.mark.parametrize(("state", "code"), [("firing", 0), ("pending", 1)])
def test_alert_evidence_reads_a_prometheus_alert_export(tmp_path, state, code):
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps({"status": "success", "data": {"alerts": [
        {"labels": {"alertname": "FieldReportNetworkBlocked", "protocol": "xhttp", "network": "as64500"}, "state": state}]}}))
    assert _evidence("alert", str(path), "--protocol", "xhttp", "--network", "as64500").returncode == code
