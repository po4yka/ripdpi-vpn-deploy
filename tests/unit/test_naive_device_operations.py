"""Real encrypted per-device writes preserve unrelated material and permissions."""

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
        "hysteria": {"clients": []},
        "amneziawg_secrets": {"peers": []},
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


@pytest.mark.parametrize("field", ["CLIENT", "SOPS_FILE"])
@pytest.mark.parametrize("value_kind", ["make", "shell"])
def test_make_keeps_device_and_document_arguments_literal(tmp_path, field, value_kind):
    marker = tmp_path / "expanded"
    value = f"$(shell touch {marker})" if value_kind == "make" else f"$(touch {marker})"
    arguments = {
        "CLIENT": "first",
        "SOPS_FILE": str(tmp_path / "absent.yaml"),
        field: value,
    }
    result = subprocess.run(
        ["make", "naive-issue", *(f"{key}={item}" for key, item in arguments.items())],
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
