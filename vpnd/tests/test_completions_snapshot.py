from pathlib import Path
import pytest
from vpnd.commands.completions import generate_completion

SNAPSHOTS = Path(__file__).parent / "snapshots"
SUBCOMMANDS = [
    "deploy",
    "share",
    "doctor",
    "host",
    "update",
    "completions",
    "reconverge",
    "probe",
    "probe-matrix",
    "preflight",
    "fleet",
    "ai-docs",
]


# Rust test: vpnd/tests/completions_snapshot.rs::bash_completion_snapshot
def test_bash_completion_snapshot():
    assert generate_completion("bash") == (SNAPSHOTS / "python_bash_completions.snap").read_text()


# Rust test: vpnd/tests/completions_snapshot.rs::zsh_completion_snapshot
def test_zsh_completion_snapshot():
    assert generate_completion("zsh") == (SNAPSHOTS / "python_zsh_completions.snap").read_text()


# Rust test: vpnd/tests/completions_snapshot.rs::fish_completion_snapshot
def test_fish_completion_snapshot():
    assert generate_completion("fish") == (SNAPSHOTS / "python_fish_completions.snap").read_text()


# Rust test: vpnd/tests/completions_snapshot.rs::bash_completion_contains_vpnd_subcommands
def test_bash_completion_contains_vpnd_subcommands():
    for command in SUBCOMMANDS:
        assert command in generate_completion("bash")


# Rust test: vpnd/tests/completions_snapshot.rs::zsh_completion_contains_vpnd_subcommands
def test_zsh_completion_contains_vpnd_subcommands():
    for command in SUBCOMMANDS:
        assert command in generate_completion("zsh")


# Rust test: vpnd/tests/completions_snapshot.rs::fish_completion_contains_vpnd_subcommands
def test_fish_completion_contains_vpnd_subcommands():
    for command in SUBCOMMANDS:
        assert command in generate_completion("fish")


# Rust test: vpnd/tests/completions_snapshot.rs::share_completions_offer_only_token_input_flags
def test_share_completions_offer_only_token_input_flags():
    for shell in ["bash", "zsh", "fish"]:
        output = generate_completion(shell)
        if shell == "fish":
            assert (
                "-l token-stdin" in output
                and "-l token-file" in output
                and " -l token -d " not in output
            )
        else:
            assert "--token-stdin" in output and "--token-file" in output
            assert "--token " not in output and "--token=[" not in output


# Rust test: vpnd/tests/completions_snapshot.rs::bash_completion_mentions_global_flags
def test_bash_completion_mentions_global_flags():
    assert "--explain" in generate_completion("bash")


def test_powershell_alias_and_unknown_shell():
    assert generate_completion("pwsh") == generate_completion("PowerShell")
    with pytest.raises(ValueError, match="unknown shell"):
        generate_completion("unsupported")


def test_described_completions_preserve_security_flag_meanings():
    for shell in ["zsh", "fish"]:
        output = generate_completion(shell)
        for meaning in [
            "opaque subscription token from stdin",
            "subscription token from a 0600 file",
            "requires --ai",
            "mirrors SKIP_PRECHECK=1",
            "default: singbox",
            "default: <root>/vpnd/config/probe-matrix.yaml",
        ]:
            assert meaning in output.replace("\\:", ":")
    from vpnd.commands.completions import render_page_set

    doctor = dict(render_page_set())["vpnd-doctor"].replace("\\-", "-")
    assert "requires --ai" in doctor
