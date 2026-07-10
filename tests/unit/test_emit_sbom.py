from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "emit-sbom.py"


@pytest.fixture
def emit_sbom_module(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("emit_sbom_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SBOM_DIR", tmp_path / "sbom")
    module.SBOM_DIR.mkdir()
    return module


def test_custom_input_uses_explicit_label_without_logging_input_path(
    emit_sbom_module, tmp_path, monkeypatch, capsys
):
    input_config = tmp_path / "prod.customer.secret.yaml"
    input_config.write_text("xray:\n  version: v1.2.3\n")
    monkeypatch.setenv("VPN_SECRETS_FILE", str(input_config))
    monkeypatch.setenv("SBOM_LABEL", "prod")

    assert emit_sbom_module.main() == 0

    captured = capsys.readouterr()
    assert str(input_config) not in captured.out
    assert str(input_config) not in captured.err
    assert "prod.customer.secret" not in captured.out
    assert (emit_sbom_module.SBOM_DIR / "prod.json").exists()
    assert not (emit_sbom_module.SBOM_DIR / "prod.customer.secret.json").exists()


def test_sbom_emits_only_allowlisted_public_pin_metadata(
    emit_sbom_module, tmp_path, monkeypatch
):
    input_config = tmp_path / "private.yaml"
    input_config.write_text(
        """
xray:
  version: v25.1.1
  linux_amd64_sha256: 0f00
  private_key: SHOULD_NOT_APPEAR
hysteria:
  version: v2.6.0
  auth_password: SHOULD_NOT_APPEAR
geodata:
  geosite_url: https://example.invalid/geosite.dat
  geosite_sha256: 0bad
  access_token: SHOULD_NOT_APPEAR
amneziawg_go_version: v0.2.13
operator_password: SHOULD_NOT_APPEAR
""".lstrip()
    )
    monkeypatch.setenv("VPN_SECRETS_FILE", str(input_config))
    monkeypatch.setenv("SBOM_LABEL", "private")

    assert emit_sbom_module.main() == 0

    payload = (emit_sbom_module.SBOM_DIR / "private.json").read_text()
    assert "SHOULD_NOT_APPEAR" not in payload
    sbom = json.loads(payload)
    names = {component["name"] for component in sbom["components"]}
    assert {"xray-core", "hysteria", "geosite", "amneziawg-go", "RealiTLScanner"} <= names


def test_example_sbom_includes_pinned_snell_candidate(emit_sbom_module, monkeypatch):
    monkeypatch.delenv("VPN_SECRETS_FILE", raising=False)
    assert emit_sbom_module.main() == 0
    sbom = json.loads((emit_sbom_module.SBOM_DIR / "example.json").read_text())
    snell = next(component for component in sbom["components"] if component["name"] == "sing-box-snell")
    assert snell["version"] == "v1.14.0-alpha.42"


def test_invalid_custom_label_is_rejected(emit_sbom_module, tmp_path, monkeypatch, capsys):
    input_config = tmp_path / "private.yaml"
    input_config.write_text("xray:\n  version: v1.2.3\n")
    monkeypatch.setenv("VPN_SECRETS_FILE", str(input_config))
    monkeypatch.setenv("SBOM_LABEL", "../private")

    assert emit_sbom_module.main() == 2

    captured = capsys.readouterr()
    assert "SBOM_LABEL must contain only" in captured.err
    assert not list(emit_sbom_module.SBOM_DIR.iterdir())
