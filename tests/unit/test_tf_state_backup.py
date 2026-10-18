"""Exercise exact environment retention and recovery with real age ciphertext."""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


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
    shutil.copyfile(ROOT / "scripts/backup-tf-state.sh", repo / "scripts/backup-tf-state.sh")
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
    start = datetime(2026, 1, 1, tzinfo=UTC)
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
        check=False, env=settings | {"ENV": environment}, text=True, capture_output=True, timeout=20,
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


def recovery_recipe():
    text = (ROOT / "docs/RUNBOOK-incident.md").read_text()
    recipe = text.split("# State backups live in", 1)[1].split("```", 1)[0]
    # Execute the documented selection and decryption. Provider work stays out.
    recipe = "# State backups live in" + recipe.split("PROVIDER=upcloud ENV=prod", 1)[0]
    return recipe + "true\n"


@pytest.mark.parametrize("available", [True, False])
def test_documented_recovery_selects_only_exact_environment(backup_workspace, available):
    repo, destination, _identity, settings = backup_workspace
    provider_root = repo / "terraform/providers/upcloud"
    provider_root.mkdir(parents=True)
    payload = b"selected synthetic production state"
    if available:
        publish_backup(destination, "upcloud-prod-20260101T000000Z.tfstate.age",
                       encrypt(b"old production state", settings["AGE_RECIPIENT"]), 1)
        publish_backup(destination, "upcloud-prod-20260102T000000Z.tfstate.age",
                       encrypt(payload, settings["AGE_RECIPIENT"]), 2)
    foreign = encrypt(b"foreign synthetic state", settings["AGE_RECIPIENT"])
    for name in (
        "upcloud-prod-green-20260103T000000Z.tfstate.age",
        "hetzner-prod-20260103T000000Z.tfstate.age",
        "upcloud-prod-20260103T000000Z.extra.tfstate.age",
        "upcloud-prod-abcdefghTijklmnZ.tfstate.age",
    ):
        publish_backup(destination, name, foreign, 3)
    before = {path: path.read_bytes() for path in destination.iterdir()}

    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", recovery_recipe()], cwd=repo,
        check=False, env=settings, text=True, capture_output=True, timeout=20,
    )

    restored = provider_root / "terraform.tfstate"
    if available:
        assert result.returncode == 0, result.stderr
        assert restored.read_bytes() == payload
        assert restored.stat().st_mode & 0o777 == 0o600
    else:
        assert result.returncode != 0
        assert "no state backup for upcloud/prod" in result.stderr
        assert not restored.exists()
    assert {path: path.read_bytes() for path in destination.iterdir()} == before


def synthetic_state(repo):
    path = repo / 'terraform/providers/upcloud/terraform.tfstate'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"version":4,"serial":123,"resources":[]}\n')
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
    environment = settings | {'PATH': str(tools) + os.pathsep + settings['PATH']}
    argv = ['bash', str(repo / 'scripts/backup-tf-state.sh')]
    first = subprocess.run(argv, check=False, env=environment, capture_output=True, timeout=20)
    assert first.returncode == 0
    output = destination / 'upcloud-prod-20260101T000000Z.tfstate.age'
    before = output.read_bytes()
    state.write_bytes(b'newer synthetic state')
    second = subprocess.run(argv, check=False, env=environment, capture_output=True, timeout=20)
    assert second.returncode != 0
    assert output.read_bytes() == before
    assert list(destination.iterdir()) == [output]
    assert subprocess.run(['age', '-d', '-i', str(identity), str(output)], capture_output=True, check=True).stdout != state.read_bytes()
