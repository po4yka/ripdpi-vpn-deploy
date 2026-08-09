"""Keep release-please and binary release tags on one contract."""

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_release_please_emits_vpnd_component_tags():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["include-component-in-tag"] is True
    assert config["packages"]["."]["component"] == "vpnd"


def test_binary_workflow_validates_vpnd_tag_contract():
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()
    validator = (ROOT / "scripts/validate-vpnd-release-tag.sh").read_text()
    assert "vpnd-v*" in workflow
    assert "^vpnd-v[0-9]+" in validator


def test_release_job_uses_one_validated_tag_for_all_dispatch_paths(tmp_path):
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()
    validator = ROOT / "scripts/validate-vpnd-release-tag.sh"

    resolver = "${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}"
    assert workflow.count(resolver) == 1
    assert "fetch-depth: 0" in workflow
    assert 'bash scripts/validate-vpnd-release-tag.sh "$TAG" "$GITHUB_SHA"' in workflow
    assert "release-tag: ${{ steps.validate.outputs.release-tag }}" in workflow
    assert "RELEASE_TAG: ${{ needs.validate-tag.outputs.release-tag }}" in workflow
    assert "SBOM_LABEL: ${{ needs.validate-tag.outputs.release-tag }}" in workflow
    assert "name: sbom-${{ needs.validate-tag.outputs.release-tag }}" in workflow

    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "release-contract",
            "GIT_AUTHOR_EMAIL": "release-contract@example.invalid",
            "GIT_COMMITTER_NAME": "release-contract",
            "GIT_COMMITTER_EMAIL": "release-contract@example.invalid",
        }
    )
    subprocess.run(["git", "init", "-q", tmp_path], check=True, env=environment)
    (tmp_path / "source").write_text("tagged\n")
    subprocess.run(["git", "add", "source"], cwd=tmp_path, check=True, env=environment)
    subprocess.run(
        ["git", "commit", "-q", "-m", "tagged release"],
        cwd=tmp_path,
        check=True,
        env=environment,
    )
    tagged_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    subprocess.run(
        ["git", "branch", "vpnd-v1.2.3"], cwd=tmp_path, check=True, env=environment
    )
    branch_only = subprocess.run(
        ["bash", validator, "vpnd-v1.2.3", tagged_revision],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert branch_only.returncode != 0
    assert "does not resolve to a commit" in branch_only.stderr

    subprocess.run(
        ["git", "tag", "vpnd-v1.2.3"], cwd=tmp_path, check=True, env=environment
    )

    matched = subprocess.run(
        ["bash", validator, "vpnd-v1.2.3", tagged_revision],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert matched.returncode == 0, matched.stderr
    assert matched.stdout == "release-tag=vpnd-v1.2.3\n"

    (tmp_path / "source").write_text("dispatch branch moved\n")
    subprocess.run(["git", "add", "source"], cwd=tmp_path, check=True, env=environment)
    subprocess.run(
        ["git", "commit", "-q", "-m", "later revision"],
        cwd=tmp_path,
        check=True,
        env=environment,
    )
    dispatch_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    mismatched = subprocess.run(
        ["bash", validator, "vpnd-v1.2.3", dispatch_revision],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert mismatched.returncode != 0
    assert "does not match the workflow revision" in mismatched.stderr


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
