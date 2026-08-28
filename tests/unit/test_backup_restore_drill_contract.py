"""Restore drills must exercise the selected repository without touching live paths."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
DRILL_TEMPLATE = REPO_ROOT / "ansible" / "roles" / "backup" / "templates" / "vpn-backup-restore-drill.sh.j2"
SERVICE_TEMPLATE = REPO_ROOT / "ansible" / "roles" / "backup" / "templates" / "vpn-backup-restore-drill.service.j2"
TIMER_TEMPLATE = REPO_ROOT / "ansible" / "roles" / "backup" / "templates" / "vpn-backup-restore-drill.timer.j2"

renderer_spec = importlib.util.spec_from_file_location("backup_drill_renderer", RENDERER)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _render(*, remote_enabled: bool, awg_instances: list[dict] | None = None) -> str:
    variables = renderer.merge_render_vars()
    amneziawg = dict(variables["amneziawg"])
    amneziawg["interface"] = "awg0"
    variables.update(
        {
            "restic_repo_dir": "/var/backups/vpn-restic",
            "backup_snapshot_max_age_hours": 36,
            "backup": {
                "restic_password": "molecule-stub-password",
                "remote": {
                    "enabled": remote_enabled,
                    "rclone_remote": "offsite",
                    "rclone_path": "vpn-backups",
                    "rclone_config": "",
                },
            },
            "vpn": {
                "enable_xray_reality": True,
                "enable_nginx_xhttp": True,
                "enable_hysteria": True,
                "enable_amneziawg": True,
            },
            "amneziawg": amneziawg,
            "amneziawg_secrets": {
                "instances": [{"name": "awg-test"}] if awg_instances is None else awg_instances,
            },
        }
    )
    return renderer.render_template(DRILL_TEMPLATE, variables)


def test_local_drill_restores_an_exact_recent_snapshot_into_runtime_storage() -> None:
    script = _render(remote_enabled=False)

    assert 'REPO="/var/backups/vpn-restic"' in script
    assert 'REPOSITORY_SOURCE="local"' in script
    assert "snapshots --tag vpn-stack --latest 1 --json" in script
    assert "dt.timedelta(hours=36)" in script
    assert 'restore "$snapshot_id" --target "$restore_target"' in script
    assert 'restore latest' not in script
    assert "--dry-run" not in script
    assert 'RUNTIME_DIRECTORY:?systemd must provide RUNTIME_DIRECTORY' in script


def test_remote_enabled_drill_uses_only_the_rclone_repository() -> None:
    script = _render(remote_enabled=True)

    assert 'REPO="rclone:offsite:vpn-backups/$(hostname)"' in script
    assert 'REPOSITORY_SOURCE="remote"' in script
    assert "RCLONE_CONFIG=/etc/rclone/rclone.conf" in script
    assert 'REPO="/var/backups/vpn-restic"' not in script
    assert "fallback" not in script.lower()


def test_drill_requires_baseline_and_enabled_transport_artifacts() -> None:
    script = _render(remote_enabled=False)

    for path in (
        "etc/nftables.conf",
        "etc/ssh/sshd_config.d/20-ansible-hardening.conf",
        "etc/sysctl.d/90-vpn.conf",
        "etc/xray/config.json",
        "etc/nginx/sites-available/vpn-xhttp.conf",
        "etc/nginx/tls/vpn.example.com.fullchain.pem",
        "etc/nginx/tls/vpn.example.com.key",
        "etc/hysteria/config.yaml",
        "etc/hysteria/server.fullchain.pem",
        "etc/hysteria/server.key",
        "etc/amnezia/amneziawg/awg-test.conf",
    ):
        assert path in script
    assert 'python3 -m json.tool "$restore_target/etc/xray/config.json"' in script


def test_drill_requires_legacy_amneziawg_interface_in_the_config_directory() -> None:
    script = _render(remote_enabled=False, awg_instances=[])

    assert "etc/amnezia/amneziawg/awg0.conf" in script
    assert "etc/amnezia/amneziawg/awg-test.conf" not in script


def test_drill_cleans_restored_secrets_before_atomically_publishing_success() -> None:
    script = _render(remote_enabled=False)

    cleanup = script.index("\nremove_restore\n", script.index("# Restored files contain live credentials."))
    metadata_cleanup = script.index('rm -f -- "$snapshot_metadata"', cleanup)
    marker_publish = script.index("os.replace(path, marker_path)")
    assert cleanup < metadata_cleanup < marker_publish
    assert "restore-drill-last-success.json" in script
    for field in ("version", "repository_source", "snapshot_id", "snapshot_time", "verified_at"):
        assert f'"{field}"' in script


def test_restore_drill_systemd_units_isolate_runtime_and_run_monthly() -> None:
    variables = renderer.merge_render_vars()
    service = renderer.render_template(SERVICE_TEMPLATE, variables)
    timer = renderer.render_template(TIMER_TEMPLATE, variables)

    for directive in (
        "RuntimeDirectory=vpn-backup-restore-drill",
        "RuntimeDirectoryMode=0700",
        "StateDirectory=vpn-backup",
        "StateDirectoryMode=0700",
        "UMask=0077",
        "PrivateTmp=true",
        "NoNewPrivileges=true",
    ):
        assert directive in service
    assert "OnCalendar=monthly" in timer
    assert "RandomizedDelaySec=2h" in timer
    assert "Persistent=true" in timer


def _drill_environment(tmp_path: Path) -> tuple[Path, dict[str, str], Path, Path, Path]:
    script = tmp_path / "vpn-backup-restore-drill.sh"
    script.write_text(_render(remote_enabled=False))
    script.chmod(0o700)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    restic = bin_dir / "restic"
    restic.write_text(
        """#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import sys

args = sys.argv[1:]
if "snapshots" in args:
    print(json.dumps([{"id": "a" * 64, "time": dt.datetime.now(dt.timezone.utc).isoformat()}]))
elif "restore" in args:
    target = pathlib.Path(args[args.index("--target") + 1])
    files = {
        "etc/nftables.conf": "table inet filter {}\\n",
        "etc/ssh/sshd_config.d/20-ansible-hardening.conf": "PasswordAuthentication no\\n",
        "etc/sysctl.d/90-vpn.conf": "net.ipv4.ip_forward = 1\\n",
        "etc/systemd/system/vpn-test.service": "[Service]\\nExecStart=/bin/true\\n",
        "etc/xray/config.json": "{}\\n",
        "etc/nginx/sites-available/vpn-xhttp.conf": "server {}\\n",
        "etc/nginx/tls/vpn.example.com.fullchain.pem": "certificate\\n",
        "etc/nginx/tls/vpn.example.com.key": "private key\\n",
        "etc/hysteria/config.yaml": "listen: :443\\n",
        "etc/hysteria/server.fullchain.pem": "certificate\\n",
        "etc/hysteria/server.key": "private key\\n",
        "etc/amnezia/amneziawg/awg-test.conf": "[Interface]\\n",
    }
    for relative, content in files.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
    if os.environ.get("RESTIC_STUB_CORRUPT_XRAY") == "1":
        (target / "etc/xray/config.json").write_text("{invalid json\\n")
else:
    raise SystemExit(f"unexpected restic invocation: {args}")
"""
    )
    restic.chmod(0o700)

    runtime_dir = tmp_path / "runtime"
    state_dir = tmp_path / "state"
    runtime_dir.mkdir()
    state_dir.mkdir()
    live_sentinel = tmp_path / "live-sentinel"
    live_sentinel.write_text("unchanged")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNTIME_DIRECTORY": str(runtime_dir),
        "STATE_DIRECTORY": str(state_dir),
    }
    return script, env, runtime_dir, state_dir, live_sentinel


@pytest.mark.parametrize("target_kind", ["directory", "file", "symlink", "dangling-symlink"])
def test_existing_restore_target_and_evidence_are_not_owned_by_cleanup(
    tmp_path: Path, target_kind: str
) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    target = runtime_dir / "restore"
    other = tmp_path / "other"
    if target_kind == "directory":
        target.mkdir()
        (target / "prior-data").write_text("prior data")
    elif target_kind == "file":
        target.write_text("prior data")
    else:
        if target_kind == "symlink":
            other.mkdir()
            (other / "prior-data").write_text("prior data")
        target.symlink_to(other, target_is_directory=True)
    metadata = runtime_dir / "snapshot.json"
    metadata.write_text("prior snapshot metadata")
    marker = state_dir / "restore-drill-last-success.json"
    marker.write_text("prior success")

    failed = subprocess.run([script], env=env, capture_output=True, text=True, check=False)

    assert failed.returncode != 0
    assert os.path.lexists(target)
    if target_kind == "directory":
        assert (target / "prior-data").read_text() == "prior data"
    elif target_kind == "file":
        assert target.read_text() == "prior data"
    else:
        assert target.is_symlink()
        assert target.readlink() == other
        if target_kind == "symlink":
            assert (other / "prior-data").read_text() == "prior data"
        else:
            assert not other.exists()
    assert metadata.read_text() == "prior snapshot metadata"
    assert marker.read_text() == "prior success"


@pytest.mark.parametrize("corrupt_restore", [False, True])
@pytest.mark.parametrize("metadata_kind", ["file", "symlink"])
def test_restore_preserves_unowned_snapshot_metadata(
    tmp_path: Path, corrupt_restore: bool, metadata_kind: str
) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    metadata = runtime_dir / "snapshot.json"
    prior = tmp_path / "prior-snapshot.json"
    prior.write_text("prior snapshot metadata")
    if metadata_kind == "symlink":
        metadata.symlink_to(prior)
    else:
        metadata.write_text("prior snapshot metadata")
    marker = state_dir / "restore-drill-last-success.json"
    marker.write_text("prior success")

    result = subprocess.run(
        [script],
        env={**env, "RESTIC_STUB_CORRUPT_XRAY": str(int(corrupt_restore))},
        capture_output=True,
        text=True,
        check=False,
    )

    assert (result.returncode != 0) == corrupt_restore, result.stderr
    assert metadata.read_text() == "prior snapshot metadata"
    assert prior.read_text() == "prior snapshot metadata"
    assert metadata.is_symlink() == (metadata_kind == "symlink")
    assert list(runtime_dir.iterdir()) == [metadata]
    if corrupt_restore:
        assert marker.read_text() == "prior success"


def test_failed_restore_preserves_unowned_pending_marker(tmp_path: Path) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    marker = state_dir / "restore-drill-last-success.json"
    marker.write_text("prior success")
    failed = subprocess.run(
        [
            "bash", "-c",
            'printf "prior pending marker" > "$STATE_DIRECTORY/.restore-drill-last-success.json.$$"; exec "$1"',
            "restore-test", str(script),
        ],
        env={**env, "RESTIC_STUB_CORRUPT_XRAY": "1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert failed.returncode != 0
    pending = list(state_dir.glob(".restore-drill-last-success.json.*"))
    assert len(pending) == 1
    assert pending[0].read_text() == "prior pending marker"
    assert marker.read_text() == "prior success"
    assert not list(runtime_dir.iterdir())


def test_cleanup_does_not_remove_a_target_claimed_after_its_restore_finishes(tmp_path: Path) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    python = tmp_path / "bin" / "python3"
    python.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys\n"
        "if len(sys.argv) > 2 and pathlib.Path(sys.argv[2]).name.startswith('.restore-drill-last-success.json.'):\n"
        "    target = pathlib.Path(os.environ['RUNTIME_DIRECTORY']) / 'restore'\n"
        "    target.mkdir()\n"
        "    (target / 'other-invocation').write_text('not owned')\n"
        "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
    )
    python.chmod(0o700)

    success = subprocess.run([script], env=env, capture_output=True, text=True, check=False)

    assert success.returncode == 0, success.stderr
    assert (runtime_dir / "restore" / "other-invocation").read_text() == "not owned"
    assert json.loads((state_dir / "restore-drill-last-success.json").read_text())["snapshot_id"] == "a" * 64


@pytest.mark.parametrize("marker_kind", ["directory", "symlink-to-directory"])
def test_marker_publication_never_moves_a_file_inside_an_existing_directory(
    tmp_path: Path, marker_kind: str
) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    marker = state_dir / "restore-drill-last-success.json"
    directory = marker if marker_kind == "directory" else tmp_path / "prior-directory"
    directory.mkdir()
    prior = directory / "prior-data"
    prior.write_text("not a restore marker")
    if marker_kind == "symlink-to-directory":
        marker.symlink_to(directory, target_is_directory=True)

    result = subprocess.run([script], env=env, capture_output=True, text=True, check=False)

    assert (result.returncode != 0) == (marker_kind == "directory"), result.stderr
    assert list(directory.iterdir()) == [prior]
    assert prior.read_text() == "not a restore marker"
    if marker_kind == "symlink-to-directory":
        assert not marker.is_symlink()
        assert json.loads(marker.read_text())["snapshot_id"] == "a" * 64
    assert not list(runtime_dir.iterdir())
    assert not list(state_dir.glob(".restore-drill-last-success.json.*"))


@pytest.mark.parametrize("delete_result", [0, 1])
def test_restore_cleanup_failure_preserves_previous_success_marker(
    tmp_path: Path, delete_result: int
) -> None:
    script, env, runtime_dir, state_dir, _ = _drill_environment(tmp_path)
    marker = state_dir / "restore-drill-last-success.json"
    marker.write_text("prior success")
    rm = tmp_path / "bin" / "rm"
    rm.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "if sys.argv[-1] == os.path.join(os.environ['RUNTIME_DIRECTORY'], 'restore'):\n"
        f"    raise SystemExit({delete_result})\n"
        "os.execv('/bin/rm', ['/bin/rm', *sys.argv[1:]])\n"
    )
    rm.chmod(0o700)

    failed = subprocess.run([script], env=env, capture_output=True, text=True, check=False)

    assert failed.returncode != 0
    assert marker.read_text() == "prior success"
    assert list(runtime_dir.iterdir()) == [runtime_dir / "restore"]
    assert (runtime_dir / "restore" / "etc/xray/config.json").read_text() == "{}\n"
    assert not list(state_dir.glob(".restore-drill-last-success.json.*"))


def test_rendered_drill_cleans_restore_and_preserves_marker_after_failure(tmp_path: Path) -> None:
    script, env, runtime_dir, state_dir, live_sentinel = _drill_environment(tmp_path)

    success = subprocess.run([script], env=env, capture_output=True, text=True, check=False)
    assert success.returncode == 0, success.stderr
    marker = state_dir / "restore-drill-last-success.json"
    first_marker = marker.read_text()
    payload = json.loads(first_marker)
    assert payload["repository_source"] == "local"
    assert payload["snapshot_id"] == "a" * 64
    assert not (runtime_dir / "restore").exists()
    assert live_sentinel.read_text() == "unchanged"

    failed = subprocess.run(
        [script],
        env={**env, "RESTIC_STUB_CORRUPT_XRAY": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    assert marker.read_text() == first_marker
    assert not (runtime_dir / "restore").exists()
