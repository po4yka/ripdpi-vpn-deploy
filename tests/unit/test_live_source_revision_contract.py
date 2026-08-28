"""Contracts that keep the deployed fleet tied to an exact repository revision."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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


@pytest.mark.parametrize("revision, digest, succeeds", [
    ("a" * 40, "b" * 64, True),
    ("c" * 40, "b" * 64, False),
    ("a" * 40, "d" * 64, False),
])
def test_source_drift_executes_full_manifest_identity_check(tmp_path, revision, digest, succeeds):
    """Exercise the complete production playbook against a local synthetic manifest."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for source identity regressions"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 2, "source_revision": revision, "deployable_digest": digest,
    }))
    playbook = tmp_path / "source-drift.yml"
    shutil.copyfile(SOURCE_DRIFT_PLAYBOOK, playbook)
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[vpn]\nlocalhost ansible_connection=local\n")
    variables = tmp_path / "variables.json"
    variables.write_text(json.dumps({
        "ansible_become": False, "ansible_python_interpreter": sys.executable,
        "source_manifest_path": str(manifest),
    }))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"),
               DEPLOY_SOURCE_REVISION="a" * 40, DEPLOYABLE_SOURCE_DIGEST="b" * 64)
    result = subprocess.run(
        [executable, "-i", str(inventory), str(playbook), "--extra-vars", "@" + str(variables)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=40,
    )
    output = result.stdout + result.stderr
    assert (result.returncode == 0) == succeeds, output
    assert ("deployable source matches" if succeeds else "repo-to-live drift detected") in output


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
