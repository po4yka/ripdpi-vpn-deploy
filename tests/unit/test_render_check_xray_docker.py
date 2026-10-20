"""The cached-image Xray validator must call the image entrypoint correctly."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_check_docker", RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docker_fallback_uses_entrypoint_and_mounts_log_directory(tmp_path, monkeypatch):
    renderer = _load()
    calls = tmp_path / "calls"
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
    docker.chmod(0o755)
    monkeypatch.setenv("CALLS", str(calls))
    monkeypatch.setattr(
        renderer.shutil, "which", lambda name: str(docker) if name == "docker" else None
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    assert renderer.validate_xray("{}", "config.json.j2", str(log_dir)) is None

    inspect, run = calls.read_text().splitlines()
    assert inspect == f"image inspect {renderer.XRAY_IMAGE}"
    arguments = run.split()
    image = arguments.index(renderer.XRAY_IMAGE)
    # The image entrypoint is xray; a repeated name becomes an unknown command.
    assert arguments[image + 1:] == ["run", "-test", "-config", "/cfg.json"]
    assert f"{log_dir}:{log_dir}" in arguments[:image]
