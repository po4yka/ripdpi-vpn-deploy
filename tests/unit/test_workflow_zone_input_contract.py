"""Credentialed deploy workflows must pass dispatch zones as Terraform data."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github/workflows"
WORKFLOWS = ("real-vps-deploy.yml", "transport-reachability-matrix.yml")


def test_dispatch_zone_is_never_expanded_inside_shell_source():
    for name in WORKFLOWS:
        source = (WORKFLOW_DIR / name).read_text()

        assert "TF_VAR_zone: ${{ github.event.inputs.zone || 'fi-hel1' }}" in source
        assert 'zone                 = "${{ github.event.inputs.zone' not in source
        assert source.count("TF_VAR_zone:") == 1
