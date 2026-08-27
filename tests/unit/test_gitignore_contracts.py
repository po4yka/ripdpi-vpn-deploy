"""Repository ignore rules must work without an operator's global config."""

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def _ignored_by_repository(tmp_path: Path, candidate: str) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text((REPO_ROOT / ".gitignore").read_text())
    result = subprocess.run(
        ["git", "-c", "core.excludesFile=/dev/null", "check-ignore", "-v", candidate],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(".gitignore:")


def test_tasking_dependencies_are_ignored_without_global_config(tmp_path: Path) -> None:
    _ignored_by_repository(tmp_path, "tools/tasking/node_modules/package/index.js")


def test_credential_qr_artifacts_are_ignored_without_global_config(tmp_path: Path) -> None:
    _ignored_by_repository(tmp_path, "phone.sub.qr.png")
    _ignored_by_repository(tmp_path, "phone.sub.qr.png.Ab12Cd")
