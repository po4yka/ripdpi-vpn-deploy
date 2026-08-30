"""Hermetic tests for the active REALITY target ASN monitor."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "monitor-reality-target.sh"
CRON_INSTALLER = REPO_ROOT / "scripts" / "install-operator-crons.sh"

TARGET = "private-target.example:443"
SERVER_NAMES = ["private-sni.example", "alt-private-sni.example"]
IPS = ["203.0.113.7", "203.0.113.8"]


def _make_stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _monitor_environment(tmp_path: Path, ambient: dict[str, str]) -> dict[str, str]:
    fixture = tmp_path / "prod.sops.yaml"
    fixture.write_text(
        json.dumps(
            {
                "xray": {"target": TARGET, "server_names": SERVER_NAMES},
                "watchdog_secrets": {
                    "ntfy_topic": "private-alert-topic",
                    "ntfy_token": "private-alert-token",
                },
            }
        )
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    alert_log = tmp_path / "alerts.log"
    forbidden_log = tmp_path / "forbidden.log"
    sops_log = tmp_path / "sops.log"

    _make_stub(
        bin_dir,
        "sops",
        '''printf '%s\\n' "$*" >> "$SOPS_LOG"
if [ "${SOPS_FAIL:-0}" = 1 ]; then printf '{"partial":'; exit 1; fi
cat "$SOPS_FIXTURE"''',
    )
    _make_stub(
        bin_dir,
        "getent",
        """if [ "${DNS_EMPTY:-0}" = 1 ]; then exit 2; fi
printf '%s STREAM target\\n' 203.0.113.7 203.0.113.8""",
    )
    _make_stub(bin_dir, "dig", "exit 0")
    _make_stub(bin_dir, "host", "exit 0")
    _make_stub(bin_dir, "timeout", 'shift; exec "$@"')
    _make_stub(
        bin_dir,
        "whois",
        '''if [ "${WHOIS_FAIL:-0}" = 1 ]; then echo 'error: unavailable'; exit 0; fi
case "$*" in
  *203.0.113.8*) ip=203.0.113.8; prefix=${WHOIS_PREFIX_2:-203.0.113.0/25} ;;
  *) ip=203.0.113.7; prefix=${WHOIS_PREFIX_1:-203.0.113.0/25} ;;
esac
asn=${WHOIS_ASN:-64500}
printf '%s | %s | %s | XX | registry | 2020-01-01 | PRIVATE-ORG\\n' "$asn" "$ip" "$prefix"''',
    )
    _make_stub(
        bin_dir,
        "openssl",
        """case "$1" in
  s_client)
    case "$*" in *"${FAIL_TLS_IP:-__none__}"*) echo 'CONNECTED'; exit 1;; esac
    printf '%s\\n' 'CONNECTED' '-----BEGIN CERTIFICATE-----' 'TESTCERT' '-----END CERTIFICATE-----'
    if [ "${FAIL_H2:-0}" = 1 ]; then echo 'ALPN protocol: http/1.1'; else echo 'ALPN protocol: h2'; fi
    [ "${FAIL_VERIFY:-0}" = 1 ] && exit 1
    exit 0
    ;;
  x509)
    if [ "${FAIL_SAN:-0}" = 1 ]; then
      echo 'X509v3 Subject Alternative Name:'
      echo '    DNS:wrong.example'
    elif [ -n "${WILDCARD_SAN:-}" ]; then
      echo 'X509v3 Subject Alternative Name:'
      echo "    DNS:${WILDCARD_SAN}"
    else
      echo 'X509v3 Subject Alternative Name:'
      echo '    DNS:private-sni.example, DNS:alt-private-sni.example, DNS:replacement-private.example'
    fi
    ;;
  dgst)
    echo 'SHA2-256(stdin)= test-fingerprint'
    ;;
  *) exit 2 ;;
esac""",
    )
    _make_stub(
        bin_dir,
        "curl",
        """case "$*" in
  *'-X POST'*)
    printf '%s\\n' "$*" >> "$ALERT_LOG"
    [ "${ALERT_FAIL:-0}" = 1 ] && exit 22
    exit 0
    ;;
esac
case "$*" in *"${FAIL_HTTP_IP:-__none__}"*) printf '000'; exit 28;; esac
printf '204'""",
    )
    for forbidden in (
        "terraform",
        "ansible-playbook",
        "vpnd",
        "make",
        "scan-reality-targets.sh",
        "blue-green.sh",
        "promote-spare",
    ):
        _make_stub(bin_dir, forbidden, f'echo {forbidden} >> "$FORBIDDEN_LOG"; exit 99')

    env = ambient.copy()
    for variable in (
        "ALERT_FAIL",
        "DNS_EMPTY",
        "FAIL_H2",
        "FAIL_HTTP_IP",
        "FAIL_SAN",
        "FAIL_TLS_IP",
        "FAIL_VERIFY",
        "SOPS_FAIL",
        "WHOIS_ASN",
        "WHOIS_FAIL",
        "WHOIS_PREFIX_1",
        "WHOIS_PREFIX_2",
        "WILDCARD_SAN",
    ):
        env.pop(variable, None)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "HOME": str(tmp_path / "home"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "TMPDIR": str(tmp_dir),
            "VPN_SECRETS_FILE": "",
            "SOPS_FILE": str(fixture),
            "SOPS_FIXTURE": str(fixture),
            "VANTAGE": "filtered-cohort-a",
            "ENV": "prod",
            "PROBE_TIMEOUT": "12",
            "NTFY_URL": "https://ntfy.fixture.invalid",
            "NTFY_TOPIC": "private-alert-topic",
            "NTFY_TOKEN": "private-alert-token",
            "ALERT_LOG": str(alert_log),
            "FORBIDDEN_LOG": str(forbidden_log),
            "SOPS_LOG": str(sops_log),
            "_MONITOR_CAPTURED_AT": "2026-07-10T04:00:00+00:00",
        }
    )
    (tmp_path / "home").mkdir()
    return env


@pytest.fixture
def monitor_env(tmp_path: Path) -> dict[str, str]:
    return _monitor_environment(tmp_path, os.environ)


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _report(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _state_path(env: dict[str, str]) -> Path:
    return Path(env["XDG_STATE_HOME"]) / "vpn-deploy/reality-target-monitor/prod.json"


def _alerts(env: dict[str, str]) -> list[str]:
    path = Path(env["ALERT_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def _set_day(env: dict[str, str], day: int) -> None:
    env["_MONITOR_CAPTURED_AT"] = f"2026-07-{day:02d}T04:00:00+00:00"


def test_fixture_ignores_poisoned_ambient_controller_inputs(tmp_path: Path) -> None:
    ambient_secrets = tmp_path / "ambient-secrets.json"
    ambient_secrets.write_text('{"ambient":"credential-boundary"}\n')
    ambient = os.environ.copy()
    ambient.update(
        {
            "VPN_SECRETS_FILE": str(ambient_secrets),
            "PROBE_TIMEOUT": "invalid-ambient-timeout",
            "NTFY_URL": "https://ambient-alert.invalid",
            "NTFY_TOPIC": "ambient-private-topic",
            "NTFY_TOKEN": "ambient-private-token",
        }
    )
    env = _monitor_environment(tmp_path, ambient)

    baseline = _report(_run(env))
    assert baseline["verdict"] == "ok", baseline
    assert baseline["baseline_created"] is True, baseline

    env["FAIL_TLS_IP"] = IPS[0]
    _set_day(env, 11)
    assert _report(_run(env))["consecutive_unhealthy"] == 1
    _set_day(env, 12)
    assert _report(_run(env))["alert_event"] == "alert"

    evidence = "\n".join([Path(env["SOPS_LOG"]).read_text(), *_alerts(env)])
    assert str(ambient_secrets) not in evidence
    assert "ambient-alert.invalid" not in evidence
    assert "ambient-private-topic" not in evidence
    assert "ambient-private-token" not in evidence
    assert env["SOPS_FIXTURE"] in evidence


def test_healthy_first_run_creates_redacted_baseline(monitor_env):
    fixture_before = Path(monitor_env["SOPS_FIXTURE"]).read_bytes()
    result = _run(monitor_env)
    report = _report(result)

    assert result.returncode == 0, result.stderr
    assert report["verdict"] == "ok"
    assert report["baseline_created"] is True
    assert report["asns"] == ["AS64500"]
    assert report["prefixes"] == ["203.0.113.0/25"]
    assert len(report["observations"]) == len(IPS)
    assert all(row["checks"] == len(SERVER_NAMES) for row in report["observations"])
    assert report["target_fingerprint"]

    state_blob = _state_path(monitor_env).read_text()
    output_blob = result.stdout + result.stderr + state_blob
    for secret in [
        TARGET,
        *SERVER_NAMES,
        "PRIVATE-ORG",
        "private-alert-topic",
        "private-alert-token",
    ]:
        assert secret not in output_blob
    assert not _alerts(monitor_env)
    assert not Path(monitor_env["FORBIDDEN_LOG"]).exists()
    sops_calls = Path(monitor_env["SOPS_LOG"]).read_text()
    assert "--decrypt" in sops_calls
    assert "--encrypt" not in sops_calls
    assert "update" not in sops_calls
    assert not list(Path(monitor_env["TMPDIR"]).glob("reality-target-monitor.*"))
    assert Path(monitor_env["SOPS_FIXTURE"]).read_bytes() == fixture_before


def test_two_strikes_alert_daily_then_recovery(monitor_env):
    baseline_result = _run(monitor_env)
    baseline = _report(baseline_result)
    assert baseline_result.returncode == 0, baseline
    assert baseline["verdict"] == "ok", baseline
    assert baseline["baseline_created"] is True, baseline

    monitor_env["FAIL_TLS_IP"] = IPS[1]
    _set_day(monitor_env, 11)
    first = _report(_run(monitor_env))
    assert first["verdict"] == "blocked"
    assert first["consecutive_unhealthy"] == 1
    assert not _alerts(monitor_env)

    same_day = _report(_run(monitor_env))
    assert same_day["consecutive_unhealthy"] == 1
    assert same_day["alert_event"] == "none"

    _set_day(monitor_env, 12)
    second = _report(_run(monitor_env))
    assert second["consecutive_unhealthy"] == 2
    assert second["alert_event"] == "alert"
    assert len(_alerts(monitor_env)) == 1
    alert_blob = "\n".join(_alerts(monitor_env))
    assert TARGET not in alert_blob
    assert all(server_name not in alert_blob for server_name in SERVER_NAMES)

    _set_day(monitor_env, 13)
    reminder = _report(_run(monitor_env))
    assert reminder["alert_event"] == "alert"
    assert len(_alerts(monitor_env)) == 2

    monitor_env.pop("FAIL_TLS_IP")
    _set_day(monitor_env, 14)
    recovered = _report(_run(monitor_env))
    assert recovered["verdict"] == "ok"
    assert recovered["alert_event"] == "recovery"
    assert recovered["consecutive_unhealthy"] == 0
    assert len(_alerts(monitor_env)) == 3


def test_skipped_day_resets_pre_alert_strike_sequence(monitor_env):
    assert _run(monitor_env).returncode == 0
    monitor_env["FAIL_TLS_IP"] = IPS[0]
    _set_day(monitor_env, 11)
    assert _report(_run(monitor_env))["consecutive_unhealthy"] == 1

    _set_day(monitor_env, 20)
    after_gap = _report(_run(monitor_env))
    assert after_gap["consecutive_unhealthy"] == 1
    assert after_gap["alert_event"] == "none"
    assert not _alerts(monitor_env)


def test_asn_drift_requires_confirmation_and_healthy_acceptance(monitor_env):
    assert _run(monitor_env).returncode == 0
    monitor_env["WHOIS_ASN"] = "64501"
    monitor_env["WHOIS_PREFIX_1"] = "198.51.100.0/24"
    monitor_env["WHOIS_PREFIX_2"] = "198.51.100.0/24"

    _set_day(monitor_env, 11)
    first = _report(_run(monitor_env))
    assert first["verdict"] == "unknown"
    assert set(first["reason_codes"]) == {"asn_set_changed", "prefix_set_changed"}
    assert first["consecutive_unhealthy"] == 1

    _set_day(monitor_env, 12)
    second = _report(_run(monitor_env))
    assert second["alert_event"] == "alert"
    assert len(_alerts(monitor_env)) == 1

    accepted = _report(_run(monitor_env, "--accept-baseline"))
    assert accepted["verdict"] == "ok"
    assert accepted["baseline_accepted"] is True
    assert accepted["consecutive_unhealthy"] == 0
    assert accepted["alert_event"] == "recovery"

    state = json.loads(_state_path(monitor_env).read_text())
    assert state["accepted_asns"] == ["AS64501"]
    assert state["accepted_prefixes"] == ["198.51.100.0/24"]


@pytest.mark.parametrize(
    ("env_key", "reason"),
    [
        ("FAIL_H2", "h2_unavailable"),
        ("FAIL_VERIFY", "certificate_validation_failed"),
        ("FAIL_SAN", "certificate_san_mismatch"),
        ("FAIL_HTTP_IP", "https_no_response"),
    ],
)
def test_path_failures_are_not_reported_as_ok(monitor_env, env_key, reason):
    monitor_env[env_key] = "1" if env_key != "FAIL_HTTP_IP" else IPS[0]
    report = _report(_run(monitor_env))
    assert report["verdict"] == "blocked"
    assert reason in report["reason_codes"]
    assert report["consecutive_unhealthy"] == 1


def test_dns_and_asn_lookup_failures_are_unknown(monitor_env):
    monitor_env["DNS_EMPTY"] = "1"
    dns = _report(_run(monitor_env))
    assert dns["verdict"] == "unknown"
    assert dns["reason_codes"] == ["dns_no_ipv4"]

    monitor_env.pop("DNS_EMPTY")
    monitor_env["WHOIS_FAIL"] = "1"
    asn = _report(_run(monitor_env))
    assert asn["verdict"] == "unknown"
    assert "asn_lookup_failed" in asn["reason_codes"]


def test_first_later_healthy_run_establishes_baseline(monitor_env):
    monitor_env["WHOIS_FAIL"] = "1"
    assert _report(_run(monitor_env))["verdict"] == "unknown"

    monitor_env.pop("WHOIS_FAIL")
    healthy = _report(_run(monitor_env))
    assert healthy["verdict"] == "ok"
    assert healthy["baseline_created"] is True
    state = json.loads(_state_path(monitor_env).read_text())
    assert state["accepted_asns"] == ["AS64500"]


def test_accept_baseline_refuses_unhealthy_path(monitor_env):
    monitor_env["FAIL_TLS_IP"] = IPS[0]
    result = _run(monitor_env, "--accept-baseline")
    report = _report(result)
    assert result.returncode != 0
    assert report["baseline_accepted"] is False
    assert "accept_requires_healthy_path" in report["reason_codes"]


def test_failed_alert_delivery_is_retried(monitor_env):
    assert _run(monitor_env).returncode == 0
    monitor_env["FAIL_TLS_IP"] = IPS[0]
    _set_day(monitor_env, 11)
    assert _run(monitor_env).returncode == 0

    _set_day(monitor_env, 12)
    monitor_env["ALERT_FAIL"] = "1"
    failed = _run(monitor_env)
    assert failed.returncode != 0
    assert _report(failed)["alert_delivery"] == "failed"

    monitor_env.pop("ALERT_FAIL")
    _set_day(monitor_env, 13)
    retried = _run(monitor_env)
    assert retried.returncode == 0
    assert _report(retried)["alert_delivery"] == "sent"
    assert len(_alerts(monitor_env)) == 2


def test_failed_recovery_delivery_is_retried(monitor_env):
    assert _run(monitor_env).returncode == 0
    monitor_env["FAIL_TLS_IP"] = IPS[0]
    _set_day(monitor_env, 11)
    assert _run(monitor_env).returncode == 0
    _set_day(monitor_env, 12)
    assert _run(monitor_env).returncode == 0

    monitor_env.pop("FAIL_TLS_IP")
    _set_day(monitor_env, 13)
    monitor_env["ALERT_FAIL"] = "1"
    failed = _run(monitor_env)
    assert failed.returncode != 0
    assert _report(failed)["alert_event"] == "recovery"

    monitor_env.pop("ALERT_FAIL")
    retried = _run(monitor_env)
    assert retried.returncode == 0
    assert _report(retried)["alert_delivery"] == "sent"


def test_healthy_target_change_creates_new_baseline_without_alert(monitor_env):
    original = _report(_run(monitor_env))
    fixture = Path(monitor_env["SOPS_FIXTURE"])
    data = json.loads(fixture.read_text())
    data["xray"]["target"] = "replacement-private.example:443"
    data["xray"]["server_names"] = ["replacement-private.example"]
    fixture.write_text(json.dumps(data))

    changed = _report(_run(monitor_env))
    assert changed["verdict"] == "ok"
    assert changed["baseline_created"] is True
    assert changed["target_fingerprint"] != original["target_fingerprint"]
    assert not _alerts(monitor_env)


def test_requires_explicit_filtered_vantage(monitor_env):
    monitor_env["VANTAGE"] = "unfiltered"
    result = _run(monitor_env)
    assert result.returncode != 0
    assert _report(result)["verdict"] == "error"


def test_tls_probe_has_a_hard_timeout():
    source = SCRIPT.read_text()
    assert '"$TIMEOUT_BIN" "$PROBE_TIMEOUT" openssl s_client' in source
    assert " -k" not in source


def test_wildcard_san_matches_exactly_one_label(monitor_env):
    fixture = Path(monitor_env["SOPS_FIXTURE"])
    data = json.loads(fixture.read_text())
    data["xray"]["server_names"] = ["a.b.example.com"]
    fixture.write_text(json.dumps(data))
    monitor_env["WILDCARD_SAN"] = "*.example.com"

    report = _report(_run(monitor_env))
    assert report["verdict"] == "blocked"
    assert "certificate_san_mismatch" in report["reason_codes"]


def test_partial_sops_decrypt_is_cleaned(monitor_env):
    monitor_env["SOPS_FAIL"] = "1"
    result = _run(monitor_env)
    assert result.returncode != 0
    assert _report(result)["verdict"] == "error"
    assert not list(Path(monitor_env["TMPDIR"]).glob("reality-target-monitor.*"))


def test_cron_installer_wires_monitor_only_with_vantage(tmp_path):
    base_env = os.environ.copy()
    base_env.update({"HOME": str(tmp_path), "PROVIDER": "upcloud", "ENV": "prod"})

    skipped = subprocess.run(
        ["bash", str(CRON_INSTALLER), "--dry-run"],
        cwd=REPO_ROOT,
        env=base_env,
        capture_output=True,
        text=True,
    )
    assert skipped.returncode == 0
    assert "monitor-reality-target" not in skipped.stdout
    assert "REALITY target monitor skipped" in skipped.stderr

    base_env["REALITY_TARGET_VANTAGE"] = "filtered-cohort-a"
    enabled = subprocess.run(
        ["bash", str(CRON_INSTALLER), "--dry-run"],
        cwd=REPO_ROOT,
        env=base_env,
        capture_output=True,
        text=True,
    )
    assert enabled.returncode == 0
    assert "17 4 * * *" in enabled.stdout
    assert "make monitor-reality-target" in enabled.stdout
    assert "VANTAGE=filtered-cohort-a" in enabled.stdout
