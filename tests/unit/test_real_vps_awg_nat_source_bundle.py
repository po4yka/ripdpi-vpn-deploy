"""Executable contract for the offline exact-source bundle helper."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE)


def _clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Bundle Test")
    _git(repo, "config", "user.email", "bundle@example.invalid")
    (repo / "tracked.txt").write_text("tracked\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "test: seed source")
    return repo


def test_bundle_helper_rejects_untracked_input(tmp_path: Path) -> None:
    repo = _clean_repo(tmp_path)
    (repo / "untracked.txt").write_text("must not be omitted\n")

    completed = subprocess.run(
        [str(HELPER), "--repo", str(repo), "--output", str(tmp_path / "out.bundle")],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    assert "including untracked files" in completed.stderr
    assert not (tmp_path / "out.bundle").exists()


def test_bundle_helper_reports_commit_bundle_and_archive_digests(
    tmp_path: Path,
) -> None:
    repo = _clean_repo(tmp_path)
    output = tmp_path / "out.bundle"

    completed = subprocess.run(
        [str(HELPER), "--repo", str(repo), "--output", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    receipt = json.loads(completed.stdout)

    assert output.is_file()
    assert set(receipt) == {
        "sourceArchiveSha256",
        "sourceBundleSha256",
        "sourceSha",
    }
    assert len(receipt["sourceSha"]) == 40
    assert len(receipt["sourceBundleSha256"]) == 64
    assert len(receipt["sourceArchiveSha256"]) == 64
