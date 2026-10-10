"""Pinned paired publication preserves the previous usable generation."""

from __future__ import annotations
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def publisher():
    spec = importlib.util.spec_from_file_location(
        "geodata_publish", ROOT / "ansible/roles/geodata/files/geodata_publish.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def paths():
    with tempfile.TemporaryDirectory(
        prefix=".geodata-pair-", dir=Path.home()
    ) as directory:
        root = Path(directory)
        installed = root / "installed"
        installed.mkdir(mode=0o755)
        for name in ("geosite.dat", "geoip.dat"):
            (installed / name).write_bytes(("old-" + name).encode())
            (installed / name).chmod(0o640)
            (root / name).write_bytes(("new-" + name).encode())
        request = {
            "install_dir": str(installed),
            "sources": {
                name: {
                    "url": (root / name).as_uri(),
                    "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                }
                for name in ("geosite.dat", "geoip.dat")
            },
        }
        yield root, installed, request


def snapshot(installed):
    return {
        name: ((installed / name).read_bytes(), (installed / name).stat().st_mode)
        for name in ("geosite.dat", "geoip.dat")
    }


def test_pair_verifies_then_activates_once_and_repeat_is_unchanged(
    publisher, paths, monkeypatch
):
    root, installed, request = paths
    seen = []
    monkeypatch.setattr(
        publisher, "activate", lambda: (seen.append(snapshot(installed)), True)[1]
    )
    assert publisher.publish(request) == {"changed": True}
    assert len(seen) == 1 and all(
        value[0].startswith(b"new-") for value in seen[0].values()
    )
    assert publisher.publish(request) == {"changed": False} and len(seen) == 1
    assert not (installed / ".geodata-pending").exists()


@pytest.mark.parametrize("failure", ["missing", "checksum"])
def test_second_input_failure_preserves_both_old_bytes_and_metadata(
    publisher, paths, monkeypatch, failure
):
    root, installed, request = paths
    before = snapshot(installed)
    monkeypatch.setattr(
        publisher, "activate", lambda: pytest.fail("must not activate incomplete pair")
    )
    if failure == "missing":
        (root / "geoip.dat").unlink()
    else:
        request["sources"]["geoip.dat"]["sha256"] = "0" * 64
    with pytest.raises((ValueError, RuntimeError)):
        publisher.publish(request)
    assert (
        snapshot(installed) == before and not (installed / ".geodata-pending").exists()
    )


def test_failed_activation_restores_prior_complete_pair_and_reactivates(
    publisher, paths, monkeypatch
):
    root, installed, request = paths
    before = snapshot(installed)
    seen = []

    def activate():
        seen.append(snapshot(installed))
        if len(seen) == 1:
            raise RuntimeError("new activation failed")

    monkeypatch.setattr(publisher, "activate", activate)
    with pytest.raises(RuntimeError, match="publication-compensated"):
        publisher.publish(request)
    assert snapshot(installed) == before and seen[-1] == before and len(seen) == 2
    assert not (installed / ".geodata-pending").exists()


def test_failed_rollback_retains_private_recovery_and_rejects_reuse(
    publisher, paths, monkeypatch
):
    root, installed, request = paths
    monkeypatch.setattr(
        publisher, "activate", lambda: (_ for _ in ()).throw(RuntimeError("activation"))
    )
    with pytest.raises(RuntimeError, match="manual-recovery-required"):
        publisher.publish(request)
    pending = installed / ".geodata-pending"
    assert pending.stat().st_mode & 0o777 == 0o700
    assert (pending / "snapshot.json").stat().st_mode & 0o777 == 0o600
    assert (pending / "old-geosite.dat").read_bytes() == b"old-geosite.dat"
    with pytest.raises(RuntimeError):
        publisher.publish(request)


def test_concurrent_owner_or_symlink_input_refuses_before_publication(publisher, paths):
    root, installed, request = paths
    before = snapshot(installed)
    with (installed / ".geodata-lock").open("w") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            publisher.publish(request)
    (installed / "geoip.dat").unlink()
    (installed / "geoip.dat").symlink_to(root / "geoip.dat")
    with pytest.raises(ValueError, match="unsafe-file"):
        publisher.publish(request)
    assert (installed / "geosite.dat").read_bytes() == before["geosite.dat"][0]


def test_same_hash_owned_metadata_drift_republishes_before_adoption(
    publisher, paths, monkeypatch
):
    _, installed, request = paths
    calls = []
    monkeypatch.setattr(
        publisher, "activate", lambda: (calls.append(snapshot(installed)), True)[1]
    )
    assert publisher.publish(request)["changed"] is True
    for name in ("geosite.dat", "geoip.dat"):
        (installed / name).chmod(0o600)
    assert publisher.publish(request)["changed"] is True
    assert len(calls) == 2
    assert all(
        (installed / name).stat().st_mode & 0o777 == 0o644
        for name in ("geosite.dat", "geoip.dat")
    )
    assert publisher.publish(request)["changed"] is False


@pytest.mark.parametrize("malformed", ["boolean", "duplicate", "unknown"])
def test_malformed_activated_receipt_refuses_without_overwrite(
    publisher, paths, monkeypatch, malformed
):
    import json

    _, installed, request = paths
    receipt = installed / ".geodata-activated.json"
    value = dict(
        schema=True if malformed == "boolean" else 2,
        desired={name: source["sha256"] for name, source in request["sources"].items()},
        metadata=dict(mode=0o644, uid=os.geteuid(), gid=os.getegid()),
    )
    raw = json.dumps(value).encode()
    if malformed == "duplicate":
        raw = raw.replace(b'"schema": 2', b'"schema": 1, "schema": 1')
    receipt.write_bytes(raw)
    receipt.chmod(0o600)
    before = snapshot(installed)
    monkeypatch.setattr(
        publisher, "activate", lambda: pytest.fail("must not adopt invalid receipt")
    )
    with pytest.raises(ValueError):
        publisher.publish(request)
    assert receipt.read_bytes() == raw and snapshot(installed) == before
    assert not (installed / ".geodata-pending").exists()
