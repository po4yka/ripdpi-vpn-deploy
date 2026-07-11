"""Xray template validation must fail closed when its runtime is unavailable."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check-templates-render.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

spec = importlib.util.spec_from_file_location("check_templates_render", CHECK_SCRIPT)
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


def test_xray_validation_fails_when_no_runtime_is_available(monkeypatch) -> None:
    monkeypatch.setattr(checker.shutil, "which", lambda _name: None)

    error = checker.validate_xray("{}", "xray-config.json.j2")

    assert error == (
        "xray-config.json.j2: xray semantic validation unavailable — "
        f"install xray or cache {checker.XRAY_IMAGE}"
    )


def test_xray_validation_fails_when_fallback_image_is_not_cached(monkeypatch) -> None:
    monkeypatch.setattr(
        checker.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )

    class InspectResult:
        returncode = 1

    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return InspectResult()

    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    error = checker.validate_xray("{}", "xray-config.json.j2")

    image = checker.XRAY_IMAGE
    assert commands == [["/usr/bin/docker", "image", "inspect", image]]
    assert error == (
        "xray-config.json.j2: xray semantic validation unavailable — "
        f"install xray or cache {image}"
    )


def test_ci_installs_the_production_pinned_xray_binary() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "Install pinned Xray semantic validator" in workflow
    assert "releases/download/${XRAY_VERSION}/Xray-linux-64.zip" in workflow
    assert 'echo "${XRAY_DIR}" >> "${GITHUB_PATH}"' in workflow
