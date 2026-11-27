"""Reproducible-build pins must be validated before reaching shell source."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reproducible-build.yml"


def test_pin_outputs_are_passed_to_shell_as_environment_data():
    source = WORKFLOW.read_text()

    assert source.count("PIN_VERSION: ${{ steps.pin.outputs.version }}") == 2
    assert source.count("PIN_SHA: ${{ steps.pin.outputs.sha }}") == 2
    assert "PIN_RELEASE: ${{ steps.pin.outputs.release }}" in source
    assert "download/${{ steps.pin.outputs." not in source
    assert '== "${{ steps.pin.outputs.sha }}"' not in source


def test_pin_readers_reject_untrusted_version_and_sha_grammar():
    source = WORKFLOW.read_text()

    assert "invalid hysteria release pin" in source
    assert "invalid hysteria version pin" in source
    assert "invalid hysteria sha256 pin" in source
    assert "invalid RealiTLScanner version pin" in source
    assert "invalid RealiTLScanner sha256 pin" in source


def test_release_asset_jobs_never_skip_on_a_placeholder_pin():
    # The example secrets file carries placeholder digests; a job that reads them can only skip.
    source = WORKFLOW.read_text()

    assert "prod.secrets.example.yaml" not in source
    assert "REPLACE_WITH" not in source
    assert "scripts/security-runtime-artifacts.json" in source


def test_producer_only_dispatch_preserves_the_default_full_gate():
    import yaml
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True]
    for trigger in ('workflow_dispatch', 'workflow_call'):
        intent = triggers[trigger]['inputs']['artifact_producer_only']
        assert intent['type'] == 'boolean' and intent['default'] is False
    assert 'if' not in workflow['jobs']['security-runtimes']
    assert set(workflow['jobs']) == {'security-runtimes', 'hysteria', 'realitlscanner'}
    for job in ('hysteria', 'realitlscanner'):
        assert workflow['jobs'][job]['if'] == '${{ !inputs.artifact_producer_only }}'
