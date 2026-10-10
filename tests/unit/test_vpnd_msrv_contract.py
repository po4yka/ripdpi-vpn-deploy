"""The declared minimum Python runtime is pinned and exercises actual CLI syntax."""

import ast
import tomllib
from pathlib import Path

import yaml


def test_ci_checks_declared_vpnd_python_floor():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "vpnd/pyproject.toml").read_text())["project"]
    tools = tomllib.loads((root / "mise.toml").read_text())["tools"]
    setup = yaml.safe_load(
        (root / ".github/actions/setup-ci-python/action.yml").read_text()
    )
    step = next(
        step
        for step in setup["runs"]["steps"]
        if "setup-python@" in step.get("uses", "")
    )
    assert project["requires-python"] == ">=3.12,<3.13"
    assert tools["python"] == "3.12"
    assert step["with"]["python-version"] == "3.12"
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    reusable = yaml.safe_load((root / ".github/workflows/_python-vpnd.yml").read_text())
    setup_steps = [
        step for job in reusable["jobs"].values() for step in job.get("steps", [])
    ]
    assert any(
        step.get("uses") == "./.github/actions/setup-ci-python" for step in setup_steps
    )
    for name in ("vpnd-test", "vpnd-lint", "vpnd-package", "vpnd-dependency"):
        assert ci[name]["uses"] == "./.github/workflows/_python-vpnd.yml"
    sources = sorted((root / "vpnd/src/vpnd").rglob("*.py"))
    assert sources
    for path in sources:
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 12))
