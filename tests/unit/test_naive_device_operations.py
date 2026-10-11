"""Real encrypted per-device writes preserve unrelated material and permissions."""

import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "naive_device", ROOT / "scripts/naive-client.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def encrypted(tmp_path, monkeypatch):
    assert shutil.which("sops") and shutil.which(
        "age-keygen"
    ), "pinned encryption tools required"
    identity = tmp_path / "age.key"
    result = subprocess.run(["age-keygen", "-o", str(identity)], capture_output=True)
    assert result.returncode == 0
    recipient = subprocess.check_output(
        ["age-keygen", "-y", str(identity)], text=True
    ).strip()
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(identity))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AUDIT_LOG_FILE", str(tmp_path / "audit.log.age"))
    document = {
        "unrelated": {"keep": "fixture-private-marker"},
        "naive_secrets": {"server_name": "proxy.example.test", "clients": []},
        "xray": {"clients": []},
        "hysteria": {"masquerade_type": "proxy", "masquerade_url": "https://owned.example", "clients": []},
        "amneziawg_secrets": {"server_private_key": base64.b64encode(bytes([8]) * 32).decode(),
                              "jc": 4, "jmin": 40, "jmax": 70, "s1": 50, "s2": 100,
                              "h1": 11, "h2": 12, "h3": 13, "h4": 14, "peers": []},
        "client_registry": {},
    }
    path = tmp_path / "devices.sops.yaml"
    result = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--age",
            recipient,
            "--input-type",
            "json",
            "--output-type",
            "yaml",
            "/dev/stdin",
        ],
        input=json.dumps(document).encode(),
        capture_output=True,
    )
    assert result.returncode == 0
    path.write_bytes(result.stdout)
    path.chmod(0o600)
    return path, document


def decrypt(path):
    return json.loads(
        subprocess.check_output(
            ["sops", "--decrypt", "--output-type", "json", str(path)]
        )
    )


def test_two_devices_readout_and_independent_then_last_revocation(encrypted):
    path, original = encrypted
    module.operate(path, "issue", "first")
    module.operate(path, "issue", "second")
    document = decrypt(path)
    clients = document["naive_secrets"]["clients"]
    assert [client["name"] for client in clients] == ["first", "second"]
    assert len({client["password"] for client in clients}) == 2
    assert document["unrelated"] == original["unrelated"]
    first = module.operate(path, "readout", "first")
    assert first == {"server_name": "proxy.example.test", **clients[0]}
    assert clients[1]["password"] not in json.dumps(first)
    module.operate(path, "revoke", "first")
    assert decrypt(path)["naive_secrets"]["clients"] == [clients[1]]
    module.operate(path, "revoke", "second")
    assert decrypt(path)["naive_secrets"]["clients"] == []
    assert path.stat().st_mode & 0o777 == 0o600
    assert b"fixture-private-marker" not in path.read_bytes()
    assert not list(path.parent.glob(".*.naive-client.*"))


def test_lock_duplicate_and_unknown_revoke_preserve_ciphertext(encrypted):
    path, _ = encrypted
    module.operate(path, "issue", "first")
    before = path.read_bytes()
    for action, name in (("issue", "first"), ("revoke", "missing")):
        with pytest.raises(ValueError):
            module.operate(path, action, name)
        assert path.read_bytes() == before
    descriptor = os.open(str(path) + ".new-client.lock", os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            module.operate(path, "issue", "second")
        assert path.read_bytes() == before
    finally:
        os.close(descriptor)


def test_failed_encrypted_set_is_redacted_and_preserves_original(
    encrypted, monkeypatch, capsys
):
    path, _ = encrypted
    before = path.read_bytes()
    real = module.run_sops

    def fail_set(argv, **kwargs):
        if argv[0] == "set":
            raise RuntimeError("fixture-sensitive-operation")
        return real(argv, **kwargs)

    monkeypatch.setattr(module, "run_sops", fail_set)
    monkeypatch.setattr(
        "sys.argv", ["naive-client.py", "issue", "first", "--file", str(path)]
    )
    assert module.main() == 1
    output = capsys.readouterr()
    assert "sensitive" not in output.err and "fixture-private-marker" not in output.err
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".*.naive-client.*"))


def test_foreign_alias_authority_is_refused_before_encrypted_read(encrypted):
    path, _ = encrypted
    alias = path.parent / "alias.yaml"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        module.operate(alias, "issue", "first")
    hardlink = path.parent / "linked.yaml"
    os.link(path, hardlink)
    with pytest.raises(ValueError):
        module.operate(path, "issue", "first")


@pytest.mark.parametrize("field", ["CLIENT", "SOPS_FILE", "OUTPUT"])
@pytest.mark.parametrize("value_kind", ["make", "shell"])
def test_make_keeps_device_and_document_arguments_literal(tmp_path, field, value_kind):
    marker = tmp_path / "expanded"
    value = f"$(shell touch {marker})" if value_kind == "make" else f"$(touch {marker})"
    arguments = {
        "CLIENT": "first",
        "SOPS_FILE": str(tmp_path / "absent.yaml"),
        "OUTPUT": str(tmp_path / "selected.json"),
        field: value,
    }
    result = subprocess.run(
        [
            "make",
            "naive-readout" if field == "OUTPUT" else "naive-issue",
            *(f"{key}={item}" for key, item in arguments.items()),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert not marker.exists()


def test_writable_document_directory_is_refused_before_decryption(
    encrypted, monkeypatch
):
    path, _ = encrypted
    before = path.read_bytes()
    path.parent.chmod(0o777)
    try:
        with pytest.raises(ValueError, match="directory"):
            module.operate(path, "issue", "first")
        assert path.read_bytes() == before
    finally:
        path.parent.chmod(0o700)


def test_all_profile_issuer_includes_optional_naive_in_same_encrypted_commit(encrypted):
    path, original = encrypted
    assert shutil.which("wg") and shutil.which("uuidgen")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/new-client.sh"), "first"],
        env={**os.environ, "SOPS_FILE": str(path)},
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    document = decrypt(path)
    assert document["unrelated"] == original["unrelated"]
    assert [item["name"] for item in document["naive_secrets"]["clients"]] == ["first"]
    assert all(
        block[0]["name"] == "first"
        for block in (
            document["xray"]["clients"],
            document["hysteria"]["clients"],
            document["amneziawg_secrets"]["peers"],
        )
    )
    assert document["client_registry"]["first"]["status"] == "issued"
    assert "password" not in result.stdout
    assert not list(path.parent.glob(".*.new-client.*"))


def test_real_readout_publishes_only_selected_device_without_terminal_credentials(
    encrypted, monkeypatch, capsys
):
    source, _ = encrypted
    module.operate(source, "issue", "first")
    module.operate(source, "issue", "second")
    before = source.read_bytes()
    clients = decrypt(source)["naive_secrets"]["clients"]
    destination = source.parent / "selected.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "naive-client.py",
            "readout",
            "first",
            "--file",
            str(source),
            "--output",
            str(destination),
        ],
    )
    assert module.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "device": "first",
        "action": "readout",
        "output": str(destination),
    }
    for client in clients:
        assert client["password"] not in output.out + output.err
    assert "password" not in output.out + output.err
    assert json.loads(destination.read_text()) == {
        "server_name": "proxy.example.test",
        **clients[0],
    }
    assert clients[1]["password"] not in destination.read_text()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_nlink == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "kind", ["file", "directory", "symlink", "dangling", "hardlink"]
)
def test_existing_output_authority_refuses_before_decryption(
    tmp_path, monkeypatch, kind
):
    destination = tmp_path / "selected.json"
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"foreign-preserved")
    if kind == "file":
        destination.write_bytes(b"existing-preserved")
    elif kind == "directory":
        destination.mkdir()
    elif kind == "hardlink":
        os.link(foreign, destination)
    else:
        destination.symlink_to(foreign if kind == "symlink" else tmp_path / "absent")
    before = destination.lstat()

    def forbidden_read(*args):
        pytest.fail("unsafe output must refuse before encrypted input is read")

    monkeypatch.setattr(module, "operate", forbidden_read)
    with pytest.raises(ValueError, match="already exists"):
        module.export_readout(tmp_path / "source", "first", destination)
    assert destination.lstat() == before
    assert foreign.read_bytes() == b"foreign-preserved"


@pytest.mark.parametrize("mode", [0o750, 0o755, 0o777])
def test_shared_output_directory_refuses_before_decryption(tmp_path, monkeypatch, mode):
    tmp_path.chmod(mode)
    monkeypatch.setattr(
        module, "operate", lambda *args: pytest.fail("unsafe output must not decrypt")
    )
    try:
        with pytest.raises(ValueError, match="directory"):
            module.export_readout(
                tmp_path / "source", "first", tmp_path / "selected.json"
            )
        assert not (tmp_path / "selected.json").exists()
    finally:
        tmp_path.chmod(0o700)


def test_partial_output_failure_removes_only_owned_artifact_and_closes_descriptors(
    tmp_path, monkeypatch
):
    destination = tmp_path / "selected.json"
    monkeypatch.setattr(
        module,
        "operate",
        lambda *args: {"name": "first", "password": "synthetic-private-material"},
    )
    opened, closed = [], []
    real_open, real_close, real_write = os.open, os.close, os.write

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def record_close(fd):
        closed.append(fd)
        return real_close(fd)

    def partial_write(fd, data):
        real_write(fd, data[:3])
        raise OSError("synthetic write failure")

    monkeypatch.setattr(module.os, "open", record_open)
    monkeypatch.setattr(module.os, "close", record_close)
    monkeypatch.setattr(module.os, "write", partial_write)
    with pytest.raises(OSError, match="write failure"):
        module.export_readout(tmp_path / "source", "first", destination)
    assert not destination.exists()
    assert sorted(opened) == sorted(closed)


def test_swapped_output_preserves_foreign_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "selected.json"
    monkeypatch.setattr(
        module, "operate", lambda *args: {"password": "synthetic-private-material"}
    )
    real_write = os.write

    def swap_after_write(fd, data):
        written = real_write(fd, data)
        destination.unlink()
        destination.write_bytes(b"foreign-replacement-preserved")
        return written

    monkeypatch.setattr(module.os, "write", swap_after_write)
    with pytest.raises(ValueError, match="authority changed"):
        module.export_readout(tmp_path / "source", "first", destination)
    assert destination.read_bytes() == b"foreign-replacement-preserved"


def test_writable_output_ancestor_refuses_before_decryption(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    private = shared / "private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(
        module, "operate", lambda *args: pytest.fail("unsafe ancestry must not decrypt")
    )
    with pytest.raises(ValueError, match="ancestry"):
        module.export_readout(tmp_path / "source", "first", private / "selected.json")
    assert not (private / "selected.json").exists()


def test_tracked_output_path_refuses_before_decryption(monkeypatch):
    monkeypatch.setattr(
        module, "operate", lambda *args: pytest.fail("tracked output must not decrypt")
    )
    with pytest.raises(ValueError, match="tracked source"):
        module.export_readout(ROOT / "absent", "first", ROOT / "selected-device.json")


def test_source_directory_metadata_failure_closes_acquired_parent(
    tmp_path, monkeypatch
):
    acquired, closed = [], []
    real_open, real_close = os.open, os.close

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def record_close(fd):
        closed.append(fd)
        return real_close(fd)

    def fail_metadata(fd):
        raise OSError("synthetic source metadata failure")

    monkeypatch.setattr(module.os, "open", record_open)
    monkeypatch.setattr(module.os, "close", record_close)
    monkeypatch.setattr(module.os, "fstat", fail_metadata)
    with pytest.raises(OSError, match="source metadata failure"):
        module.operate(tmp_path / "source", "readout", "first")
    assert len(acquired) == 1
    assert acquired == closed


def test_encrypted_candidate_cleanup_failure_still_closes_source_authority(
    encrypted, monkeypatch
):
    path, _ = encrypted
    before = path.read_bytes()
    acquired, closed = [], []
    real_open, real_close, real_sops = os.open, os.close, module.run_sops

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        acquired.append(fd)
        return fd

    def record_close(fd):
        closed.append(fd)
        return real_close(fd)

    def fail_set(arguments, **kwargs):
        if arguments[0] == "set":
            raise RuntimeError("synthetic encrypted update failure")
        return real_sops(arguments, **kwargs)

    def fail_cleanup(*args, **kwargs):
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(module.os, "open", record_open)
    monkeypatch.setattr(module.os, "close", record_close)
    monkeypatch.setattr(module, "run_sops", fail_set)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(OSError, match="cleanup failure"):
        module.operate(path, "issue", "first")
    assert acquired[:3] == list(reversed(closed[-3:]))
    assert path.read_bytes() == before
