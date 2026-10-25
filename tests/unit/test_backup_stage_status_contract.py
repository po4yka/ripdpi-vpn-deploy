"""Backup stage outcomes are producer-owned, bounded, and atomically published."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import shlex
import re
import subprocess
import sys

import pytest
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


def _render(*, remote_enabled: bool, native_acme: bool = False) -> str:
    variables = renderer.merge_render_vars()
    variables["xray_etc_dir"] = variables["xray_config_dir"]
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
    if native_acme:
        variables['hysteria']['acme'] = {'domains': ['h2.example.test'], 'email': 'operator@example.test'}
    return renderer.render_template(TEMPLATE, variables)


def _environment(
    tmp_path: Path, *, fail_at: str | None = None, remote_enabled: bool = False, native_acme: bool = False
) -> tuple[Path, dict[str, str], Path]:
    script = tmp_path / "vpn-backup.sh"
    rendered = _render(remote_enabled=remote_enabled, native_acme=native_acme).replace('/etc/', str(tmp_path / 'etc') + '/').replace('/var/lib/vpn-subscription', str(tmp_path / 'subscription'))
    if native_acme:
        rendered = rendered.replace('/var/lib/hysteria/acme', str(tmp_path/'native-cache'))
    for block in ('INCLUDES', 'REQUIRED_FILES'):
        entries = shlex.split(re.search(rf'{block}=\((.*?)\)', rendered, re.S)[1])
        for entry in entries:
            path = Path(entry)
            path.parent.mkdir(parents=True, exist_ok=True)
            if block == 'REQUIRED_FILES' or path.name == 'nftables.conf' or path.name.startswith('vpn-watchdog') or path.name == 'revoked':
                path.write_text('synthetic input\n')
            else:
                path.mkdir(exist_ok=True)
    script.write_text(rendered)
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
    assert "written = os.write(temporary_fd, view)" in script
    assert "if written <= 0:" in script


@pytest.mark.parametrize('case', ['valid', 'cache-refused', 'summary-missing', 'summary-duplicate', 'summary-short'])
def test_native_cache_snapshot_is_admitted_before_retention_or_replication(tmp_path, case):
    script, environment, state = _environment(tmp_path, remote_enabled=True, native_acme=True)
    runtime = tmp_path/'runtime'
    runtime.mkdir(mode=0o700)
    actions = tmp_path/'actions.jsonl'
    actions.write_text('')
    environment.update(RUNTIME_DIRECTORY=str(runtime), TEST_ACTIONS=str(actions), TEST_CACHE_CASE=case)
    restic = tmp_path/'bin/restic'
    restic.write_text(f'#!{sys.executable}\n' + '''import datetime as dt,json,os,pathlib,sys
args=sys.argv[1:]
log=pathlib.Path(os.environ['TEST_ACTIONS'])
with log.open('a') as out:out.write(json.dumps(args)+'\\n')
if 'backup' in args:
 case=os.environ['TEST_CACHE_CASE']
 row={'message_type':'summary','snapshot_id':'a'*64}
 if case=='summary-short':row['snapshot_id']='short-id'
 if case!='summary-missing':print(json.dumps(row))
 if case=='summary-duplicate':print(json.dumps(row))
if 'snapshots' in args:print(json.dumps([{'short_id':'different-latest-snapshot','time':dt.datetime.now(dt.timezone.utc).isoformat()}]))
''')
    restic.chmod(0o700)
    checker = tmp_path/'cache-check.py'
    checker.write_text('''import json,os,pathlib,sys
with pathlib.Path(os.environ['TEST_ACTIONS']).open('a') as out:out.write(json.dumps(['cache-check'])+'\\n')
raise SystemExit(1 if os.environ['TEST_CACHE_CASE']=='cache-refused' else 0)
''')
    script.write_text(script.read_text().replace('/usr/local/libexec/ripdpi-transport-egress/transport_runtime_validate.py', str(checker)))
    completed = subprocess.run([str(script)], env=environment, capture_output=True, text=True, timeout=20)
    calls = [json.loads(line) for line in actions.read_text().splitlines()]
    restored = [call for call in calls if 'restore' in call]
    marker = json.loads((state/'backup-stage-status.json').read_text())
    if case == 'valid':
        assert completed.returncode == 0, completed.stderr
        assert restored[0][restored[0].index('restore')+1] == 'a'*64
        kinds = [next((kind for kind in ('backup','restore','cache-check','forget','check','snapshots') if kind in call), '') for call in calls]
        assert kinds == ['backup', 'restore', 'cache-check', 'forget', 'check', 'snapshots']
        assert marker['local_backup']['result'] == 'success' and marker['remote_copy']['result'] == 'success'
    else:
        assert completed.returncode != 0
        assert marker['local_backup']['result'] == 'failed' and marker['remote_copy']['result'] == 'disabled'
        assert not any('forget' in call or 'check' in call for call in calls)
        assert bool(restored) is (case == 'cache-refused')
    assert not list(runtime.iterdir())
