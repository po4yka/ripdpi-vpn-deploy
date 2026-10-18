"""Exercise exact environment retention and recovery with real age ciphertext."""

from datetime import datetime, timedelta, timezone
import os
import json
from pathlib import Path
import shutil
import subprocess

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
    for name in ("backup-tf-state.sh", "restore-tf-state.sh"):
        shutil.copy2(ROOT / "scripts" / name, repo / "scripts" / name)
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


def recovery_recipe():
    text = (ROOT / "docs/RUNBOOK-incident.md").read_text()
    recipe = text.split("# State backups live in", 1)[1].split("```", 1)[0]
    # Execute the documented selection and decryption. Provider work stays out.
    recipe = "# State backups live in" + recipe.split("PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh", 1)[0]
    return recipe + "true\n"


@pytest.mark.parametrize("available", [True, False])
def test_documented_recovery_selects_only_exact_environment(backup_workspace, available):
    repo, destination, _identity, settings = backup_workspace
    provider_root = repo / "terraform/providers/upcloud"
    provider_root.mkdir(parents=True)
    payload = state_bytes(7)
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
        env=settings, text=True, capture_output=True, timeout=20,
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


@pytest.mark.parametrize("failure", ["truncated", "wrong-key", "invalid-json", "invalid-state"])
def test_failed_restore_preserves_state_and_removes_private_candidate(backup_workspace, tmp_path, failure):
    repo, destination, _identity, settings = backup_workspace
    state = prepare_state(repo)
    prior, inode = state.read_bytes(), state.stat().st_ino
    payload = state_bytes(99)
    if failure == "invalid-json":
        payload = b'synthetic-private-state-not-json'
    elif failure == "invalid-state":
        payload = b'{"version":4,"serial":true,"lineage":"synthetic-private-state","resources":[]}'
    ciphertext = encrypt(payload, settings["AGE_RECIPIENT"])
    if failure == "truncated":
        ciphertext = ciphertext[:-5]
    publish_backup(destination, "upcloud-prod-20260101T000000Z.tfstate.age", ciphertext, 1)
    if failure == "wrong-key":
        identity = tmp_path / "wrong.key"
        subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
        settings = settings | {"AGE_IDENTITY": str(identity)}
    result = subprocess.run(["bash", str(repo / "scripts/restore-tf-state.sh")],
        env=settings | {"ENV": "prod"}, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert state.read_bytes() == prior and state.stat().st_ino == inode
    assert not list(state.parent.glob(".state-restore.*"))
    assert "synthetic-private-state" not in result.stdout + result.stderr


def test_nonprod_restore_uses_its_exact_state_path(backup_workspace):
    repo, destination, _identity, settings = backup_workspace
    prod = prepare_state(repo)
    selected = prepare_state(repo, "prod-green")
    payload = state_bytes(9)
    publish_backup(destination, "upcloud-prod-green-20260101T000000Z.tfstate.age",
                   encrypt(payload, settings["AGE_RECIPIENT"]), 1)
    result = subprocess.run(["bash", str(repo / "scripts/restore-tf-state.sh")],
        env=settings | {"ENV": "prod-green"}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert selected.read_bytes() == payload and prod.read_bytes() == state_bytes(1)
    assert selected.stat().st_mode & 0o777 == 0o600
    assert not list(selected.parent.glob(".state-restore.*"))


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
