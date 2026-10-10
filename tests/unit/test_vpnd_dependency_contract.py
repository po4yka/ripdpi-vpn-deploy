"""Python dependency selection preserves locked execution and vulnerability gates."""

import re
import tomllib
from pathlib import Path

import yaml


def test_ci_runs_locked_vpnd_dependency_policy():
    root = Path(__file__).resolve().parents[2]
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    release = (root / ".github/workflows/release-vpnd.yml").read_text()
    makefile = (root / "Makefile").read_text()
    assert "vpnd-dependency" in ci["required"]["needs"]
    assert ci["vpnd-dependency"]["uses"] == "./.github/workflows/_python-vpnd.yml"
    assert ci["vpnd-dependency"]["with"]["command"] == "dependency"
    reusable = (root / ".github/workflows/_python-vpnd.yml").read_text()
    assert "./.github/actions/setup-ci-python" in reusable
    assert "case" in reusable and "vpnd-dependency-check" in reusable
    assert "run: ${{ inputs.command }}" not in reusable
    assert "run: python3 ${{ inputs.command }}" not in reusable
    body = makefile.split("vpnd-dependency-check:", 1)[1].split("\n\n", 1)[0]
    assert "python3 -m pip_audit" in body and "vpnd/requirements.txt" in body
    assert (
        "--require-hashes" in body and "--no-deps" in body and "--disable-pip" in body
    )
    assert "--ignore-vuln" not in body
    for name in ("vpnd-test", "vpnd-lint", "vpnd-package"):
        assert name in ci["required"]["needs"]
    assert "scripts/build-vpnd-package.py" in release
    assert "scripts/validate-vpnd-release-tag.sh" in release
    assert "cargo-command" not in release
    assert not (root / ".github/workflows/_rust.yml").exists()
    assert "cargo test" not in makefile and "cargo clippy" not in makefile


def test_runtime_lock_matches_approved_inputs_and_hash_policy():
    root = Path(__file__).resolve().parents[2]
    package = root / "vpnd"
    project = tomllib.loads((package / "pyproject.toml").read_text())["project"]
    direct = dict(
        re.findall(
            r"^([A-Za-z0-9_.-]+)==([^\s]+)$",
            (package / "requirements.in").read_text(),
            re.MULTILINE,
        )
    )
    normalize = lambda name: name.lower().replace("_", "-")
    direct = {normalize(name): version for name, version in direct.items()}
    declared = {
        normalize(name): version
        for name, version in (item.split("==") for item in project["dependencies"])
    }
    lock = (package / "requirements.txt").read_text()
    locked = {
        normalize(name): version
        for name, version in re.findall(
            r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", lock, re.MULTILINE
        )
    }
    assert direct == declared
    assert all(locked[name] == version for name, version in direct.items())
    assert direct["qrcode"] == "8.2" and direct["tomli-w"] == "1.2.0"
    assert "anyhow" not in locked
    blocks = re.split(r"(?m)^(?=[A-Za-z0-9_.-]+==)", lock)[1:]
    assert len(blocks) == len(locked)
    assert all(re.search(r"--hash=sha256:[a-f0-9]{64}", block) for block in blocks)
    assert not any(
        token in lock
        for token in ("git+", "http://", "--extra-index-url", "--trusted-host")
    )


def test_reusable_workflow_dispatches_only_fixed_checks(tmp_path):
    import json
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/_python-vpnd.yml").read_text())
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("name") == "Run the fixed selected check"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    command = binary / "make"
    command.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        "with open(os.environ['MAKE_CAPTURE'], 'w') as handle: json.dump(sys.argv[1:], handle)\n"
    )
    command.chmod(0o755)
    selected = {
        "test": ["vpnd-test", "vpnd-parity-check"],
        "lint": ["vpnd-lint"],
        "package": ["vpnd-package-check"],
        "dependency": ["vpnd-dependency-check"],
    }
    for index, value in enumerate(
        [*selected, "", "test; touch must-not-exist", "$(touch must-not-exist)"]
    ):
        capture = tmp_path / str(index)
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=tmp_path,
            env={
                **os.environ,
                "PATH": f"{binary}:{os.environ['PATH']}",
                "VPND_CHECK": value,
                "MAKE_CAPTURE": str(capture),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if value in selected:
            assert result.returncode == 0, result.stderr
            assert json.loads(capture.read_text()) == selected[value]
        else:
            assert result.returncode != 0 and not capture.exists()
        assert not (tmp_path / "must-not-exist").exists()
