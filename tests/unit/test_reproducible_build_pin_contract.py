"""Reproducible-build pins must be validated before reaching shell source."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reproducible-build.yml"


def test_pin_outputs_are_passed_to_shell_as_environment_data():
    source = WORKFLOW.read_text()

    assert source.count("PIN_VERSION: ${{ steps.pin.outputs.version }}") == 3
    assert source.count("PIN_SHA: ${{ steps.pin.outputs.sha }}") == 3
    assert 'branch "${{ steps.pin.outputs.version }}"' not in source
    assert 'schema_sha="${{ steps.pin.outputs.sha }}"' not in source
    assert "download/${{ steps.pin.outputs.version }}" not in source
    assert '== "${{ steps.pin.outputs.sha }}"' not in source


def test_pin_readers_reject_untrusted_version_and_sha_grammar():
    source = WORKFLOW.read_text()

    assert "invalid xray version pin" in source
    assert "invalid xray sha256 pin" in source
    assert "invalid hysteria version pin" in source
    assert "invalid hysteria sha256 pin" in source
    assert "invalid RealiTLScanner version pin" in source
    assert "invalid RealiTLScanner sha256 pin" in source
