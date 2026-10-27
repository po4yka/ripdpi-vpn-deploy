"""The cached-image Xray validator must call the image entrypoint correctly."""

import importlib.util
from pathlib import Path

import pytest

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


def test_kuma_ingress_reaches_nginx_validator(monkeypatch, capsys):
    renderer = _load()
    validated = []

    def validate(_text, label):
        validated.append(label)
        return "kuma parser refusal" if label.endswith("observability-kuma.conf.j2") else None

    monkeypatch.setattr(renderer, "validate_xray", lambda *args: None)
    monkeypatch.setattr(renderer, "validate_nginx", validate)

    assert renderer.main() == 1
    assert "ansible/roles/observability_kuma/templates/observability-kuma.conf.j2" in validated
    assert "kuma parser refusal" in capsys.readouterr().out


@pytest.mark.parametrize("address,expected", [
    ("100.64.0.8:9444", "100.64.0.8:9444"),
    ("100.64.0.8:80", "100.64.0.8:18080"),
    ("[::1]:80", "[::1]:18080"),
    ("80", "18080"),
])
def test_nginx_validator_lifts_only_the_port(tmp_path, monkeypatch, address, expected):
    renderer = _load()
    captured = tmp_path / "captured.conf"
    nginx = tmp_path / "nginx"
    nginx.write_text('#!/bin/sh\ncp "$5" "$CAPTURE"\n')
    nginx.chmod(0o755)
    monkeypatch.setenv("CAPTURE", str(captured))
    monkeypatch.setattr(renderer.shutil, "which", lambda _name: str(nginx))
    monkeypatch.setattr(renderer.tempfile, "mkdtemp", lambda **_kwargs: str(tmp_path / "prefix"))

    assert renderer.validate_nginx(f"server {{ listen {address}; }}", "fixture") is None
    assert f"listen {expected};" in captured.read_text()
