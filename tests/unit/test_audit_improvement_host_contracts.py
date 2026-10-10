"""Executable observation, private-listener and fresh audit-report boundaries."""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


endpoint = load(
    ROOT / "ansible/roles/monitoring/files/private_endpoint.py", "private_endpoint_test"
)
audit = load(
    ROOT / "ansible/roles/security_audit/files/lynis_collect.py", "lynis_collect_test"
)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("127.0.0.1:9100", "127.0.0.1:9100"),
        ("[::1]:09100", "[::1]:9100"),
        ("127.0.0.2:1234", "127.0.0.2:1234"),
    ],
)
def test_loopback_endpoint_normalization(value, expected):
    assert (
        endpoint.validate(
            {"endpoint": value, "approved_tailnet_addresses": [], "local_addresses": []}
        )["endpoint"]
        == expected
    )


@pytest.mark.parametrize(
    "value",
    [
        "0.0.0.0:9100",
        "[::]:9100",
        "192.0.2.1:9100",
        "10.0.0.1:9100",
        "localhost:9100",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "127.0.0.1:9100 --web.config.file=/tmp/config",
        '127.0.0.1:9100"',
        "100.64.0.2:9100",
    ],
)
def test_unapproved_endpoint_refuses(value):
    with pytest.raises(ValueError):
        endpoint.validate(
            {"endpoint": value, "approved_tailnet_addresses": [], "local_addresses": []}
        )


@pytest.mark.parametrize("address", ["100.64.0.2", "fd7a:115c:a1e0::2"])
def test_tailnet_requires_both_exact_approval_and_local_identity(address):
    host = f"[{address}]" if ":" in address else address
    value = {
        "endpoint": f"{host}:9101",
        "approved_tailnet_addresses": [address],
        "local_addresses": [address],
    }
    assert endpoint.validate(value)["address"] == address
    for key in ("approved_tailnet_addresses", "local_addresses"):
        with pytest.raises(ValueError):
            endpoint.validate({**value, key: []})


REPORT = """# Lynis Report
report_version_major=1
report_datetime_start=2026-10-10 00:00:00
lynis_version=3.1.4
lynis_tests_done=200
report_datetime_end=2026-10-10 00:00:02
finish=true
"""
START = 1791590400


def test_fresh_completed_machine_report_accepts_actual_warning_record():
    assert audit.validate_report(REPORT, START, START + 3) == 0
    assert (
        audit.validate_report(
            REPORT + "warning[]=SSH-7408|Warning text|-|-|\n", START, START + 3
        )
        == 1
    )


@pytest.mark.parametrize(
    "data, start",
    [
        ("", START),
        (REPORT.replace("finish=true", "finish=false"), START),
        (REPORT.replace("lynis_tests_done=200", "lynis_tests_done=0"), START),
        (REPORT, START + 60),
        (REPORT + "finish=true\n", START),
        (REPORT + "warning[]=\n", START),
        (REPORT + "malformed\n", START),
    ],
)
def test_failed_stale_or_malformed_machine_report_refuses(data, start):
    with pytest.raises((ValueError, KeyError)):
        audit.validate_report(data, start, start + 3)


def test_honeypot_observations_exceed_log_cap_without_losing_counts(
    tmp_path, monkeypatch
):
    renderer = load(ROOT / "scripts/check-templates-render.py", "cap_renderer")
    variables = renderer.merge_render_vars()
    variables["honeypot"].update(
        {
            "events_per_minute_max": 2,
            "log_dir": str(tmp_path / "log"),
            "textfile_dir": str(tmp_path / "metrics"),
        }
    )
    source = tmp_path / "honeypot.py"
    source.write_text(
        renderer.render_template(
            ROOT / "ansible/roles/honeypot/templates/honeypot.py.j2", variables
        )
    )
    detector = load(source, "cap_detector")
    monkeypatch.setattr(detector.time, "time", lambda: 120 * 60)
    for i in range(8):
        writer, reader = socket.socketpair()
        writer.sendall(b"public fixture")
        writer.close()
        detector._handle(reader, (f"192.0.2.{i+1}", 1234))
    detector._flush_textfile()
    assert len((tmp_path / "log/connections.log").read_text().splitlines()) == 2
    metrics = (tmp_path / "metrics/vpn_honeypot.prom").read_text()
    for name in (
        "events_total",
        "events_last_minute",
        "events_60min",
        "input_progress_total",
    ):
        assert f"vpn_honeypot_{name} 8\n" in metrics
    assert "vpn_honeypot_logs_suppressed_total 6\n" in metrics
    assert "vpn_honeypot_unique_ips 8\n" in metrics
    monkeypatch.setattr(detector.time, "time", lambda: 121 * 60)
    assert detector._bump("192.0.2.9", None)
    assert detector._total_events == 9
    monkeypatch.setattr(detector.time, "time", lambda: 181 * 60)
    detector._flush_textfile()
    assert (
        "vpn_honeypot_events_60min 0\n"
        in (tmp_path / "metrics/vpn_honeypot.prom").read_text()
    )


@pytest.mark.parametrize("check", [False, True])
def test_actual_monitoring_role_refuses_before_package_or_write(tmp_path, check):
    import os
    import subprocess
    import yaml

    play = tmp_path / "guard.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {"monitoring": {"node_exporter_listen": "0.0.0.0:9100"}},
                    "roles": ["monitoring"],
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play)]
        + (["--check"] if check else []),
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "private exporter endpoint rejected" in result.stdout
    assert "Install node_exporter from distro packages" not in result.stdout


def test_actual_opt_in_audit_rejects_disabled_scan_before_mutation(tmp_path):
    import os
    import subprocess
    import yaml

    play = tmp_path / "audit-disabled.yml"
    report = tmp_path / "reports"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "security_audit": {
                            "lynis": False,
                            "fail_on_high_findings": True,
                            "report_root": str(report),
                        }
                    },
                    "roles": ["security_audit"],
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert (
        "Opt-in audit acceptance requires Lynis collection to be enabled"
        in result.stdout
    )
    assert not report.exists()


def test_supported_lynis_repeat_non_acceptance_fields_preserves_strict_receipt():
    # The supported 3.0.9 producer repeats this technical finding key.
    report = (
        REPORT
        + "uncommon_network_protocol_enabled=1\nuncommon_network_protocol_enabled=1\n"
    )
    assert audit.validate_report(report, START, START + 3) == 0
    with pytest.raises(ValueError):
        audit.validate_report(
            report + "report_datetime_end=2026-10-10 00:00:02\n", START, START + 3
        )
