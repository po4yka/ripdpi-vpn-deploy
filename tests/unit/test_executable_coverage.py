"""Execute skip-policy regressions and guard mandatory native/Go lane wiring."""
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("body,expected", [
    ("pass", 0),
    ("pytest.skip('missing native tool')", 1),
    ("assert False", 1),
])
def test_required_lane_rejects_skips_and_failures(tmp_path, body, expected):
    (tmp_path / "conftest.py").write_text((ROOT / "tests/conftest.py").read_text())
    (tmp_path / "test_sample.py").write_text(
        f"import pytest\ndef test_sample():\n    {body}\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "--fail-on-skip", "-q"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == expected, result.stdout + result.stderr


def test_native_and_go_lanes_are_unconditional_and_required():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for name, target in [("native-runtime", "test-native-runtime"),
                         ("go-helper", "test-probe-matrix-mtproto")]:
        job = jobs[name]
        assert name in jobs["required"]["needs"]
        assert "if" not in job and "continue-on-error" not in job
        assert any(f"make {target}" in step.get("run", "") for step in job["steps"])
    native = jobs["native-runtime"]["steps"]
    terraform = next(s for s in native if "setup-terraform@" in s.get("uses", ""))
    assert terraform["with"]["terraform_wrapper"] is False
    assert 'sudo env "PATH=$PATH"' in native[-1]["run"]
    assert "ALERTMANAGER_BIN=" in native[-1]["run"]


def test_local_and_ci_partition_native_tests_without_silent_skips():
    makefile = (ROOT / "Makefile").read_text()
    assert 'pytest tests/unit/ -m "not native_runtime" --fail-on-skip' in makefile
    assert "pytest tests/unit/ -m native_runtime --fail-on-skip" in makefile
    assert "$(MAKE) test-probe-matrix-mtproto" in makefile.split("ci-fast:", 1)[1]
    assert "go test -mod=readonly -count=1" in makefile
    names = []
    import ast
    for path in (ROOT / "tests/unit").glob("test_*.py"):
        module = ast.parse(path.read_text())
        names.extend(node.name for node in module.body if isinstance(node, ast.FunctionDef)
                     and any(ast.unparse(d) == "pytest.mark.native_runtime" for d in node.decorator_list))
    assert set(names) == {
        "test_adapter_command_uses_reviewed_terraform_fd_and_snapshot",
        "test_actual_builtin_terraform_data_plan_can_be_saved_if_terraform_exists",
        "test_alertmanager_v0281_enforces_the_webhook_request_timeout",
        "test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output",
    }


def test_make_test_unit_does_not_contaminate_nested_make_json(tmp_path):
    unit = tmp_path / "tests/unit"
    unit.mkdir(parents=True)
    (tmp_path / "tests/conftest.py").write_text((ROOT / "tests/conftest.py").read_text())
    (tmp_path / "json.mk").write_text("json:\n\t@printf '%s\\n' '{\"ok\":true}'\n")
    (unit / "test_json.py").write_text(
        "import json, subprocess\n"
        "def test_json():\n"
        "    result = subprocess.run(['make', '-f', 'json.mk'], capture_output=True, text=True, check=True)\n"
        "    assert json.loads(result.stdout) == {'ok': True}\n"
    )
    import os
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    # Simulate a recursive CI gate, including GNU Make's directory chatter.
    env.update(MAKELEVEL="2", MAKEFLAGS="w")
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "test-unit"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
