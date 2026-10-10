from pathlib import Path
import os
import pytest
from vpnd.config import Context
from vpnd.secrets import Secrets
from vpnd.protected_file import harden
import threading


def fake_ctx(root=Path("/repo"), explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "prod",
        "upcloud",
        Path("/config/prod.secrets.sops.yaml"),
        Path("/tmp/vpn-prod.secrets.yaml"),
        Path("/config"),
        explain,
        True,
    )


STUB_YAML = (
    "xray:\n  clients:\n    - name: phone\n      uuid: 00000000-0000-0000-0000-000000000000\n"
)
FIXTURE = (Path(__file__).resolve().parents[2] / "tests/fixtures/secrets-sample.yml").read_bytes()


def secret(tmp_path, payload=FIXTURE):
    path = tmp_path / "secrets.yaml"
    path.write_bytes(payload.encode() if isinstance(payload, str) else payload)
    path.chmod(0o600)
    return path


# Rust test: vpnd/tests/secrets_parse.rs::fixture_loads_without_error
def test_fixture_loads_without_error(tmp_path):
    Secrets.load(secret(tmp_path))


# Rust test: vpnd/tests/secrets_parse.rs::find_client_hit_returns_correct_client
def test_find_client_hit_returns_correct_client(tmp_path):
    assert Secrets.load(secret(tmp_path)).find_client("phone").name == "phone"


# Rust test: vpnd/tests/secrets_parse.rs::find_client_miss_returns_none
def test_find_client_miss_returns_none(tmp_path):
    assert Secrets.load(secret(tmp_path)).find_client("nonexistent-client-xyz") is None


# Rust test: vpnd/tests/secrets_parse.rs::extra_preserves_unknown_top_level_keys
def test_extra_preserves_unknown_top_level_keys(tmp_path):
    assert Secrets.load(secret(tmp_path)).extra_key_count() > 0


# Rust test: vpnd/tests/secrets_parse.rs::malformed_or_empty_secrets_fail_without_a_typed_payload
def test_malformed_or_empty_secrets_fail_without_a_typed_payload(tmp_path):
    for raw in ("", " \n", "[unclosed", "42", "xray: 7", "xray: {clients: [{uuid: secret}]}"):
        with pytest.raises(ValueError):
            Secrets.load(secret(tmp_path, raw))


# Rust test: vpnd/tests/secrets_parse.rs::load_fails_gracefully_for_missing_file
def test_load_fails_gracefully_for_missing_file():
    with pytest.raises(ValueError) as error:
        Secrets.load(Path("/nonexistent/path/secrets.yaml"))
    assert str(error.value)


# Rust test: vpnd/tests/secrets_parse.rs::load_rejects_group_readable_secrets
def test_load_rejects_group_readable_secrets(tmp_path):
    path = secret(tmp_path)
    path.chmod(0o640)
    with pytest.raises(ValueError):
        Secrets.load(path)


# Rust test: vpnd/tests/secrets_parse.rs::load_rejects_symlinked_secrets
def test_load_rejects_symlinked_secrets(tmp_path):
    path = secret(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        Secrets.load(link)


# Rust test: vpnd/tests/secrets_parse.rs::fixture_exposes_nginx_xhttp_server_name
def test_fixture_exposes_nginx_xhttp_server_name(tmp_path):
    assert Secrets.load(secret(tmp_path)).nginx_xhttp.server_name == "vpn.example.com"


# Rust test: vpnd/tests/secrets_gate.rs::hardening_rejects_missing_plaintext
def test_hardening_rejects_missing_plaintext(tmp_path):
    with pytest.raises(ValueError):
        harden(tmp_path / "missing.yaml")


# Rust test: vpnd/tests/secrets_gate.rs::hardening_rejects_symlinks_without_chmoding_the_target
def test_hardening_rejects_symlinks_without_chmoding_the_target(tmp_path):
    path = secret(tmp_path, "not a secret")
    path.chmod(0o644)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        harden(link)
    assert path.stat().st_mode & 0o777 == 0o644


# Rust test: vpnd/tests/secrets_gate.rs::hardening_regular_plaintext_sets_0600_and_keeps_it_readable
def test_hardening_regular_plaintext_sets_0600_and_keeps_it_readable(tmp_path):
    path = secret(tmp_path, STUB_YAML)
    path.chmod(0o644)
    harden(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert Secrets.load(path).find_client("phone") is not None


# Rust test: vpnd/tests/secrets_gate.rs::load_accepts_private_read_only_files
def test_load_accepts_private_read_only_files(tmp_path):
    path = secret(tmp_path, STUB_YAML)
    path.chmod(0o400)
    assert Secrets.load(path).find_client("phone") is not None


# Rust test: vpnd/tests/secrets_gate.rs::file_gates_reject_fifos_without_waiting_for_a_writer
def test_file_gates_reject_fifos_without_waiting_for_a_writer(tmp_path):
    import json
    import subprocess
    import sys

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    script = """import json, sys
from vpnd.protected_file import harden
from vpnd.secrets import Secrets
outcomes = []
for function in (harden, Secrets.load):
    try:
        function(sys.argv[1])
        outcomes.append(False)
    except ValueError:
        outcomes.append(True)
print(json.dumps(outcomes))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(fifo)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [True, True]


# Rust test: vpnd/tests/secrets_gate.rs::load_rejects_symlink_even_to_compliant_file
def test_load_rejects_symlink_even_to_compliant_file(tmp_path):
    path = secret(tmp_path, STUB_YAML)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="regular file"):
        Secrets.load(link)


# Rust test: vpnd/tests/secrets_gate.rs::load_rejects_loose_mode_on_held_handle
def test_load_rejects_loose_mode_on_held_handle(tmp_path):
    path = secret(tmp_path, STUB_YAML)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe owner, type, or permissions"):
        Secrets.load(path)


# Rust test: vpnd/tests/secrets_gate.rs::load_accepts_compliant_0600_regular_file
def test_load_accepts_compliant_0600_regular_file(tmp_path):
    assert Secrets.load(secret(tmp_path, STUB_YAML)).find_client("phone") is not None


# Rust test: vpnd/tests/secrets_gate.rs::file_gates_never_follow_concurrently_swapped_symlinks
def test_file_gates_never_follow_concurrently_swapped_symlinks(tmp_path):
    trusted = secret(tmp_path, STUB_YAML)
    other = tmp_path / "other.yaml"
    current = tmp_path / "current.yaml"
    nxt = tmp_path / "next.yaml"
    other.write_text("xray:\n  clients:\n    - name: redirected\n")
    other.chmod(0o600)
    os.link(trusted, current)
    running = threading.Event()
    running.set()

    def writer():
        while running.is_set():
            nxt.symlink_to(other)
            os.replace(nxt, current)
            os.link(trusted, nxt)
            os.replace(nxt, current)

    thread = threading.Thread(target=writer)
    thread.start()
    reads = 0
    redirected = 0
    try:
        for _ in range(5000):
            try:
                loaded = Secrets.load(current)
            except ValueError:
                continue
            reads += 1
            redirected += loaded.find_client("redirected") is not None
        other.chmod(0o644)
        for _ in range(5000):
            try:
                harden(current)
            except ValueError:
                # Concurrent replacement intentionally produces refused
                # symlink generations; only accepted regular files matter.
                pass
    finally:
        running.clear()
        thread.join()
    assert reads > 0 and redirected == 0
    assert other.stat().st_mode & 0o777 == 0o644


def test_yaml_scalar_strings_match_baseline(tmp_path):
    for name in ("on", "off", "yes", "no", "2026-10-10"):
        loaded = Secrets.load(secret(tmp_path, f"xray:\n  clients:\n    - name: {name}\n"))
        assert loaded.find_client(name).name == name
    with pytest.raises(ValueError):
        Secrets.load(secret(tmp_path, "subscription: {port: true}\n"))


def test_yaml12_numeric_edges_and_duplicate_keys_never_leak_input(tmp_path):
    from vpnd.yaml_loader import load_yaml

    for scalar, expected in (
        ("0123", "0123"),
        ("1:23", "1:23"),
        ("0o123", 83),
        ("0x53", 83),
        ("0b1010", 10),
        ("1e2", 100.0),
        ("+83", 83),
        ("-0o123", -83),
    ):
        value = load_yaml("value: " + scalar)["value"]
        assert value == expected and type(value) is type(expected)
    sentinel = "synthetic_secret_DO_NOT_ECHO"
    for raw in (
        f"subscription: {{port: 443, port: {sentinel}}}",
        f"xray: {{clients: []}}\nxray: {sentinel}\n",
        f"xray: [{sentinel}",
        f"xray: !!python/object {sentinel}",
    ):
        with pytest.raises(ValueError) as error:
            Secrets.load(secret(tmp_path, raw))
        assert sentinel not in str(error.value)
        assert str(tmp_path) not in str(error.value)


def test_binary_yaml_numeric_client_names_and_ports(tmp_path):
    loaded = Secrets.load(secret(tmp_path, "subscription: {port: 0b1010}\n"))
    assert loaded.subscription_port() == 10
    with pytest.raises(ValueError):
        Secrets.load(secret(tmp_path, "xray: {clients: [{name: 0b1010}]}\n"))
