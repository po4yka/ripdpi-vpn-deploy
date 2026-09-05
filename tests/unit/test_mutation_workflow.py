"""Exercise mutation runner isolation and the hosted step's exit-code contract."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("code,log_failure", [
    (0, False), (2, False), (1, False), (3, False), (4, False), (70, False),
    (0, True), (2, True),
])
def test_workflow_only_accepts_clean_or_surviving_mutants(tmp_path, code, log_failure):
    workflow = yaml.safe_load((ROOT / ".github/workflows/mutants.yml").read_text())
    step = next(step for step in workflow["jobs"]["mutants"]["steps"]
                if step.get("id") == "mutants")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runner = scripts / "test-vpnd-mutants.sh"
    runner.write_text(f"#!/bin/sh\necho mutation-output\nexit {code}\n")
    runner.chmod(0o755)
    binary = tmp_path / "bin"
    binary.mkdir()
    cargo = binary / "cargo"
    cargo.write_text(runner.read_text())
    cargo.chmod(0o755)
    crate = tmp_path / "vpnd"
    crate.mkdir()
    output = tmp_path / "github-output"
    if log_failure:
        (tmp_path / "mutants-output.txt").mkdir()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=crate, capture_output=True, text=True,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
             "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output)},
        timeout=10,
    )
    expected = 1 if log_failure else (0 if code in (0, 2) else code)
    assert result.returncode == expected, result.stderr
    assert output.read_text() == f"exit_code={code}\n"
    if not log_failure:
        assert (tmp_path / "mutants-output.txt").read_text() == "mutation-output\n"
    assert not step.get("continue-on-error", False)


@pytest.mark.parametrize("missing_input", [False, True])
def test_runner_preserves_repository_inputs_and_original_source(tmp_path, missing_input):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in {
        "scripts/test-vpnd-mutants.sh": (ROOT / "scripts/test-vpnd-mutants.sh").read_text(),
        "vpnd/src/lib.rs": "original source\n",
        "docs/runbook.md": "original docs\n",
        "tests/fixtures/sample.yml": "fixture\n",
        "scripts/helper.sh": "helper\n",
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    if missing_input:
        (repo / "scripts/helper.sh").unlink()
    (repo / "docs/runbook.md").write_text("working tree docs\n")
    (repo / "untracked-private-file").write_text("not a build input")
    binary = tmp_path / "bin"
    binary.mkdir()
    cargo = binary / "cargo"
    marker = tmp_path / "scratch-path"
    if missing_input:
        # GNU tar uses 2 for fatal copy errors, the same code cargo-mutants
        # uses for survivors. A setup error must never become a finding.
        tar = binary / "tar"
        tar.write_text("#!/bin/sh\nexit 2\n")
        tar.chmod(0o755)
    cargo.write_text("""#!/usr/bin/env python3
import os
from pathlib import Path
import sys
root = Path.cwd().parent
assert root != Path(os.environ['ORIGINAL_ROOT'])
assert (root / 'docs/runbook.md').read_text() == 'working tree docs\\n'
assert (root / 'tests/fixtures/sample.yml').read_text() == 'fixture\\n'
assert (root / 'scripts/helper.sh').read_text() == 'helper\\n'
assert not (root / 'untracked-private-file').exists()
assert '--in-place' in sys.argv
(root / 'vpnd/src/lib.rs').write_text('mutated')
Path(os.environ['SCRATCH_MARKER']).write_text(str(root))
sys.exit(4)
""")
    cargo.chmod(0o755)
    result = subprocess.run(
        ["bash", str(repo / "scripts/test-vpnd-mutants.sh")],
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
             "ORIGINAL_ROOT": str(repo), "SCRATCH_MARKER": str(marker)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == (1 if missing_input else 4), result.stderr
    assert (repo / "vpnd/src/lib.rs").read_text() == "original source\n"
    if missing_input:
        assert not marker.exists()
    else:
        assert not Path(marker.read_text()).exists()
