import asyncio
import io
import os
from types import SimpleNamespace
import pytest
from artifact_helpers import SAMPLE, scaffold, context, private, cli
from vpnd.commands import share
from vpnd.pages import qr


def setup(root, contents=None):
    scaffold(root)
    ctx = context(root)
    private(ctx.secrets_file, contents or SAMPLE)
    private(root / "token", "test-token_123\n")
    (root / "Makefile").write_text("emit-singbox:\n\t@printf '%s\\n' '{\"outbounds\":[]}'\n")
    return ctx


def args(root, out=None):
    return SimpleNamespace(
        client="phone",
        qr=True,
        type="singbox",
        out=out,
        token_stdin=False,
        token_file=root / "token",
    )


# Rust test: vpnd/tests/share_command.rs::share_generates_a_bundle_for_a_canonical_xray_client
def test_share_generates_a_bundle_for_a_canonical_xray_client(tmp_path):
    ctx = setup(
        tmp_path, SAMPLE + "\nsubscription:\n  server_name: sub.example.com\n  port: 8444\n"
    )
    out = tmp_path / "bundle"
    out.mkdir()
    stale = ["config.singbox.tmp", "index.tmp", "qr.tmp", "qr-ripdpi.tmp"]
    for name in stale:
        (out / name).write_text("interrupted old write")
    asyncio.run(share.run(ctx, args(tmp_path, out)))
    assert (out / "config.singbox.json").read_text() == '{"outbounds":[]}\n'
    page = (out / "index.html").read_text()
    assert "phone" in page and "https://sub.example.com:8444/sub/test-token_123" in page
    assert out.stat().st_mode & 0o777 == 0o700
    for name in ["config.singbox.json", "index.html", "qr.svg", "qr-ripdpi.svg"]:
        assert (out / name).stat().st_mode & 0o777 == 0o600
    for name in stale:
        assert (out / name).read_text() == "interrupted old write"
    assert len(list(out.iterdir())) == 8


# Rust test: vpnd/tests/share_command.rs::invalid_tokens_from_stdin_and_file_fail_before_emission
def test_invalid_tokens_from_stdin_and_file_fail_before_emission(tmp_path):
    setup(tmp_path)
    (tmp_path / "Makefile").write_text("emit-singbox:\n\t@touch emitted\n")
    for source in ["stdin", "token file"]:
        for token in ["", " \n\t", "token/invalid", "token<script>", "токен"]:
            private(tmp_path / "token", token)
            option = (
                ["--token-stdin"] if source == "stdin" else ["--token-file", tmp_path / "token"]
            )
            out = cli(tmp_path, "share", "phone", *option, input=token)
            assert out.returncode != 0 and source in out.stderr
            assert not (tmp_path / "emitted").exists() and not (tmp_path / "share").exists()


# Rust test: vpnd/tests/share_command.rs::missing_or_blank_host_fails_before_creating_a_bundle
def test_missing_or_blank_host_fails_before_creating_a_bundle(tmp_path):
    for value in ["", "nginx_xhttp:\n  server_name: '  '\nsubscription:\n  server_name: ''\n"]:
        ctx = setup(tmp_path, "xray:\n  clients:\n    - name: phone\n" + value)
        with pytest.raises(ValueError, match="server_name"):
            asyncio.run(share.run(ctx, args(tmp_path)))
        assert not (tmp_path / "share").exists()


# Rust test: vpnd/tests/share_command.rs::failed_qr_publication_removes_its_temp_file
def test_failed_qr_publication_removes_its_temp_file(tmp_path):
    path = tmp_path / "qr.svg"
    path.mkdir()
    with pytest.raises(OSError):
        qr.write_svg("sensitive-payload", path)
    assert len(list(tmp_path.iterdir())) == 1 and path.is_dir()


# Rust test: vpnd/tests/share_command.rs::cli_bundle_artifacts_are_private_even_with_permissive_umask
def test_cli_bundle_artifacts_are_private_even_with_permissive_umask(tmp_path):
    setup(tmp_path)
    out = tmp_path / "bundle"
    old = os.umask(0o022)
    try:
        output = cli(
            tmp_path, "share", "phone", "--qr", "--token-file", tmp_path / "token", "--out", out
        )
    finally:
        os.umask(old)
    assert output.returncode == 0, output.stderr
    for name in ["config.singbox.json", "index.html", "qr.svg", "qr-ripdpi.svg"]:
        assert (out / name).stat().st_mode & 0o777 == 0o600
    assert len(list(out.iterdir())) == 4


# Rust test: vpnd/src/commands/share.rs::token_file_gate_rejects_symlink
def test_token_file_gate_rejects_symlink(tmp_path):
    private(tmp_path / "real-token", "tok")
    (tmp_path / "link-token").symlink_to(tmp_path / "real-token")
    with pytest.raises((ValueError, OSError)):
        share.load_token_file(tmp_path / "link-token")


# Rust test: vpnd/src/commands/share.rs::token_file_gate_rejects_loose_mode
def test_token_file_gate_rejects_loose_mode(tmp_path):
    path = private(tmp_path / "token", "tok")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        share.load_token_file(path)


# Rust test: vpnd/src/commands/share.rs::token_file_gate_accepts_0600_raw
def test_token_file_gate_accepts_0600_raw(tmp_path):
    assert share.load_token_file(private(tmp_path / "token", "  tok-value \n")) == "  tok-value \n"


def test_token_trim_preserves_rejected_control_separators(tmp_path, monkeypatch):
    from vpnd.text import WHITE_SPACE

    for source in ["stdin", "file"]:
        values = args(tmp_path)
        values.token_stdin = source == "stdin"
        for character in ["\x1c", "\x1d", "\x1e", "\x1f"]:
            for text in [character + "valid-token", "valid-token" + character]:
                if source == "stdin":
                    monkeypatch.setattr("sys.stdin", io.StringIO(text))
                else:
                    private(tmp_path / "token", text)
                with pytest.raises(ValueError, match="invalid token"):
                    share.read_token(values)
        if source == "stdin":
            monkeypatch.setattr("sys.stdin", io.StringIO(WHITE_SPACE + "valid-token" + WHITE_SPACE))
        else:
            private(tmp_path / "token", WHITE_SPACE + "valid-token" + WHITE_SPACE)
        assert share.read_token(values) == "valid-token"
