"""Portable operator and synthetic-render contracts for AWG NAT provisioning."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RENDER_CHECK = ROOT / "scripts/check-templates-render.py"
BUNDLE_HELPER = ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh"
RUNBOOK = ROOT / "docs/REAL-VPS-AWG-NAT.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
    )


def _clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Portability Test")
    _git(repo, "config", "user.email", "portability@example.invalid")
    (repo / "tracked.txt").write_text("tracked\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "test: seed source")
    return repo


def test_synthetic_render_covers_task_local_awg_nat_template_vars() -> None:
    completed = subprocess.run(
        ["python3", str(RENDER_CHECK)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_bundle_helper_uses_python_tempfiles_beside_atomic_output(
    tmp_path: Path,
) -> None:
    source = BUNDLE_HELPER.read_text()
    repo = _clean_repo(tmp_path)
    output_parent = tmp_path / "owner controlled output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "source.bundle"

    completed = subprocess.run(
        [str(BUNDLE_HELPER), "--repo", str(repo), "--output", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert "tempfile.mkstemp" in source
    assert "$(mktemp" not in source
    assert "os.replace" in source
    assert json.loads(completed.stdout)["sourceBundleSha256"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(output_parent.iterdir()) == [output]


def test_bundle_helper_cleans_sibling_tempfiles_on_failure(tmp_path: Path) -> None:
    repo = _clean_repo(tmp_path)
    output_parent = tmp_path / "private output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "source.bundle"
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_stub = bin_dir / "git"
    git_stub.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ $1 == bundle && $2 == verify ]]; then exit 17; fi\n"
        f'exec {real_git!r} "$@"\n'
    )
    git_stub.chmod(0o700)

    completed = subprocess.run(
        [str(BUNDLE_HELPER), "--repo", str(repo), "--output", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert completed.returncode == 17
    assert list(output_parent.iterdir()) == []


def test_bundle_helper_rejects_head_change_during_generation(tmp_path: Path) -> None:
    repo = _clean_repo(tmp_path)
    output_parent = tmp_path / "private output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "source.bundle"
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_stub = bin_dir / "git"
    git_stub.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ $1 == -C && $3 == bundle && $4 == create ]]; then\n"
        f"  {real_git!r} -C \"$2\" commit --allow-empty -qm 'test: race HEAD'\n"
        "fi\n"
        f'exec {real_git!r} "$@"\n'
    )
    git_stub.chmod(0o700)

    completed = subprocess.run(
        [str(BUNDLE_HELPER), "--repo", str(repo), "--output", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert completed.returncode != 0
    assert "source HEAD changed" in completed.stderr
    assert list(output_parent.iterdir()) == []


def test_runbook_loads_repository_ansible_config() -> None:
    runbook = RUNBOOK.read_text()

    assert "cd ansible" in runbook or "ANSIBLE_CONFIG=" in runbook
