"""Exercise exact environment backup retention with real age ciphertext.

The remote backend is replaced by a terraform-env.sh stand-in that serves the
state from the legacy local path; restore is covered by test_tf_state_restore.py.
"""

from datetime import datetime, timedelta, timezone
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


STATE_PULL_STUB = """#!/usr/bin/env bash
set -euo pipefail
[[ "$1 $2" == "state pull" && -z "${STUB_PULL_FAIL:-}" ]] || exit 9
state="$(cd "$(dirname "$0")/.." && pwd)/terraform/providers/${PROVIDER}"
[[ "$ENV" == prod ]] || state="${state}/terraform.tfstate.d/${ENV}"
[[ ! -e "${state}/terraform.tfstate" ]] || cat "${state}/terraform.tfstate"
"""


@pytest.fixture
def backup_workspace(tmp_path):
    home = tmp_path / "home"
    configuration = home / ".config/vpn-provision"
    destination = configuration / "state-backups"
    destination.mkdir(parents=True, mode=0o700)
    identity = configuration / "age.key"
    subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(["age-keygen", "-y", str(identity)], text=True).strip()
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/backup-tf-state.sh", repo / "scripts/backup-tf-state.sh")
    wrapper = repo / "scripts/terraform-env.sh"
    wrapper.write_text(STATE_PULL_STUB)
    wrapper.chmod(0o700)
    environment = {
        "PATH": os.environ["PATH"], "HOME": str(home), "AGE_RECIPIENT": recipient,
        "BACKUP_DEST": str(destination), "PROVIDER": "upcloud",
    }
    return repo, destination, identity, environment


def encrypt(payload, recipient):
    return subprocess.run(
        ["age", "-r", recipient], input=payload, check=True, capture_output=True,
    ).stdout


def publish_backup(destination, name, ciphertext, timestamp):
    path = destination / name
    path.write_bytes(ciphertext)
    os.utime(path, (timestamp, timestamp))
    return path


def test_retention_keeps_recent_backups_beyond_the_count(backup_workspace):
    """Repeated runs after a bad apply must not push out the last good backups."""
    import time

    repo, destination, _, settings = backup_workspace
    state = repo / "terraform/providers/upcloud/terraform.tfstate"
    state.parent.mkdir(parents=True)
    state.write_bytes(b'{"version":4,"resources":[],"serial":7,"lineage":"synthetic"}\n')
    ciphertext = encrypt(b"prior synthetic state", settings["AGE_RECIPIENT"])
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = [publish_backup(destination, f"upcloud-prod-{start + timedelta(days=index):%Y%m%dT%H%M%SZ}.tfstate.age",
                             ciphertext, time.time() - 3600 - index) for index in range(31)]

    result = subprocess.run(
        ["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": "prod"}, text=True, capture_output=True, timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert all(path.exists() for path in recent) and "removed old backup" not in result.stdout


@pytest.mark.parametrize("environment", ["prod", "prod-green"])
def test_retention_preserves_other_exact_environments(backup_workspace, environment):
    repo, destination, identity, settings = backup_workspace
    provider_root = repo / "terraform/providers/upcloud"
    state = provider_root / ("terraform.tfstate" if environment == "prod" else
                             f"terraform.tfstate.d/{environment}/terraform.tfstate")
    state.parent.mkdir(parents=True)
    payload = b'{"version":4,"resources":[],"serial":7,"lineage":"synthetic"}\n'
    state.write_bytes(payload)
    prior_ciphertext = encrypt(b"prior synthetic state", settings["AGE_RECIPIENT"])
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    selected = []
    for index in range(31):
        timestamp = start + timedelta(days=index)
        selected.append(publish_backup(
            destination, f"upcloud-{environment}-{timestamp:%Y%m%dT%H%M%SZ}.tfstate.age",
            prior_ciphertext, timestamp.timestamp(),
        ))
    unrelated = [
        publish_backup(destination, f"upcloud-{environment}-green-20250101T000000Z.tfstate.age", prior_ciphertext, 1),
        publish_backup(destination, "upcloud-prod-20250101T000000Z.tfstate.age", prior_ciphertext, 1)
        if environment != "prod" else
        publish_backup(destination, "upcloud-prod-other-20250101T000000Z.tfstate.age", prior_ciphertext, 1),
        publish_backup(destination, f"hetzner-{environment}-20250101T000000Z.tfstate.age", prior_ciphertext, 1),
        publish_backup(destination, f"upcloud-{environment}-20250101T000000Z.extra.tfstate.age", prior_ciphertext, 1),
        publish_backup(destination, f"upcloud-{environment}-abcdefghTijklmnZ.tfstate.age", prior_ciphertext, 1),
    ]
    before = {path: path.read_bytes() for path in unrelated}

    result = subprocess.run(
        ["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": environment}, text=True, capture_output=True, timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert not selected[0].exists() and not selected[1].exists()
    assert all(path.exists() for path in selected[2:])
    assert {path: path.read_bytes() for path in unrelated} == before
    output = Path(next(line.removeprefix("wrote ") for line in result.stdout.splitlines()
                       if line.startswith("wrote ")))
    assert output not in selected and output not in unrelated
    decrypted = subprocess.run(
        ["age", "-d", "-i", str(identity), str(output)], check=True, capture_output=True,
    ).stdout
    assert decrypted == payload
    assert output.stat().st_mode & 0o777 == 0o600
    assert len([path for path in selected if path.exists()]) + 1 == 30


def state_bytes(serial):
    return json.dumps({"version": 4, "serial": serial, "lineage": "synthetic", "resources": []}).encode()


def prepare_state(repo, environment="prod"):
    parent = repo / "terraform/providers/upcloud"
    if environment != "prod":
        parent = parent / "terraform.tfstate.d" / environment
    parent.mkdir(parents=True, exist_ok=True)
    state = parent / "terraform.tfstate"
    state.write_bytes(state_bytes(1))
    state.chmod(0o600)
    return state


def test_failed_encryption_publishes_no_partial_backup(backup_workspace, tmp_path):
    repo, destination, identity, settings = backup_workspace
    prepare_state(repo)
    accepted = publish_backup(destination, "upcloud-prod-20260101T000000Z.tfstate.age",
                             encrypt(state_bytes(1), settings["AGE_RECIPIENT"]), 1)
    previous = accepted.read_bytes()
    binary = tmp_path / "bin"
    binary.mkdir()
    age = binary / "age"
    age.write_text('#!/bin/sh\nprintf partial-ciphertext\nexit 1\n')
    age.chmod(0o700)
    result = subprocess.run(["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": "prod", "PATH": str(binary) + os.pathsep + settings["PATH"]},
        capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert list(destination.iterdir()) == [accepted]
    assert accepted.read_bytes() == previous
    assert subprocess.run(["age", "-d", "-i", str(identity), str(accepted)],
                          capture_output=True, check=True).stdout == state_bytes(1)


def test_concurrent_backups_remain_distinct_and_private(backup_workspace):
    repo, destination, identity, settings = backup_workspace
    state = prepare_state(repo)
    environment = settings | {"ENV": "prod"}
    processes = [subprocess.Popen(["bash", str(repo / "scripts/backup-tf-state.sh")],
                 env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stdout + stderr
    backups = list(destination.iterdir())
    assert len(backups) == 2
    for path in backups:
        assert path.name.endswith(".tfstate.age")
        assert path.stat().st_mode & 0o777 == 0o600
        assert subprocess.run(["age", "-d", "-i", str(identity), str(path)],
                              capture_output=True, check=True).stdout == state.read_bytes()


@pytest.mark.parametrize("pulled", ["fail", None, b"", b"synthetic-private-state-not-json",
                                    b'{"version":4,"serial":true,"lineage":"synthetic-private-state","resources":[]}'])
def test_empty_or_invalid_pull_publishes_no_backup(backup_workspace, pulled):
    repo, destination, _identity, settings = backup_workspace
    if isinstance(pulled, bytes):
        state = prepare_state(repo)
        state.write_bytes(pulled)
    elif pulled == "fail":
        prepare_state(repo)
        settings = settings | {"STUB_PULL_FAIL": "1"}
    result = subprocess.run(["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": "prod"}, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "empty or invalid" in result.stderr
    assert "synthetic-private-state" not in result.stdout + result.stderr
    assert list(destination.iterdir()) == []


def test_collision_exhaustion_preserves_accepted_backup(backup_workspace, tmp_path):
    repo, destination, _identity, settings = backup_workspace
    prepare_state(repo)
    accepted = publish_backup(destination, "upcloud-prod-20260101T000000Z.tfstate.age",
                             encrypt(state_bytes(3), settings["AGE_RECIPIENT"]), 1)
    previous = accepted.read_bytes()
    binary = tmp_path / "bin"
    binary.mkdir()
    date = binary / "date"
    date.write_text('#!/bin/sh\nprintf "20260101T000000Z\\n"\n')
    date.chmod(0o700)
    sleep = binary / "sleep"
    retry_log = tmp_path / "retries"
    sleep.write_text(f'#!/bin/sh\nprintf "retry\\n" >> "{retry_log}"\n')
    sleep.chmod(0o700)
    result = subprocess.run(["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": "prod", "PATH": str(binary) + os.pathsep + settings["PATH"]},
        capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "publication failed" in result.stderr
    assert len(retry_log.read_text().splitlines()) == 10
    assert accepted.read_bytes() == previous
    assert list(destination.iterdir()) == [accepted]


def synthetic_state(repo):
    path = repo / 'terraform/providers/upcloud/terraform.tfstate'
    path.parent.mkdir(parents=True)
    path.write_bytes(state_bytes(123))
    return path


def age_fault_wrapper(tmp_path, settings, *, wait=False):
    """Inject an interrupted write after obtaining real age ciphertext."""
    binary = shutil.which('age')
    assert binary, 'real age is required'
    tools = tmp_path / 'fault-bin'
    tools.mkdir()
    wrapper = tools / 'age'
    wrapper.write_text(
        '#!' + shutil.which('python3') + '\n'
        'import os, pathlib, signal, subprocess, sys\n'
        f'result = subprocess.run([{binary!r}, *sys.argv[1:]], capture_output=True, check=True)\n'
        'sys.stdout.buffer.write(result.stdout[:len(result.stdout)//2]); sys.stdout.buffer.flush()\n'
        'pathlib.Path(os.environ["FAULT_READY"]).write_text("ready")\n'
        + ('signal.pause()\n' if wait else 'raise SystemExit(23)\n')
    )
    wrapper.chmod(0o700)
    return settings | {'PATH': str(tools) + os.pathsep + settings['PATH'], 'FAULT_READY': str(tmp_path / 'ready')}


def test_failed_encryption_never_publishes_a_recovery_name(backup_workspace, tmp_path):
    repo, destination, identity, settings = backup_workspace
    synthetic_state(repo)
    old = publish_backup(destination, 'upcloud-prod-20260101T000000Z.tfstate.age',
                         encrypt(b'prior synthetic state', settings['AGE_RECIPIENT']), 1)
    foreign = destination / '.state-backup.foreign'
    foreign.write_bytes(b'not owned by this invocation')
    before = {path: path.read_bytes() for path in (old, foreign)}
    result = subprocess.run(['bash', str(repo / 'scripts/backup-tf-state.sh')],
                            check=False, env=age_fault_wrapper(tmp_path, settings), capture_output=True, timeout=20)
    assert result.returncode != 0
    assert {path: path.read_bytes() for path in destination.iterdir()} == before
    assert subprocess.run(['age', '-d', '-i', str(identity), str(old)], capture_output=True, check=True).stdout == b'prior synthetic state'


def test_signal_removes_only_owned_incomplete_ciphertext(backup_workspace, tmp_path):
    import signal
    import time

    repo, destination, _, settings = backup_workspace
    synthetic_state(repo)
    old = publish_backup(destination, 'upcloud-prod-20260101T000000Z.tfstate.age',
                         encrypt(b'prior synthetic state', settings['AGE_RECIPIENT']), 1)
    before = old.read_bytes()
    environment = age_fault_wrapper(tmp_path, settings, wait=True)
    child = subprocess.Popen(['bash', str(repo / 'scripts/backup-tf-state.sh')], env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not Path(environment['FAULT_READY']).exists() and time.monotonic() < deadline:
            assert child.poll() is None, 'backup exited before interruption boundary'
            time.sleep(0.01)
        assert Path(environment['FAULT_READY']).exists()
        os.killpg(child.pid, signal.SIGTERM)
        child.communicate(timeout=10)
        assert child.returncode != 0
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=10)
    assert list(destination.iterdir()) == [old]
    assert old.read_bytes() == before


def test_same_timestamp_refuses_overwriting_complete_snapshot(backup_workspace, tmp_path):
    repo, destination, identity, settings = backup_workspace
    state = synthetic_state(repo)
    tools = tmp_path / 'time-bin'
    tools.mkdir()
    clock = tools / 'date'
    clock.write_text('#!/bin/sh\nprintf "%s\\n" 20260101T000000Z\n')
    clock.chmod(0o700)
    sleep = tools / 'sleep'
    sleep.write_text('#!/bin/sh\nexit 0\n')
    sleep.chmod(0o700)
    environment = settings | {'PATH': str(tools) + os.pathsep + settings['PATH']}
    argv = ['bash', str(repo / 'scripts/backup-tf-state.sh')]
    first = subprocess.run(argv, check=False, env=environment, capture_output=True, timeout=20)
    assert first.returncode == 0
    output = destination / 'upcloud-prod-20260101T000000Z.tfstate.age'
    before = output.read_bytes()
    state.write_bytes(state_bytes(124))
    second = subprocess.run(argv, check=False, env=environment, capture_output=True, timeout=20)
    assert second.returncode != 0
    assert output.read_bytes() == before
    assert list(destination.iterdir()) == [output]
    assert subprocess.run(['age', '-d', '-i', str(identity), str(output)], capture_output=True, check=True).stdout != state.read_bytes()


@pytest.mark.parametrize("phase", ["file", "directory"])
def test_fsync_failure_never_announces_success_or_prunes(backup_workspace, tmp_path, phase):
    import sys

    repo, destination, identity, settings = backup_workspace
    state = prepare_state(repo)
    ciphertext = encrypt(state_bytes(2), settings["AGE_RECIPIENT"])
    for day in range(1, 32):
        publish_backup(destination, f"upcloud-prod-202501{day:02d}T000000Z.tfstate.age",
                       ciphertext, day)
    foreign = destination / ".state-backup.foreign"
    foreign.write_bytes(b"not owned by this invocation")
    before = {path: path.read_bytes() for path in destination.iterdir()}
    tools = tmp_path / "sync-fault-bin"
    tools.mkdir()
    wrapper = tools / "python3"
    wrapper.write_text(
        "#!" + sys.executable + "\n"
        "import os, stat, sys\n"
        "if sys.argv[1:2] == ['-c']:\n"
        "    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
        "program = sys.stdin.buffer.read()\n"
        "sys.argv = sys.argv[1:]\n"
        "original_fsync = os.fsync\n"
        + f"phase = {phase!r}\n"
        + "def fail_selected_sync(fd):\n"
        "    directory = stat.S_ISDIR(os.fstat(fd).st_mode)\n"
        "    if directory == (phase == 'directory'):\n"
        "        raise OSError('synthetic sync failure')\n"
        "    return original_fsync(fd)\n"
        "os.fsync = fail_selected_sync\n"
        "exec(compile(program, '<owned-sync-fault>', 'exec'))\n"
    )
    wrapper.chmod(0o700)
    result = subprocess.run(["bash", str(repo / "scripts/backup-tf-state.sh")],
        env=settings | {"ENV": "prod", "PATH": str(tools) + os.pathsep + settings["PATH"]},
        capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "sync failed" in result.stderr
    assert "wrote " not in result.stdout and "removed old backup" not in result.stdout
    assert {path: path.read_bytes() for path in before} == before
    added = set(destination.iterdir()) - before.keys()
    if phase == "file":
        assert not added
    else:
        assert len(added) == 1
        published = next(iter(added))
        assert published.name.endswith(".tfstate.age")
        assert published.stat().st_mode & 0o777 == 0o600
        assert subprocess.run(["age", "-d", "-i", str(identity), str(published)],
                              capture_output=True, check=True).stdout == state.read_bytes()
    assert set(destination.glob(".state-backup.*")) == {foreign}


def test_cron_backs_up_state_only_through_both_sops_documents(tmp_path):
    installer = ROOT / "scripts/install-operator-crons.sh"

    def cron(**extra):
        return subprocess.run(["bash", str(installer), "--dry-run"], cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, HOME=str(tmp_path), PROVIDER="upcloud", ENV="prod", **extra))

    skipped = cron()
    assert skipped.returncode == 0 and "backup-state" not in skipped.stdout.split("vpn-state")[0].splitlines()[-1]
    assert "state backup skipped" in skipped.stderr
    identity, passphrase = tmp_path / "scw state.sops.json", tmp_path / "pass.sops.json"
    identity.write_text(json.dumps({"AWS_SECRET_ACCESS_KEY": "synthetic-key"}))
    passphrase.write_text(json.dumps({"TF_VAR_state_passphrase": "synthetic-passphrase"}))
    enabled = cron(STATE_IDENTITY_SOPS_FILE=str(identity), STATE_PASSPHRASE_SOPS_FILE=str(passphrase))
    assert enabled.returncode == 0, enabled.stderr
    [line] = [entry for entry in enabled.stdout.splitlines() if entry.startswith("47 3 * * *")]
    assert "synthetic" not in line
    # Run the scheduled command with stand-ins: sops exec-env merges the document into the child.
    tools = tmp_path / "cron-bin"
    tools.mkdir()
    (tools / "sops").write_text("#!/usr/bin/env python3\nimport json, os, subprocess, sys\n"
                                "assert sys.argv[1] == 'exec-env'\n"
                                "sys.exit(subprocess.call(['sh', '-c', sys.argv[3]], env=dict(os.environ, **json.load(open(sys.argv[2])))))\n")
    record = tmp_path / "make.json"
    (tools / "make").write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                                f"json.dump({{'argv': sys.argv[1:], 'env': {{k: os.environ.get(k) for k in "
                                f"('AWS_SECRET_ACCESS_KEY', 'TF_VAR_state_passphrase', 'PROVIDER', 'ENV')}}}}, open({str(record)!r}, 'w'))\n")
    (tools / "logger").write_text('#!/bin/sh\ncat >/dev/null\n')
    for tool in tools.iterdir():
        tool.chmod(0o700)
    command = line.removeprefix("47 3 * * *")
    run = subprocess.run(["sh", "-c", command], env=dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}"),
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert json.loads(record.read_text()) == {"argv": ["backup-state"], "env": {
        "AWS_SECRET_ACCESS_KEY": "synthetic-key", "TF_VAR_state_passphrase": "synthetic-passphrase",
        "PROVIDER": "upcloud", "ENV": "prod"}}
    # A scheduled monitor can read the public address. Only tofu gets the credentials.
    monitors = cron(MONITOR_STATE_IDENTITY_SOPS_FILE=str(identity), STATE_PASSPHRASE_SOPS_FILE=str(passphrase))
    assert monitors.returncode == 0, monitors.stderr
    for goal in ("burn-check", "asn-drift", "check-ip-reputation", "probing-summary"):
        assert sum(line.endswith(f"make {goal}") for line in monitors.stdout.splitlines()) == 1
    [entry] = [line for line in monitors.stdout.splitlines() if line.endswith("make burn-check")]
    command = entry.split(" cd ", 1)[1]
    (tools / "make").write_text('#!/bin/sh\nset -eu\ntest -z "${AWS_SECRET_ACCESS_KEY:-}${TF_VAR_state_passphrase:-}"\n'
                                'exec ./scripts/terraform-env.sh output -raw server_ipv4\n')
    (tools / "tofu").write_text('#!/bin/sh\nset -eu\ntest "$AWS_SECRET_ACCESS_KEY" = synthetic-key\n'
                                'test "$TF_VAR_state_passphrase" = synthetic-passphrase\nexit "${TOFU_STATUS:-0}"\n')
    (tools / "logger").write_text('#!/bin/sh\ncat >/dev/null\n')
    for name in ("tofu", "logger"):
        (tools / name).chmod(0o700)
    backend = tmp_path / "config"
    backend.mkdir()
    (backend / "upcloud.s3.tfbackend").write_text('key = "state/upcloud/terraform.tfstate"\nworkspace_key_prefix = "state/workspaces"\nuse_lockfile = true\n')
    child = {"HOME": str(tmp_path), "PATH": f"{tools}:{os.environ['PATH']}", "TF_BACKEND_ROOT": str(backend)}
    for status in ("0", "1"):
        run = subprocess.run(["sh", "-c", "cd " + command], env=dict(child, TOFU_STATUS=status),
                             capture_output=True, text=True, timeout=20)
        assert run.returncode == int(status), run.stderr
    missing = cron(STATE_IDENTITY_SOPS_FILE=str(identity), STATE_PASSPHRASE_SOPS_FILE=str(tmp_path / "missing.json"))
    assert missing.returncode != 0 and "must both name existing absolute files" in missing.stderr
