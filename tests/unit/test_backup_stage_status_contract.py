"""Backup stage outcomes are producer-owned, bounded, and atomically published."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "backup" / "templates" / "vpn-backup.sh.j2"

renderer_spec = importlib.util.spec_from_file_location(
    "backup_status_renderer", RENDERER
)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _render(*, remote_enabled: bool) -> str:
    variables = renderer.merge_render_vars()
    variables.update(
        {
            "restic_repo_dir": "/var/backups/vpn-restic",
            "backup_snapshot_max_age_hours": 36,
            "backup": {
                "remote": {
                    "enabled": remote_enabled,
                    "rclone_remote": "offsite",
                    "rclone_path": "vpn-backups",
                    "transfers": 1,
                    "bwlimit": "off",
                },
            },
        }
    )
    return renderer.render_template(TEMPLATE, variables)


def _environment(
    tmp_path: Path, *, fail_at: str | None = None, remote_enabled: bool = False
) -> tuple[Path, dict[str, str], Path]:
    script = tmp_path / "vpn-backup.sh"
    script.write_text(_render(remote_enabled=remote_enabled))
    script.chmod(0o700)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(mode=0o700)
    restic = bin_dir / "restic"
    restic.write_text(
        f"#!{sys.executable}\n"
        "import datetime as dt, json, os, sys\n"
        "args = sys.argv[1:]\n"
        f"if os.environ.get('BACKUP_STUB_FAIL_AT') == {fail_at!r} and {fail_at!r} in args: raise SystemExit(23)\n"
        "if 'snapshots' in args:\n"
        " print(json.dumps([{'short_id': 'secret-snapshot', 'time': dt.datetime.now(dt.timezone.utc).isoformat()}]))\n"
    )
    restic.chmod(0o700)
    rclone = bin_dir / "rclone"
    rclone.write_text(f"#!{sys.executable}\nimport sys\n")
    rclone.chmod(0o700)
    state_dir = tmp_path / "state"
    state_dir.mkdir(mode=0o700)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STATE_DIRECTORY": str(state_dir),
    }
    if fail_at is not None:
        environment["BACKUP_STUB_FAIL_AT"] = fail_at
    return script, environment, state_dir


def _run(
    tmp_path: Path, *, fail_at: str | None = None, remote_enabled: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path]:
    script, environment, state_dir = _environment(
        tmp_path, fail_at=fail_at, remote_enabled=remote_enabled
    )
    return (
        subprocess.run(
            [script], env=environment, capture_output=True, text=True, check=False
        ),
        state_dir,
    )


def test_backup_publishes_versioned_local_and_integrity_outcomes_without_snapshot_data(
    tmp_path: Path,
) -> None:
    result, state_dir = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    marker = state_dir / "backup-stage-status.json"
    payload = json.loads(marker.read_text())
    assert payload["version"] == 1
    assert payload["local_backup"]["result"] == "success"
    assert payload["integrity"]["result"] == "success"
    assert payload["remote_copy"]["result"] == "disabled"
    assert payload["local_backup"]["attempted_at"]
    assert payload["local_backup"]["succeeded_at"]
    assert payload["integrity"]["attempted_at"]
    assert payload["integrity"]["succeeded_at"]
    assert "snapshot" not in marker.read_text()
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert not list(state_dir.glob(".backup-stage-status.json.*"))


def test_integrity_failure_is_published_without_overriding_backup_exit_status(
    tmp_path: Path,
) -> None:
    result, state_dir = _run(tmp_path, fail_at="check")

    assert result.returncode == 23
    payload = json.loads((state_dir / "backup-stage-status.json").read_text())
    assert payload["local_backup"]["result"] == "success"
    assert payload["integrity"]["result"] == "failed"
    assert payload["integrity"]["failed_at"]
    assert payload["remote_copy"]["result"] == "disabled"


def test_remote_copy_outcome_is_published_only_when_the_optional_stage_runs(
    tmp_path: Path,
) -> None:
    result, state_dir = _run(tmp_path, remote_enabled=True)

    assert result.returncode == 0, result.stderr
    payload = json.loads((state_dir / "backup-stage-status.json").read_text())
    assert payload["remote_copy"]["result"] == "success"
    assert payload["remote_copy"]["attempted_at"]
    assert payload["remote_copy"]["succeeded_at"]


def test_status_publication_refuses_an_unsafe_existing_destination(
    tmp_path: Path,
) -> None:
    script, environment, state_dir = _environment(tmp_path)
    marker = state_dir / "backup-stage-status.json"
    marker.mkdir(mode=0o700)
    prior = marker / "prior"
    prior.write_text("unowned")

    result = subprocess.run(
        [script], env=environment, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0
    assert prior.read_text() == "unowned"
    assert marker.is_dir()


def test_template_uses_fd_backed_atomic_replacement_and_does_not_change_backup_commands() -> (
    None
):
    script = TEMPLATE.read_text()

    for command in (
        'restic -r "$REPO" backup',
        'restic -r "$REPO" forget',
        'restic -r "$REPO" check',
        "rclone sync --quiet",
        'rclone check "$REPO"',
    ):
        assert command in script
    assert "backup-stage-status.json" in script
    assert "os.replace(" in script
    assert "os.fsync(" in script
    assert "O_EXCL" in script
