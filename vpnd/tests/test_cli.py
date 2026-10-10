from pathlib import Path
import pytest
from vpnd.config import Context
from vpnd.cli import parse_args


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


# Rust test: vpnd/src/cli.rs::clip_without_ai_is_a_parse_time_error
def test_clip_without_ai_is_a_parse_time_error(capsys):
    with pytest.raises(SystemExit) as error:
        parse_args(["doctor", "--clip"])
    assert error.value.code == 2
    assert "--ai" in capsys.readouterr().err


# Rust test: vpnd/src/cli.rs::clip_with_ai_parses_and_carries_both_flags
def test_clip_with_ai_parses_and_carries_both_flags():
    args = parse_args(["doctor", "--ai", "--clip"])
    assert args.command == "doctor" and args.ai and args.clip


# Rust test: vpnd/src/cli.rs::json_flag_is_rejected_for_unsupported_subcommands
def test_json_flag_is_rejected_for_unsupported_subcommands():
    for argv in (
        ["--json", "host", "list"],
        ["host", "list", "--json", "--json"],
        ["doctor", "--json"],
        ["deploy", "--json"],
        ["update", "--json"],
    ):
        with pytest.raises(SystemExit):
            parse_args(argv)
    for argv in (
        ["host", "list", "--json"],
        ["host", "show", "name", "--json"],
        ["probe-matrix", "--json"],
    ):
        assert parse_args(argv).json


def test_globals_keep_explicit_values_at_every_depth():
    for argv in (
        ["-e", "test", "-p", "vultr", "-y", "host", "list"],
        ["host", "-e", "test", "list", "-p", "vultr", "-y"],
    ):
        args = parse_args(argv)
        assert (args.env, args.provider, args.yes) == ("test", "vultr", True)


def test_host_add_keeps_scope_distinct():
    args = parse_args(
        ["--provider", "upcloud", "host", "add", "one", "--env", "staging", "--provider", "hetzner"]
    )
    assert (
        args.provider == "upcloud"
        and args.host_provider == "hetzner"
        and args.host_env == "staging"
    )


def test_baseline_global_flag_scope_and_duplicate_matrix():
    for argv, env, explain, yes in (
        (["--env", "one", "deploy", "--env", "two"], "two", False, False),
        (["--explain", "deploy", "--explain"], "prod", True, False),
        (["--yes", "--explain", "deploy", "--yes"], "prod", True, True),
        (["host", "-e", "one", "list", "-e", "two"], "two", False, False),
    ):
        args = parse_args(argv)
        assert (args.env, args.explain, args.yes) == (env, explain, yes)
    for argv in (
        ["--explain", "--explain", "deploy"],
        ["--env", "one", "--env", "two", "--explain", "deploy"],
    ):
        with pytest.raises(SystemExit) as error:
            parse_args(argv)
        assert error.value.code == 2
