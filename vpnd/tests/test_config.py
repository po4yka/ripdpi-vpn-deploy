from pathlib import Path
from dataclasses import replace
import os
import sys
import pytest
from vpnd.config import Context
from vpnd.config import resolve_runtime_dir
from vpnd.cli import parse_args
import tempfile


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


def scaffold(root, provider="upcloud"):
    (root / "Makefile").write_text("# fake\n")
    (root / "ansible").mkdir()
    (root / "terraform/providers" / provider).mkdir(parents=True)
    return root


def cli(root, provider="upcloud"):
    return parse_args(["--root", str(root), "--provider", provider, "completions", "bash"])


# Rust test: vpnd/src/config.rs::runtime_dir_resolution_matrix_xdg_set_and_unset
def test_runtime_dir_resolution_matrix_xdg_set_and_unset(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/runtime-xdg")
    assert resolve_runtime_dir() == Path("/runtime-xdg")
    for value in (None, ""):
        if value is None:
            monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        else:
            monkeypatch.setenv("XDG_RUNTIME_DIR", value)
        assert resolve_runtime_dir() == Path(tempfile.gettempdir()) / f"vpn-provision-{os.getuid()}"


# Rust test: vpnd/src/config.rs::secure_secrets_file_propagates_chmod_failure
def test_secure_secrets_file_propagates_chmod_failure(tmp_path):
    if sys.platform == "linux":
        ctx = replace(fake_ctx(tmp_path), secrets_file=Path("/proc/self/cmdline"))
        with pytest.raises(ValueError, match="failed to set 0600"):
            ctx.secure_secrets_file()
    else:
        import subprocess

        path = tmp_path / "immutable"
        path.write_bytes(b"synthetic")
        subprocess.run(["/usr/bin/chflags", "uchg", str(path)], check=True)
        try:
            ctx = replace(fake_ctx(tmp_path), secrets_file=path)
            with pytest.raises(ValueError, match="failed to set 0600"):
                ctx.secure_secrets_file()
        finally:
            subprocess.run(["/usr/bin/chflags", "nouchg", str(path)], check=True)


# Rust test: vpnd/tests/config_discover.rs::root_override_wins_over_ancestor_walk
def test_root_override_wins_over_ancestor_walk(tmp_path):
    root = scaffold(tmp_path)
    assert Context.discover(cli(root)).root == root.resolve()


# Rust test: vpnd/tests/config_discover.rs::missing_ansible_dir_returns_error
def test_missing_ansible_dir_returns_error(tmp_path):
    (tmp_path / "Makefile").write_text("# fake")
    (tmp_path / "terraform/providers/upcloud").mkdir(parents=True)
    with pytest.raises(ValueError, match="ansible"):
        Context.discover(cli(tmp_path))


# Rust test: vpnd/tests/config_discover.rs::unknown_provider_returns_error
def test_unknown_provider_returns_error(tmp_path):
    root = scaffold(tmp_path)
    with pytest.raises(ValueError, match="bogus|provider|unknown"):
        Context.discover(cli(root, "bogus"))


# Rust test: vpnd/tests/config_discover.rs::missing_root_dir_returns_error
def test_missing_root_dir_returns_error():
    with pytest.raises(ValueError) as error:
        Context.discover(cli(Path("/nonexistent/path/that/does/not/exist")))
    assert str(error.value)


# Rust test: vpnd/tests/config_discover.rs::context_env_and_provider_propagated
def test_context_env_and_provider_propagated(tmp_path):
    root = scaffold(tmp_path, "hetzner")
    args = parse_args(
        ["--root", str(root), "--env", "staging", "--provider", "hetzner", "completions", "bash"]
    )
    ctx = Context.discover(args)
    assert ctx.env == "staging" and ctx.provider == "hetzner"
