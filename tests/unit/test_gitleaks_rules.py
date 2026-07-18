"""Lock the custom gitleaks rules against code-identifier false positives."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _custom_rule(rule_id: str) -> dict:
    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text())
    return next(rule for rule in config["rules"] if rule["id"] == rule_id)


def test_snell_credential_rule_ignores_python_psk_identifiers() -> None:
    regex = re.compile(_custom_rule("snell-credential")["regex"])

    assert regex.search("_client_psk = _client_config_credentials(config)") is None
    assert regex.search("_rotated_psk = rotate_credentials(config)") is None


def test_snell_credential_rule_still_detects_credential_assignment() -> None:
    regex = re.compile(_custom_rule("snell-credential")["regex"])

    assert regex.search("psk: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") is not None
    assert regex.search("snell userkey = BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB") is not None
    assert regex.search("snell_psk = CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC") is not None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _gitleaks(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("gitleaks")
    assert executable is not None, "gitleaks is a required repository prerequisite"
    return subprocess.run(
        [
            executable,
            "git",
            *args,
            "--config",
            str(REPO_ROOT / ".gitleaks.toml"),
            "--redact",
            "--no-banner",
            ".",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _temporary_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / ".gitignore").write_text("secrets/local/\n")
    (repo / "code.py").write_text("_client_psk = load_credentials(config)\n")
    _git(repo, "add", ".gitignore", "code.py")
    _git(repo, "commit", "-qm", "initial")
    return repo


def test_gitleaks_history_ignores_code_identifier_false_positive(tmp_path: Path) -> None:
    repo = _temporary_repo(tmp_path)

    assert _gitleaks(repo).returncode == 0


def test_gitleaks_history_detects_committed_secret(tmp_path: Path) -> None:
    repo = _temporary_repo(tmp_path)
    secret = "A" * 32
    (repo / "credential.conf").write_text(f"psk: {secret}\n")
    _git(repo, "add", "credential.conf")
    _git(repo, "commit", "-qm", "add credential")

    result = _gitleaks(repo)

    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr


def test_gitleaks_ignores_untracked_local_operator_secret(tmp_path: Path) -> None:
    repo = _temporary_repo(tmp_path)
    secret_file = repo / "secrets" / "local" / "client.conf"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("snell_psk = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n")

    assert _gitleaks(repo).returncode == 0
    assert _gitleaks(repo, "--staged").returncode == 0


def test_gitleaks_staged_scan_detects_force_added_local_secret(tmp_path: Path) -> None:
    repo = _temporary_repo(tmp_path)
    secret_file = repo / "secrets" / "local" / "client.conf"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("snell_psk = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n")
    _git(repo, "add", "-f", "secrets/local/client.conf")

    assert _gitleaks(repo).returncode == 0
    staged = _gitleaks(repo, "--staged")
    assert staged.returncode == 1
    assert "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in staged.stdout + staged.stderr
