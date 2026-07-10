"""Restore drills must exercise the selected repository without touching live paths."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


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
        "etc/amnezia/awg-test.conf",
    ):
        assert path in script
    assert 'python3 -m json.tool "$restore_target/etc/xray/config.json"' in script


def test_drill_requires_legacy_amneziawg_interface_when_instance_list_is_empty() -> None:
    script = _render(remote_enabled=False, awg_instances=[])

    assert "etc/amnezia/awg0.conf" in script
    assert "etc/amnezia/awg-test.conf" not in script


def test_drill_cleans_restored_secrets_before_atomically_publishing_success() -> None:
    script = _render(remote_enabled=False)

    cleanup = script.index('rm -rf -- "$restore_target"')
    cleanup_check = script.index('test ! -e "$restore_target"')
    marker_publish = script.index('mv -f -- "$marker_tmp" "$marker"')
    assert cleanup < cleanup_check < marker_publish
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


def test_rendered_drill_cleans_restore_and_preserves_marker_after_failure(tmp_path: Path) -> None:
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
        "etc/amnezia/awg-test.conf": "[Interface]\\n",
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
