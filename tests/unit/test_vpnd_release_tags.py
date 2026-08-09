"""Keep release-please and binary release tags on one contract."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_please_emits_vpnd_component_tags():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["include-component-in-tag"] is True
    assert config["packages"]["."]["component"] == "vpnd"


def test_binary_workflow_validates_vpnd_tag_contract():
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()
    assert "vpnd-v*" in workflow
    assert "^vpnd-v[0-9]+" in workflow


def test_release_job_uses_one_validated_tag_for_all_dispatch_paths():
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()

    resolver = "${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}"
    assert workflow.count(resolver) == 1
    assert "release-tag: ${{ steps.validate.outputs.release-tag }}" in workflow
    assert "RELEASE_TAG: ${{ needs.validate-tag.outputs.release-tag }}" in workflow
    assert "SBOM_LABEL: ${{ needs.validate-tag.outputs.release-tag }}" in workflow
    assert "name: sbom-${{ needs.validate-tag.outputs.release-tag }}" in workflow


def test_release_assets_are_uploaded_with_rerun_overwrite_semantics():
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()

    assert "softprops/action-gh-release" not in workflow
    assert 'gh release upload "$RELEASE_TAG"' in workflow
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    assert "GH_REPO: ${{ github.repository }}" in workflow
    assert workflow.count("            dist/vpnd-") == 4
    assert "            dist/SHA256SUMS \\" in workflow
    assert "            dist/sbom.json \\" in workflow
    assert "            --clobber" in workflow
