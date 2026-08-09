"""Contracts that keep the deployed fleet tied to an exact repository revision."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
SOURCE_DRIFT_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "source-drift.yml"
MANIFEST_TEMPLATE = (
    REPO_ROOT / "ansible" / "roles" / "node_manifest" / "templates" / "manifest.json.j2"
)
IDENTITY_SCRIPT = REPO_ROOT / "scripts" / "deploy-source-identity.sh"


def test_manifest_records_only_deterministic_source_provenance() -> None:
    template = MANIFEST_TEMPLATE.read_text()

    assert '"source_revision": {{ node_manifest_source_revision | to_json }}' in template
    assert '"deployable_digest": {{ node_manifest_deployable_digest | to_json }}' in template
    assert '"generated_at"' not in template


def test_source_drift_playbook_fails_closed_on_revision_mismatch() -> None:
    source = SOURCE_DRIFT_PLAYBOOK.read_text()
    playbook = yaml.safe_load(source)
    tasks = playbook[0]["tasks"]
    rendered = str(tasks)

    assert "/var/lib/ripdpi-vpn-deploy/manifest.json" in source
    assert "DEPLOY_SOURCE_REVISION" in source
    assert "DEPLOYABLE_SOURCE_DIGEST" in source
    assert "source_revision" in rendered
    assert "deployable_digest" in rendered
    assert "expected_deployable_digest" in rendered
    assert source.count("source_revision | default('unknown')") == 2


def test_make_deploy_records_and_verifies_clean_head() -> None:
    makefile = MAKEFILE.read_text()

    assert "DEPLOY_SOURCE_REVISION" in makefile
    assert "DEPLOYABLE_SOURCE_DIGEST" in makefile
    assert "require-clean-source" in makefile
    assert "source-drift" in makefile
    assert "deploy: require-clean-source" in makefile
    assert "verify: require-clean-source" in makefile


def test_deploy_identity_matches_committed_deployable_tree() -> None:
    revision, digest = subprocess.check_output(
        [IDENTITY_SCRIPT, "--identity"], cwd=REPO_ROOT, text=True
    ).split()
    tree = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "-z",
            revision,
            "--",
            "ansible",
            "scripts",
            "requirements.yml",
        ],
        cwd=REPO_ROOT,
    )

    assert digest == hashlib.sha256(tree).hexdigest()
    assert b"docs/" not in tree
