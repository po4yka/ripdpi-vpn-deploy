"""Portable AWG publication policy and inode compensation; no native VPN proof."""

import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ansible/roles/runtime-release/files/transport_runtime_transaction.py"
MIB = 1024 * 1024


@pytest.fixture
def core():
    spec = importlib.util.spec_from_file_location("runtime_awg_profile", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def area(private_authority_path):
    root = private_authority_path.resolve()
    os.chown(root, -1, os.getgid())
    return root


def write(path, content, mode=0o644):
    path.write_bytes(content)
    path.chmod(mode)
    os.chown(path, -1, os.getgid())
    return path


def candidate(path, content, mode=0o600):
    return {"path": str(path), "data": base64.b64encode(content).decode(),
            "mode": mode, "gid": os.getgid()}


@pytest.fixture
def canonical_files(core, area, monkeypatch):
    """Map canonical lookups to real owned files, without touching /usr or /opt."""
    observed = {}
    native_node = core.node

    def resolve(path, uid, **kwargs):
        selected = observed.get(str(path))
        return None if selected is None else native_node(selected, uid, **kwargs)

    monkeypatch.setattr(core, "node", resolve)

    def transaction(awg):
        selected = core.Transaction(area / "state", uid=os.getuid(), awg=awg)
        # Only canonical parent/storage lookup is virtual. Executable admission,
        # hashing, source modes and byte limits use the production implementation.
        monkeypatch.setattr(selected, "parent", lambda _path: None)
        monkeypatch.setattr(selected, "storage", Path)
        return selected

    return observed, transaction


@pytest.mark.parametrize("awg,target,source,mode,accepted", [
    (True, "/usr/local/bin/amneziawg-go", "/opt/amneziawg/releases/go-" + "a" * 40 + "/amneziawg-go", 0o755, True),
    (True, "/usr/local/bin/amneziawg-go", "/opt/amneziawg/releases/go-" + "a" * 40 + "-" + "d" * 64 + "/amneziawg-go", 0o755, True),
    (True, "/usr/local/bin/amneziawg-go", "/opt/amneziawg/releases/go-" + "a" * 40 + "-" + "d" * 63 + "/amneziawg-go", 0o755, False),
    (True, "/usr/local/bin/amneziawg-go", "/opt/amneziawg/releases/go-" + "a" * 40 + "-" + "D" * 64 + "/amneziawg-go", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 40 + "-" + "d" * 64 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 64 + "/awg", 0o755, True),
    (True, "/usr/bin/awg-quick", "/opt/amneziawg/releases/tools-" + "c" * 40 + "/awg-quick", 0o755, True),
    (False, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 40 + "/awg", 0o755, False),
    (True, "/usr/bin/unrelated", "/opt/amneziawg/releases/tools-" + "b" * 40 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 39 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 65 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 41 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 63 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "B" * 40 + "/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-latest/awg", 0o755, False),
    (True, "/usr/bin/awg", "/opt/amneziawg/releases/tools-" + "b" * 40 + "/another", 0o755, False),
    (False, "/etc/transport/asset", "/opt/transport/asset", 0o644, True),
    (False, "/etc/transport/asset", "/opt/transport/asset", 0o755, False),
])
def test_source_admission_keeps_executables_awg_scoped(
        core, area, canonical_files, awg, target, source, mode, accepted):
    observed, transaction = canonical_files
    payload = write(area / "immutable-source", b"synthetic executable or asset", mode)
    observed[source] = payload
    value = {"path": target, "source": source, "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
             "mode": mode, "gid": os.getgid()}
    tx = transaction(awg)
    if accepted:
        tx.validate([value])
    else:
        with pytest.raises(core.Refusal, match="asset-authority-invalid"):
            tx.validate([value])
    assert payload.read_bytes() == b"synthetic executable or asset"


@pytest.mark.parametrize("awg,path,size,accepted", [
    (False, "/usr/bin/awg", MIB, True),
    (False, "/usr/bin/awg", MIB + 1, False),
    (True, "/usr/bin/awg", MIB + 1, True),
    (True, "/usr/bin/awg", 128 * MIB, True),
    (True, "/usr/bin/awg", 128 * MIB + 1, False),
    (True, "/etc/amnezia/amneziawg/awg0.conf", MIB, True),
    (True, "/etc/amnezia/amneziawg/awg0.conf", MIB + 1, False),
])
def test_executable_byte_budget_does_not_expand_other_files(
        core, area, canonical_files, awg, path, size, accepted):
    observed, transaction = canonical_files
    payload = write(area / "bounded-file", b"", 0o755 if path.endswith("/awg") else 0o600)
    with payload.open("r+b") as stream:
        stream.truncate(size)
    observed[path] = payload
    if accepted:
        result = transaction(awg)._node(Path(path))
        assert len(result["sha256"]) == 64
        assert result["identity"][1] == payload.stat().st_ino
    else:
        with pytest.raises(core.Refusal, match="unsafe-node"):
            transaction(awg)._node(Path(path))


class Lifecycle:
    """Service lifecycle double; every publication and rollback uses real files."""

    def __init__(self, core, files=()):
        self.core, self.files = core, files
        self.running = False
        self.restore_expected = None
        self.restored = False
        self.activations = []

    def retained(self, _receipt):
        pass

    def validate(self):
        pass

    def validate_units(self, units):
        if set(units) != {"running"} or type(units["running"]) is not bool:
            raise self.core.Refusal("unit-state-invalid")

    def inspect(self):
        return {"running": self.running}

    def stop(self):
        self.running = False

    def start(self):
        self.activations.append(snapshot(self.files))
        if self.files:
            binary, unit, _config = self.files
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=3)
            if unit.read_bytes().startswith(b"rejected"):
                raise RuntimeError("synthetic unit activation refusal")
        self.running = True

    def ready(self):
        assert self.running

    def ensure(self):
        changed = not self.running
        if changed:
            self.start()
        return changed

    def restore(self, units):
        if self.restore_expected is not None:
            assert snapshot(self.files) == self.restore_expected
        if units is not None and units["running"]:
            self.start()
        else:
            self.running = False
        self.restored = True


def snapshot(files):
    return {str(path): (path.read_bytes(), path.stat().st_ino, stat.S_IMODE(path.stat().st_mode))
            for path in files}


@pytest.mark.parametrize("awg,count,accepted", [(False, 64, True), (False, 65, False),
                                              (True, 65, True), (True, 128, True), (True, 129, False)])
def test_profile_node_budget_round_trips_actual_publication_and_receipt(core, area, awg, count, accepted):
    live = area / "live"
    live.mkdir()
    live.chmod(0o755)
    os.chown(live, -1, os.getgid())
    plan = [candidate(live / f"config-{index}", f"value-{index}".encode()) for index in range(count)]
    adapter = Lifecycle(core)
    state = area / "state"
    if not accepted:
        with core.Transaction(state, uid=os.getuid(), awg=awg) as tx:
            with pytest.raises(core.Refusal, match="candidate-invalid"):
                tx.apply(plan, adapter)
        assert not list(live.iterdir()) and not adapter.running
        return
    with core.Transaction(state, uid=os.getuid(), awg=awg) as tx:
        result = tx.apply(plan, adapter)
        receipt = tx.accepted()
    assert result["published"] and len(receipt["nodes"]) == count and adapter.running
    before = snapshot([Path(item["path"]) for item in plan])
    with core.Transaction(state, uid=os.getuid(), awg=awg) as tx:
        assert not tx.apply(plan, adapter)["changed"]
        assert tx.accepted() == receipt
    assert snapshot([Path(item["path"]) for item in plan]) == before


@pytest.mark.parametrize("rejected", ["binary", "unit"])
def test_activation_refusal_restores_binary_unit_config_and_original_inodes(core, area, monkeypatch, rejected):
    live, releases = area / "live", area / "releases"
    live.mkdir()
    releases.mkdir()
    for directory in (live, releases):
        directory.chmod(0o755)
        os.chown(directory, -1, os.getgid())
    binary, unit, config = live / "amneziawg-go", live / "awg-quick@.service", live / "awg0.conf"
    old = write(releases / "old", b"#!/bin/sh\n# accepted runtime\nexit 0\n", 0o755)
    new = write(releases / "new", b"#!/bin/sh\n# candidate runtime\nexit "
                + (b"7\n" if rejected == "binary" else b"0\n"), 0o755)
    allowed = {binary, old, new}
    # Canonical executable names are tested above. Only this confined publication
    # fixture substitutes its private executable locations for the policy paths.
    monkeypatch.setattr(core.Transaction, "executable", lambda _self, path: Path(path) in allowed)

    def plan(source, unit_bytes, config_bytes):
        return [{"path": str(binary), "source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                 "mode": 0o755, "gid": os.getgid()}, candidate(unit, unit_bytes, 0o644),
                candidate(config, config_bytes)]

    state = area / "state"
    adapter = Lifecycle(core, (binary, unit, config))
    with core.Transaction(state, uid=os.getuid(), awg=True) as tx:
        tx.apply(plan(old, b"accepted unit", b"accepted config"), adapter)
    original = snapshot(adapter.files)
    receipt = (state / "accepted.json").read_bytes()
    adapter.restore_expected = original
    upgrade = plan(new, b"rejected unit" if rejected == "unit" else b"candidate unit", b"candidate config")
    with core.Transaction(state, uid=os.getuid(), awg=True) as tx:
        with pytest.raises(core.Refusal, match="candidate-refused"):
            tx.apply(upgrade, adapter)
        assert tx.accepted() is not None
    assert adapter.activations[-2] != original and adapter.activations[-1] == original
    assert adapter.restored and adapter.running
    assert snapshot(adapter.files) == original
    assert (state / "accepted.json").read_bytes() == receipt
    assert not (state / "pending.json").exists()
