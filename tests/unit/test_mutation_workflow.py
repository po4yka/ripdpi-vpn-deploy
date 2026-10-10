"""Exercise mutation runner isolation and the hosted step's exit-code contract."""

import os
from pathlib import Path
import subprocess
import sys
import shlex

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def scaffold_mutation_dependencies(root):
    for name, content in {
        "vpnd/tests/test_sample.py": "pass\n", "vpnd/config/example.yaml": "fixture: true\n",
        "vpnd/templates/recipient.html": "fixture", "vpnd/requirements.txt": "locked\n",
        "docs/runbook.md": "original docs\n", "tests/fixtures/sample.yml": "fixture\n",
    }.items():
        path = root / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


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
    interpreter = binary / "python3"
    interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
    interpreter.chmod(0o755)
    mutmut = binary / "mutmut"
    mutmut.write_text(runner.read_text())
    mutmut.chmod(0o755)
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
        "scripts/prepare-vpnd-mutation-tree.py": (ROOT / "scripts/prepare-vpnd-mutation-tree.py").read_text(),
        "vpnd/pyproject.toml": '[tool.mutmut]\nsource_paths = ["src/vpnd/core.py"]\n',
        "vpnd/src/vpnd/core.py": "original source\n",
        "docs/runbook.md": "original docs\n",
        "tests/fixtures/sample.yml": "fixture\n",
        "scripts/helper.sh": "helper\n",
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    scaffold_mutation_dependencies(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    if missing_input:
        (repo / "scripts/helper.sh").unlink()
    (repo / "docs/runbook.md").write_text("working tree docs\n")
    (repo / "untracked-private-file").write_text("not a build input")
    binary = tmp_path / "bin"
    binary.mkdir()
    interpreter = binary / "python3"
    interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
    interpreter.chmod(0o755)
    mutmut = binary / "mutmut"
    obsolete = binary / "cargo"
    obsolete.write_text("#!/bin/sh\necho 'unexpected Rust dependency in mutation runner' >&2\nexit 98\n")
    obsolete.chmod(0o755)
    marker = tmp_path / "scratch-path"
    if missing_input:
        # GNU tar uses 2 for fatal copy errors, the same code the normalized mutation wrapper
        # uses for survivors. A setup error must never become a finding.
        tar = binary / "tar"
        tar.write_text("#!/bin/sh\nexit 2\n")
        tar.chmod(0o755)
    mutmut.write_text("""#!/usr/bin/env python3
import os
from pathlib import Path
import sys
root = Path.cwd()
import tomllib
configuration = tomllib.loads((root / 'pyproject.toml').read_text())['tool']['mutmut']
assert configuration['source_paths'] == ['src/vpnd/']
assert configuration['only_mutate'] == ['src/vpnd/core.py']
assert os.environ['PYTHONPATH'] == str(root / 'mutants/src')
assert root != Path(os.environ['ORIGINAL_ROOT'])
assert (root / 'docs/runbook.md').read_text() == 'working tree docs\\n'
assert (root / 'tests/fixtures/sample.yml').read_text() == 'fixture\\n'
assert (root / 'scripts/helper.sh').read_text() == 'helper\\n'
assert not (root / 'untracked-private-file').exists()
if sys.argv[1:] == ['export-cicd-stats']:
    sys.exit(0)
assert sys.argv[1:] == ['run', '--max-children', '2']
(root / 'vpnd/src/vpnd/core.py').write_text('mutated')
Path(os.environ['SCRATCH_MARKER']).write_text(str(root))
sys.exit(4)
""")
    mutmut.chmod(0o755)
    result = subprocess.run(
        ["bash", str(repo / "scripts/test-vpnd-mutants.sh")],
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
             "ORIGINAL_ROOT": str(repo), "SCRATCH_MARKER": str(marker)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == (1 if missing_input else 4), result.stderr
    assert (repo / "vpnd/src/vpnd/core.py").read_text() == "original source\n"
    if missing_input:
        assert not marker.exists()
    else:
        assert not Path(marker.read_text()).exists()


@pytest.mark.parametrize("mode,expected", [
    ("killed", 0), ("survived", 2), ("tool-failure", 4), ("backend-usage", 1),
    ("missing-output", 1), ("invalid-output", 1), ("empty-output", 1),
    ("no_tests", 1), ("skipped", 1), ("suspicious", 1), ("timeout", 1),
    ("check_was_interrupted_by_user", 1), ("segfault", 1), ("partial", 1),
    ("invalid-count", 1), ("export-failure", 23),
])
def test_runner_normalizes_only_complete_executed_mutation_results(tmp_path, mode, expected):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in {
        "scripts/test-vpnd-mutants.sh": (ROOT / "scripts/test-vpnd-mutants.sh").read_text(),
        "scripts/check-vpnd-mutation-results.py": (ROOT / "scripts/check-vpnd-mutation-results.py").read_text(),
        "scripts/prepare-vpnd-mutation-tree.py": (ROOT / "scripts/prepare-vpnd-mutation-tree.py").read_text(),
        "vpnd/pyproject.toml": '[tool.mutmut]\nsource_paths = ["src/vpnd/core.py"]\n',
        "vpnd/src/vpnd/core.py": "original source\n",
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    scaffold_mutation_dependencies(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    binary = tmp_path / "bin"
    binary.mkdir()
    interpreter = binary / "python3"
    interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
    interpreter.chmod(0o755)
    backend = binary / "mutmut"
    backend.write_text('''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
mode = os.environ['MUTATION_MODE']
output = Path('mutants')
output.mkdir(exist_ok=True)
(output / 'diagnostic.txt').write_text('retained diagnostic')
if sys.argv[1:] == ['run', '--max-children', '2']:
    (Path('vpnd/src/vpnd/core.py')).write_text('mutated')
    sys.exit(4 if mode == 'tool-failure' else 2 if mode == 'backend-usage' else 0)
assert sys.argv[1:] == ['export-cicd-stats']
if mode == 'export-failure':
    sys.exit(23)
if mode == 'missing-output':
    sys.exit(0)
path = output / 'mutmut-cicd-stats.json'
if mode == 'invalid-output':
    path.write_text('invalid JSON')
    sys.exit(0)
document = dict.fromkeys(['killed', 'survived', 'no_tests', 'skipped', 'suspicious', 'timeout', 'check_was_interrupted_by_user', 'segfault'], 0)
document['total'] = 1
document['killed' if mode not in document else mode] = 1
if mode == 'empty-output':
    document['total'] = document['killed'] = 0
if mode == 'partial':
    document['total'] = 2
if mode == 'invalid-count':
    document['killed'] = True
path.write_text(json.dumps(document))
''')
    backend.chmod(0o755)
    result = subprocess.run(
        ["bash", str(repo / "scripts/test-vpnd-mutants.sh")],
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}", "MUTATION_MODE": mode},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == expected, result.stderr
    assert (repo / "vpnd/src/vpnd/core.py").read_text() == "original source\n"
    reports = list((repo / "vpnd/mutants").glob("run.*"))
    assert len(reports) == 1
    assert (reports[0] / "diagnostic.txt").read_text() == "retained diagnostic"
