"""Exercise the private rollback CLI on a current-UID temporary filesystem root."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

HELPER = (
    Path(__file__).resolve().parents[2]
    / "ansible/roles/observability_control_plane/files/observability-authority-snapshot.py"
)
CONFIG = "etc/observability-control-plane"
CREDENTIALS = CONFIG + "/credentials"
SNAPSHOT = CONFIG + "/.authority-rollback/snapshot.json"
SERVICES = {
    "observability-alertmanager.service": {
        "exists": True,
        "active": True,
        "enabled": True,
    },
    "observability-silence-gateway.service": {
        "exists": True,
        "active": True,
        "enabled": True,
    },
    "observability-prometheus.service": {
        "exists": True,
        "active": True,
        "enabled": True,
    },
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    # The alternate root is a filesystem fixture, not production root authority.
    root = tmp_path / "host"
    root.mkdir(mode=0o700)
    for relative in (
        CREDENTIALS,
        CONFIG + "/generations",
        "etc/systemd/system",
        "usr/local/libexec",
    ):
        (root / relative).mkdir(parents=True, mode=0o700)
    return root


def write(root: Path, relative: str, content: bytes, mode: int = 0o600) -> Path:
    path = root / relative
    path.write_bytes(content)
    path.chmod(mode)
    return path


def invoke(
    root: Path,
    action: str,
    identifier: str | None = None,
    owners: list[str] | None = None,
):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            HELPER.read_text(),
            action,
            str(root),
            *([identifier] if identifier else []),
        ],
        input=json.dumps({"owners": owners or [], "services": SERVICES}),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def prepare(root: Path, owners: list[str] | None = None) -> dict:
    result = invoke(root, "prepare", owners=owners)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_snapshot_larger_than_one_source_file_remains_restorable(root: Path) -> None:
    payload = b"private-fixture-material\x00" * 9000
    path = write(root, CREDENTIALS + "/silence-backend-ca.pem", payload)
    prepared = prepare(root)
    assert (root / SNAPSHOT).stat().st_size > 262144
    path.write_bytes(b"replacement")
    result = invoke(root, "restore", prepared["id"])
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == payload


def test_all_32_owners_can_rotate_without_losing_previous_tokens(root: Path) -> None:
    previous = [f"previous-{index}" for index in range(32)]
    candidate = [f"candidate-{index}" for index in range(32)]
    write(
        root,
        CREDENTIALS + "/silence-auth.json",
        json.dumps(
            {
                "owners": [
                    {"owner": owner, "token_sha256": "a" * 64} for owner in previous
                ],
                "sender_token_sha256": "b" * 64,
            }
        ).encode(),
    )
    for owner in previous:
        write(root, CREDENTIALS + f"/silence-owner-{owner}-token", owner.encode())
    prepared = prepare(root, candidate)
    assert prepared["previous_owners"] == previous
    for owner in previous:
        (root / CREDENTIALS / f"silence-owner-{owner}-token").unlink()
    for owner in candidate:
        write(root, CREDENTIALS + f"/silence-owner-{owner}-token", b"new-token")
    result = invoke(root, "restore", prepared["id"])
    assert result.returncode == 0, result.stderr
    assert all(
        (root / CREDENTIALS / f"silence-owner-{owner}-token").read_bytes()
        == owner.encode()
        for owner in previous
    )
    assert all(
        not (root / CREDENTIALS / f"silence-owner-{owner}-token").exists()
        for owner in candidate
    )


def test_restore_preserves_bytes_metadata_links_absence_and_private_output(
    root: Path,
) -> None:
    secret = b"fixture-secret-must-not-reach-stdout\x00\xff\n"
    token = write(root, CREDENTIALS + "/silence-sender-token", secret)
    program = write(
        root, "usr/local/libexec/observability-silence-gateway", b"old-program\n", 0o755
    )
    before = {path: path.stat() for path in (token, program)}
    target = root / CONFIG / "generations" / ("alertmanager-" + "a" * 64 + ".yml")
    target.write_bytes(b"old-config")
    current = root / CONFIG / "alertmanager-current.yml"
    current.symlink_to(target)
    prepared = prepare(root, ["candidate"])
    assert set(prepared) == {"id", "previous_owners", "services"}
    assert prepared["services"] == SERVICES
    snapshot = root / SNAPSHOT
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshot.parent.stat().st_mode) == 0o700
    token.write_bytes(b"rotated")
    program.write_bytes(b"new-program")
    program.chmod(0o700)
    current.unlink()
    created = write(
        root, CREDENTIALS + "/silence-owner-candidate-token", b"candidate-token"
    )
    result = invoke(root, "restore", prepared["id"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""
    assert token.read_bytes() == secret
    assert program.read_bytes() == b"old-program\n"
    for path, original in before.items():
        restored = path.stat()
        assert (stat.S_IMODE(restored.st_mode), restored.st_uid, restored.st_gid) == (
            stat.S_IMODE(original.st_mode),
            original.st_uid,
            original.st_gid,
        )
    assert current.is_symlink() and current.readlink() == target
    assert not created.exists()
    finished = invoke(root, "finish", prepared["id"])
    assert finished.returncode == 0 and finished.stdout == ""
    assert not snapshot.parent.exists()


@pytest.mark.parametrize(
    "unsafe",
    [
        "credential-link",
        "ancestor-link",
        "writable-ancestor",
        "writable-credential",
        "hardlink",
        "fifo",
    ],
)
def test_prepare_refuses_unsafe_paths_without_touching_external_bytes(
    root: Path, unsafe: str
) -> None:
    outside = root.parent / "outside"
    outside.mkdir(mode=0o700)
    external = write(outside, "sensitive", b"external-fixture-secret")
    credential = root / CREDENTIALS / "silence-sender-token"
    if unsafe == "credential-link":
        credential.symlink_to(external)
    elif unsafe == "ancestor-link":
        (root / CREDENTIALS).rmdir()
        (root / CREDENTIALS).symlink_to(outside, target_is_directory=True)
    elif unsafe == "writable-ancestor":
        (root / "etc").chmod(0o777)
    elif unsafe == "writable-credential":
        write(root, CREDENTIALS + "/silence-sender-token", b"fixture-secret", 0o666)
    elif unsafe == "fifo":
        os.mkfifo(credential, 0o600)
    else:
        os.link(external, credential)
    result = invoke(root, "prepare")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "secret" not in result.stderr
    assert external.read_bytes() == b"external-fixture-secret"
    assert not (root / SNAPSHOT).exists()


@pytest.mark.parametrize("action", ["restore", "finish", "mark"])
def test_foreign_identifier_cannot_read_restore_or_remove_snapshot(
    root: Path, action: str
) -> None:
    prepared = prepare(root)
    snapshot = root / SNAPSHOT
    original = snapshot.read_bytes()
    result = invoke(root, action, "0" * 32)
    assert prepared["id"] != "0" * 32
    assert result.returncode == 1 and result.stdout == ""
    assert snapshot.read_bytes() == original


@pytest.mark.parametrize("foreign", ["entry", "write-set", "mode", "symlink"])
def test_foreign_snapshot_content_is_not_consumed_or_deleted(
    root: Path, foreign: str
) -> None:
    prepared = prepare(root)
    snapshot = root / SNAPSHOT
    external = write(root.parent, "unrelated", b"unchanged")
    if foreign == "entry":
        write(snapshot.parent, "unrelated", b"preserve")
    elif foreign == "write-set":
        state = json.loads(snapshot.read_text())
        state["files"]["../unrelated"] = {"kind": "absent"}
        snapshot.write_text(json.dumps(state))
    elif foreign == "mode":
        snapshot.chmod(0o644)
    else:
        snapshot.unlink()
        snapshot.symlink_to(external)
    result = invoke(root, "finish", prepared["id"])
    assert result.returncode == 1 and result.stdout == ""
    assert snapshot.parent.exists()
    assert external.read_bytes() == b"unchanged"


def test_failed_restore_retains_manual_recovery_and_blocks_next_publication(
    root: Path,
) -> None:
    token = write(root, CREDENTIALS + "/silence-sender-token", b"old-private-fixture")
    prepared = prepare(root)
    external = write(root.parent, "outside-token", b"external-private-fixture")
    token.unlink()
    token.symlink_to(external)
    result = invoke(root, "restore", prepared["id"])
    assert result.returncode == 1 and result.stdout == ""
    assert "private-fixture" not in result.stderr
    assert external.read_bytes() == b"external-private-fixture"
    snapshot = root / SNAPSHOT
    assert json.loads(snapshot.read_text())["phase"] == "manual-recovery"
    retry = invoke(root, "prepare")
    assert retry.returncode == 1 and retry.stdout == ""
    assert snapshot.exists()


def test_oversized_source_is_refused_before_snapshot_creation(root: Path) -> None:
    write(root, CREDENTIALS + "/silence-sender-token", b"x" * 262145)
    result = invoke(root, "prepare")
    assert result.returncode == 1 and result.stdout == ""
    assert not (root / SNAPSHOT).exists()


def test_mark_retains_snapshot_and_finish_removes_only_owned_evidence(
    root: Path,
) -> None:
    unrelated = write(root, CONFIG + "/unrelated", b"keep")
    prepared = prepare(root)
    result = invoke(root, "mark", prepared["id"])
    assert result.returncode == 0 and result.stdout == ""
    assert json.loads((root / SNAPSHOT).read_text())["phase"] == "manual-recovery"
    assert invoke(root, "prepare").returncode == 1
    assert invoke(root, "finish", prepared["id"]).returncode == 0
    assert unrelated.read_bytes() == b"keep"


def test_oversized_snapshot_is_not_loaded_or_deleted(root: Path) -> None:
    prepared = prepare(root)
    snapshot = root / SNAPSHOT
    payload = b" " * 8388609
    snapshot.write_bytes(payload)
    result = invoke(root, "finish", prepared["id"])
    assert result.returncode == 1 and result.stdout == ""
    assert snapshot.stat().st_size == len(payload)


def test_aggregate_write_limit_does_not_publish_truncated_recovery(root: Path) -> None:
    owners = [f"owner-{index}" for index in range(32)]
    for owner in owners:
        write(root, CREDENTIALS + f"/silence-owner-{owner}-token", b"x" * 262144)
    result = invoke(root, "prepare", owners=owners)
    assert result.returncode == 1 and result.stdout == ""
    snapshot = root / SNAPSHOT
    assert not snapshot.exists()
    assert snapshot.parent.exists()
    assert invoke(root, "prepare", owners=owners).returncode == 1


def test_production_root_requires_effective_root_before_filesystem_access() -> None:
    # UID injection exercises the authorization guard without touching host '/'.
    source = "import os\nos.geteuid = lambda: 12345\n" + HELPER.read_text().replace(
        "from __future__ import annotations", ""
    )
    result = subprocess.run(
        [sys.executable, "-c", source, "prepare", "/"],
        input="{}",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1 and result.stdout == ""
    assert (
        result.stderr
        == "authority snapshot refused; private recovery may be required\n"
    )
