"""Behavioural coverage for watchdog and backup observability adaptation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collections.abc import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = (
    ROOT
    / "ansible"
    / "roles"
    / "observability_agent"
    / "files"
    / "observability-agent-health-adapter.py"
)

TEST_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIICvDCCAaQCCQDPLjjGiTxbyzANBgkqhkiG9w0BAQsFADAgMR4wHAYDVQQDDBVv
YnNlcnZhYmlsaXR5LWZpeHR1cmUwHhcNMjYwOTA1MDAyNjU0WhcNMzYwOTAyMDAy
NjU0WjAgMR4wHAYDVQQDDBVvYnNlcnZhYmlsaXR5LWZpeHR1cmUwggEiMA0GCSqG
SIb3DQEBAQUAA4IBDwAwggEKAoIBAQC7b3bi8aYD6C2GS+J5q8qh7u8xItAxC3Yn
iNh0fdfyqevTu0NfNKiQF3zqBnbHbQ0P0P02u8ozmTl9xCKpx6DZFa86iFMaRfx8
BajfM/nzrVgCGUBAF1O7EA/UuuE+WPSQNGaCXClTnds093OvtBJL6vTS7tcTwg++
cjYH5UuTvfTIIbfcXTCwrDobAomSfYlIQkiH9YS4qAMsn6WQeBUEMIO1DX3kjwV/
GLlcIgnjRmkpoMuTF6YZRr7ln+A7ZpmQZ5hnMaZn6i44IWl8j6mlP9P3jdkgE+I2
YDAOBnJmYDezvRI2i95SFnFd7dblTLAjKo3efDlxWG9SEYR6kLcHAgMBAAEwDQYJ
KoZIhvcNAQELBQADggEBAIR8MevB6e4YQtuGWpo46PsEzpkeNdcCDezBnz2CnecT
Y/ec+0fpGJXEz0CbiDBKpwTWyvfDNGJjIYE6JaYxad3TLNIAW5SmGdrTPeKl7TMw
EctTjO4Ha4T7CRp8Hna7/Vi3DS/ag5Mhy2nSxuvQwTgJ1n1chxGpXo8UNeV68Kd3
1SoUzS7TfjelQMABKHfYWkt9pVYuW+oHPt5fUcWGXshNxzgE/bpVjXJeI3336C1q
M9Hn/0Bi3kgI3gr4Gurew/0P7dv7ccBBto5+1SDRw5KcaVn61+wcwiD1NW1c+Pp+
B5gpOzyTwNBrxapJpEM/r44DE19ojingFHecLo60hF0=
-----END CERTIFICATE-----
"""


def _adapter_module():
    spec = importlib.util.spec_from_file_location(
        "observability_health_adapter", ADAPTER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="observability-health-", dir=Path.home()
    ) as value:
        root = Path(value)
        root.chmod(0o700)
        yield root


def _timestamp(offset: timedelta = timedelta()) -> str:
    return (datetime.now(UTC) + offset).isoformat().replace("+00:00", "Z")


def _watchdog_state(**overrides: int) -> str:
    values = {
        "consecutive_fails": 0,
        "last_alert_epoch": 0,
        "alerts_this_hour": 0,
        "alerts_hour_started": int(datetime.now(UTC).timestamp()),
        "kicks_this_hour": 0,
        "kicks_hour_started": int(datetime.now(UTC).timestamp()),
    }
    values.update(overrides)
    return "".join(f"{key}={value}\n" for key, value in values.items())


def _backup_stage(**stage_overrides: object) -> dict[str, object]:
    attempted = _timestamp(timedelta(seconds=-10))
    succeeded = _timestamp(timedelta(seconds=-5))
    payload: dict[str, object] = {
        "version": 1,
        "updated_at": _timestamp(),
        "local_backup": {
            "result": "success",
            "attempted_at": attempted,
            "succeeded_at": succeeded,
        },
        "integrity": {
            "result": "success",
            "attempted_at": attempted,
            "succeeded_at": succeeded,
        },
        "remote_copy": {"result": "disabled"},
    }
    payload.update(stage_overrides)
    return payload


def _restore_marker(
    *, source: str = "remote", age: timedelta = timedelta()
) -> dict[str, object]:
    return {
        "version": 1,
        "repository_source": source,
        "snapshot_id": "a" * 64,
        "snapshot_time": _timestamp(age - timedelta(minutes=5)),
        "verified_at": _timestamp(age),
    }


def _write_inputs(
    root: Path,
    *,
    watchdog: str | None = None,
    stage: dict[str, object] | str | None = None,
    restore: dict[str, object] | str | None = None,
) -> tuple[Path, Path, Path, Path]:
    watchdog_path = root / "watchdog" / "state"
    stage_path = root / "backup" / "backup-stage-status.json"
    restore_path = root / "backup" / "restore-drill-last-success.json"
    certificate_path = root / "credentials" / "client.crt"
    output = root / "textfile" / "observability-health.prom"
    for directory in (
        watchdog_path.parent,
        stage_path.parent,
        certificate_path.parent,
        output.parent,
    ):
        directory.mkdir(mode=0o700, exist_ok=True)
    watchdog_path.write_text(watchdog if watchdog is not None else _watchdog_state())
    watchdog_path.chmod(0o640)
    stage_payload = _backup_stage() if stage is None else stage
    stage_path.write_text(
        stage_payload if isinstance(stage_payload, str) else json.dumps(stage_payload)
    )
    stage_path.chmod(0o600)
    restore_payload = _restore_marker() if restore is None else restore
    restore_path.write_text(
        restore_payload
        if isinstance(restore_payload, str)
        else json.dumps(restore_payload)
    )
    restore_path.chmod(0o600)
    if certificate_path.exists():
        certificate_path.chmod(0o600)
    certificate_path.write_text(TEST_CERTIFICATE)
    certificate_path.chmod(0o400)
    return watchdog_path, stage_path, restore_path, output


def _run(
    root: Path,
    *,
    watchdog: str | None = None,
    stage: dict[str, object] | str | None = None,
    restore: dict[str, object] | str | None = None,
) -> tuple[subprocess.CompletedProcess[str], str, tuple[Path, Path, Path, Path]]:
    paths = _write_inputs(root, watchdog=watchdog, stage=stage, restore=restore)
    watchdog_path, stage_path, restore_path, output = paths
    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--node-id",
            "edge-prod",
            "--watchdog-state",
            str(watchdog_path),
            "--watchdog-fail-threshold",
            "3",
            "--watchdog-alert-limit",
            "4",
            "--watchdog-restart-limit",
            "3",
            "--watchdog-max-age-seconds",
            "900",
            "--backup-stage",
            str(stage_path),
            "--backup-stage-max-age-seconds",
            "129600",
            "--restore-drill",
            str(restore_path),
            "--restore-drill-max-age-seconds",
            "3024000",
            "--backup-snapshot-max-age-seconds",
            "129600",
            "--certificate",
            str(root / "credentials" / "client.crt"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, output.read_text() if output.exists() else "", paths


def test_adapter_publishes_healthy_watchdog_and_backup_evidence(tmp_path: Path) -> None:
    result, metrics, (_watchdog, _stage, _restore, output) = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (
        'vpn_watchdog_collection_success{node="edge-prod",role="watchdog"} 1' in metrics
    )
    assert (
        'vpn_watchdog_result{node="edge-prod",role="watchdog",state="healthy"} 1'
        in metrics
    )
    assert (
        'vpn_watchdog_recovery_outcome{node="edge-prod",role="watchdog",state="not-attempted"} 1'
        in metrics
    )
    assert (
        'vpn_backup_result{node="edge-prod",role="local-backup",state="success"} 1'
        in metrics
    )
    assert (
        'vpn_backup_result{node="edge-prod",role="remote-copy",state="disabled"} 1'
        in metrics
    )
    assert (
        'vpn_backup_restore_source{node="edge-prod",role="restore-drill",state="remote"} 1'
        in metrics
    )
    assert (
        'vpn_certificate_collection_success{node="edge-prod",role="observability-sender"} 1'
        in metrics
    )
    assert (
        'vpn_certificate_not_after_timestamp_seconds{node="edge-prod",role="observability-sender"}'
        in metrics
    )
    assert output.stat().st_mode & 0o777 == 0o640


def test_certificate_parse_failure_is_explicit_and_redacted(tmp_path: Path) -> None:
    result, _metrics, paths = _run(tmp_path)
    assert result.returncode == 0
    certificate = tmp_path / "credentials" / "client.crt"
    certificate.chmod(0o600)
    certificate.write_text("private-certificate-content")
    certificate.chmod(0o400)

    rerun = subprocess.run(
        result.args, cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    metrics = paths[3].read_text()

    assert rerun.returncode == 2
    assert rerun.stderr == "observability-health-adapter: collection failed\n"
    assert (
        'vpn_certificate_collection_success{node="edge-prod",role="observability-sender"} 0'
        in metrics
    )
    assert "vpn_certificate_not_after_timestamp_seconds" not in metrics
    assert "private-certificate-content" not in metrics + rerun.stderr


def test_watchdog_failure_restart_rate_limit_and_recovery_are_bounded(
    tmp_path: Path,
) -> None:
    failing = _watchdog_state(
        consecutive_fails=4,
        alerts_this_hour=4,
        kicks_this_hour=3,
    )
    result, metrics, _paths = _run(tmp_path, watchdog=failing)

    assert result.returncode == 0, result.stderr
    assert 'state="failed"' in metrics
    assert "vpn_watchdog_consecutive_failures" in metrics and " 4\n" in metrics
    assert "vpn_watchdog_restart_attempts" in metrics and " 3\n" in metrics
    assert 'role="alerts-rate-limit",state="limited"' in metrics
    assert 'role="restart-rate-limit",state="limited"' in metrics
    assert 'state="unresolved"' in metrics

    recovered = _watchdog_state(kicks_this_hour=1)
    result, metrics, _paths = _run(tmp_path, watchdog=recovered)
    assert result.returncode == 0
    assert (
        'vpn_watchdog_recovery_outcome{node="edge-prod",role="watchdog",state="recovered"} 1'
        in metrics
    )


@pytest.mark.parametrize(
    "watchdog",
    [
        "consecutive_fails=0\n",
        _watchdog_state() + "unknown=1\n",
        _watchdog_state() + "consecutive_fails=0\n",
        _watchdog_state(consecutive_fails=-1),
        _watchdog_state().replace("alerts_this_hour=0", "alerts_this_hour=secret"),
    ],
)
def test_watchdog_malformed_state_fails_closed_without_raw_content(
    tmp_path: Path, watchdog: str
) -> None:
    result, metrics, _paths = _run(tmp_path, watchdog=watchdog)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "observability-health-adapter: collection failed\n"
    assert (
        'vpn_watchdog_collection_success{node="edge-prod",role="watchdog"} 0' in metrics
    )
    assert "vpn_watchdog_result" not in metrics
    assert "secret" not in metrics + result.stderr


def test_watchdog_stale_or_future_state_fails_closed(tmp_path: Path) -> None:
    result, metrics, paths = _run(tmp_path)
    assert result.returncode == 0
    watchdog = paths[0]
    old = datetime.now(UTC).timestamp() - 901
    os.utime(watchdog, (old, old))
    result = subprocess.run(
        [*result.args], cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    metrics = paths[3].read_text()
    assert result.returncode == 2
    assert 'role="watchdog",state="stale"' in metrics
    assert "vpn_watchdog_result" not in metrics

    future = datetime.now(UTC).timestamp() + 60
    os.utime(watchdog, (future, future))
    result = subprocess.run(
        [*result.args], cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 2


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "world-writable"])
def test_watchdog_unsafe_input_fails_closed(tmp_path: Path, kind: str) -> None:
    result, _metrics, paths = _run(tmp_path)
    assert result.returncode == 0
    watchdog = paths[0]
    if kind == "symlink":
        target = tmp_path / "target-state"
        watchdog.rename(target)
        watchdog.symlink_to(target)
    elif kind == "hardlink":
        other = tmp_path / "other-state"
        other.hardlink_to(watchdog)
    else:
        watchdog.chmod(0o666)
    rerun = subprocess.run(
        result.args, cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert rerun.returncode == 2
    assert "target-state" not in rerun.stderr


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ({"result": "pending", "attempted_at": _timestamp()}, "pending"),
        (
            {
                "result": "failed",
                "attempted_at": _timestamp(),
                "failed_at": _timestamp(),
            },
            "failed",
        ),
    ],
)
def test_backup_stage_states_and_timestamps_are_explicit(
    tmp_path: Path, stage: dict[str, str], expected: str
) -> None:
    payload = _backup_stage(integrity=stage)
    result, metrics, _paths = _run(tmp_path, stage=payload)

    assert result.returncode == 0, result.stderr
    assert f'role="integrity",state="{expected}"' in metrics
    assert (
        'vpn_backup_attempted_timestamp_seconds{node="edge-prod",role="integrity"}'
        in metrics
    )
    if expected == "failed":
        assert (
            'vpn_backup_failed_timestamp_seconds{node="edge-prod",role="integrity"}'
            in metrics
        )


@pytest.mark.parametrize(
    "stage",
    [
        "not-json",
        '{"version":1,"version":1}',
        {"version": 1},
        _backup_stage(local_backup={"result": "success"}),
        _backup_stage(remote_copy={"result": "enabled"}),
        pytest.param(
            lambda: _backup_stage(updated_at=_timestamp(timedelta(minutes=1))),
            id="future-at-execution",
        ),
    ],
)
def test_backup_malformed_or_future_stage_fails_closed(
    tmp_path: Path, stage: object
) -> None:
    # Construct relative time at execution, not during whole-suite collection.
    if callable(stage):
        stage = stage()
    result, metrics, _paths = _run(tmp_path, stage=stage)  # type: ignore[arg-type]

    assert result.returncode == 2
    assert (
        'vpn_backup_collection_success{node="edge-prod",role="stage-status"} 0'
        in metrics
    )
    assert 'role="local-backup",state="success"' not in metrics


def test_backup_stale_stage_is_explicit_but_not_healthy(tmp_path: Path) -> None:
    updated_at = _timestamp(timedelta(hours=-37))
    attempted_at = _timestamp(timedelta(hours=-37, seconds=-10))
    succeeded_at = _timestamp(timedelta(hours=-37, seconds=-5))
    result, metrics, _paths = _run(
        tmp_path,
        stage=_backup_stage(
            updated_at=updated_at,
            local_backup={
                "result": "success",
                "attempted_at": attempted_at,
                "succeeded_at": succeeded_at,
            },
            integrity={
                "result": "success",
                "attempted_at": attempted_at,
                "succeeded_at": succeeded_at,
            },
        ),
    )

    assert result.returncode == 2
    assert 'role="stage-status",state="stale"' in metrics
    assert 'role="local-backup",state="success"' not in metrics


@pytest.mark.parametrize("source", ["local", "remote"])
def test_restore_drill_source_and_freshness_are_bounded(
    tmp_path: Path, source: str
) -> None:
    result, metrics, _paths = _run(tmp_path, restore=_restore_marker(source=source))

    assert result.returncode == 0, result.stderr
    assert (
        f'vpn_backup_restore_source{{node="edge-prod",role="restore-drill",state="{source}"}} 1'
        in metrics
    )
    assert (
        'vpn_backup_freshness_state{node="edge-prod",role="restore-drill",state="fresh"} 1'
        in metrics
    )
    assert "snapshot_id" not in metrics
    assert "a" * 64 not in metrics


@pytest.mark.parametrize(
    "restore",
    [
        "not-json",
        '{"version":1,"version":1}',
        {"version": 1},
        _restore_marker(source="unknown"),
        {**_restore_marker(), "snapshot_id": "secret-snapshot"},
        pytest.param(
            lambda: _restore_marker(age=timedelta(minutes=1)),
            id="future-at-execution",
        ),
    ],
)
def test_restore_malformed_or_future_marker_fails_closed(
    tmp_path: Path, restore: object
) -> None:
    # A queued suite must not turn this future timestamp into a valid past one.
    if callable(restore):
        restore = restore()
    result, metrics, _paths = _run(tmp_path, restore=restore)  # type: ignore[arg-type]

    assert result.returncode == 2
    assert (
        'vpn_backup_collection_success{node="edge-prod",role="restore-drill"} 0'
        in metrics
    )
    assert "secret-snapshot" not in metrics + result.stderr


def test_restore_stale_marker_is_explicit_but_not_healthy(tmp_path: Path) -> None:
    result, metrics, _paths = _run(
        tmp_path,
        restore=_restore_marker(age=timedelta(days=-36)),
    )

    assert result.returncode == 2
    assert 'role="restore-drill",state="stale"' in metrics
    assert "vpn_backup_restore_source" not in metrics


def test_adapter_never_invokes_producer_commands_and_redacts_sensitive_values(
    tmp_path: Path,
) -> None:
    stage = _backup_stage(secret_url="https://token.example/path")
    result, metrics, _paths = _run(tmp_path, stage=stage)

    assert result.returncode == 2
    combined = metrics + result.stdout + result.stderr
    for sensitive in ("token.example", "restic", "systemctl", "vpn-backup", "https://"):
        assert sensitive not in combined
    source = ADAPTER.read_text()
    for forbidden in (
        "systemctl",
        "restic",
        "vpn-watchdog.sh",
        "vpn-backup.sh",
    ):
        assert forbidden not in source


def test_missing_private_evidence_fails_without_disclosing_paths(
    tmp_path: Path,
) -> None:
    result, _metrics, paths = _run(tmp_path)
    paths[0].unlink()

    rerun = subprocess.run(
        result.args, cwd=ROOT, capture_output=True, text=True, timeout=10
    )

    assert rerun.returncode == 2
    assert rerun.stderr == "observability-health-adapter: collection failed\n"
    assert str(paths[0]) not in rerun.stderr


def test_atomic_health_output_retries_short_writes_and_publishes_0640(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter_module()
    output = tmp_path / "health.prom"
    original_write = adapter.os.write

    def one_byte(descriptor: int, content: bytes) -> int:
        return original_write(descriptor, content[:1])

    monkeypatch.setattr(adapter.os, "write", one_byte)
    adapter._atomic_write(output, "bounded\n")

    assert output.read_text() == "bounded\n"
    assert output.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".health.prom.*.tmp"))


def test_atomic_health_output_cleans_temporary_after_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter_module()
    output = tmp_path / "health.prom"

    def fail_write(_descriptor: int, _content: bytes) -> int:
        raise OSError("injected write failure")

    monkeypatch.setattr(adapter.os, "write", fail_write)
    with pytest.raises(OSError, match="injected write failure"):
        adapter._atomic_write(output, "never publish\n")

    assert not output.exists()
    assert not list(tmp_path.glob(".health.prom.*.tmp"))


@pytest.mark.parametrize("component", ["stage", "restore"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "oversized"])
def test_private_json_inputs_refuse_unsafe_nodes_without_disclosure(
    tmp_path: Path, component: str, kind: str
) -> None:
    result, _metrics, paths = _run(tmp_path)
    assert result.returncode == 0
    selected = paths[1] if component == "stage" else paths[2]
    if kind == "symlink":
        target = tmp_path / f"{component}-private-target"
        selected.rename(target)
        selected.symlink_to(target)
    elif kind == "hardlink":
        (tmp_path / f"{component}-private-link").hardlink_to(selected)
    else:
        selected.write_text("{" + '"private":"value",' * 2000 + '"version":1}')

    rerun = subprocess.run(
        result.args, cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    metrics = paths[3].read_text()

    assert rerun.returncode == 2
    role = "stage-status" if component == "stage" else "restore-drill"
    assert (
        f'vpn_backup_collection_success{{node="edge-prod",role="{role}"}} 0' in metrics
    )
    assert "private-target" not in rerun.stderr + metrics


def test_group_writable_private_evidence_parent_is_rejected(tmp_path: Path) -> None:
    result, _metrics, paths = _run(tmp_path)
    assert result.returncode == 0
    paths[1].parent.chmod(0o770)

    rerun = subprocess.run(
        result.args, cwd=ROOT, capture_output=True, text=True, timeout=10
    )

    assert rerun.returncode == 2
    assert rerun.stderr == "observability-health-adapter: collection failed\n"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "wrong-mode"])
def test_atomic_health_output_refuses_unsafe_existing_destination(
    tmp_path: Path, kind: str
) -> None:
    adapter = _adapter_module()
    output = tmp_path / "health.prom"
    target = tmp_path / "target.prom"
    target.write_text("producer-owned\n")
    if kind == "symlink":
        output.symlink_to(target)
    elif kind == "hardlink":
        output.hardlink_to(target)
    else:
        output.write_text("stale\n")
        output.chmod(0o600)

    with pytest.raises(adapter.HealthAdapterError, match="unsafe output"):
        adapter._atomic_write(output, "replace\n")

    assert target.read_text() == "producer-owned\n"
    assert not list(tmp_path.glob(".health.prom.*.tmp"))
