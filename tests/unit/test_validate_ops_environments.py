"""The ops environment validator keeps CI secrets in their environments and defers untrusted PR input."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate-ops-environments.py"
TFVARS = 'server_name = "p0"\nssh_port = 22\nenable_hysteria = false\nenable_backups = false\n'


def git(repository: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout.strip()


def commit(repository: Path, files: dict[str, str | None], message: str = "change") -> str:
    for name, text in files.items():
        path = repository / name
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    git(repository, "add", "-A")
    git(repository, "commit", "-q", "--allow-empty", "-m", message)
    return git(repository, "rev-parse", "HEAD")


@pytest.fixture
def ops(tmp_path: Path) -> Path:
    repository = tmp_path / "ops"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    commit(repository, {"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS, "config/known_hosts": "host key\n",
                        "config/inventories/current.ini": "[vpn]\np0 ansible_host=192.0.2.1\n",
                        "catalog.json": json.dumps({"credentials": []})}, "base")
    return repository


def run(ops: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(SCRIPT), "--root", str(ops), *args], capture_output=True, text=True,
                          timeout=60, check=False)


def workflow(ops: Path, text: str, catalog: list[dict] | None = None) -> None:
    (ops / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (ops / ".github/workflows/ci.yml").write_text(text)
    if catalog is not None:
        (ops / "catalog.json").write_text(json.dumps({"credentials": catalog}))


def entry(environment: str, secret: str) -> dict:
    return {"authority": "gh-environment", "environment": environment, "secret": secret,
            "scope": "fleet project", "expires_at": "2027-05-01", "revoke_procedure": "delete the token"}


APPLY = """
on:
  push:
    branches: [main]
jobs:
  apply:
    runs-on: ubuntu-24.04
    environment: tofu-apply
    steps:
      - run: make apply
        env:
          VULTR_API_KEY: ${{ secrets.VULTR_API_KEY }}
          TF_VAR_state_passphrase: ${{ secrets.STATE_PASSPHRASE }}
"""

PREVIEW = """
on:
  pull_request_target:
    branches: [main]
jobs:
  plan:
    runs-on: ubuntu-24.04
    environment: tofu-plan
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - uses: actions/checkout@0000000000000000000000000000000000000000
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          path: pr
      - run: python3 scripts/validate-ops-environments.py --root pr --pr "$BASE" "$HEAD"
      - run: make plan
        env:
          VULTR_API_KEY: ${{ secrets.VULTR_API_KEY }}
"""


def test_matrix_accepts_secrets_in_their_own_environments(ops):
    workflow(ops, APPLY, [entry("tofu-apply", "VULTR_API_KEY"), entry("tofu-apply", "STATE_PASSPHRASE")])
    result = run(ops)
    assert result.returncode == 0, result.stderr
    assert "2 environment secret references" in result.stdout


def test_matrix_rejects_a_provider_token_in_deploy(ops):
    workflow(ops, APPLY.replace("tofu-apply", "deploy").replace("make apply", "make deploy"),
             [entry("deploy", "VULTR_API_KEY"), entry("deploy", "STATE_PASSPHRASE")])
    result = run(ops)
    assert result.returncode == 1
    assert ".github/workflows/ci.yml job apply: secret VULTR_API_KEY does not belong to environment deploy" in result.stderr


@pytest.mark.parametrize(("change", "message"), [
    (lambda text: text.replace("    environment: tofu-apply\n", ""), "uses secret VULTR_API_KEY without an environment"),
    (lambda text: text.replace("environment: tofu-apply", "environment: ${{ inputs.target }}"), "is not in the environment matrix"),
    (lambda text: text.replace("${{ secrets.VULTR_API_KEY }}", "${{ toJSON(secrets) }}"), "passes the whole secrets context"),
    (lambda text: text.replace("branches: [main]", "branches: [main, release]"), "push trigger must name only branch main"),
], ids=["no-environment", "dynamic-environment", "whole-context", "extra-branch"])
def test_matrix_rejects_unverifiable_secret_use(ops, change, message):
    workflow(ops, change(APPLY), [entry("tofu-apply", "VULTR_API_KEY"), entry("tofu-apply", "STATE_PASSPHRASE")])
    result = run(ops)
    assert result.returncode == 1 and message in result.stderr


def test_trigger_rejects_apply_in_a_preview_environment(ops):
    workflow(ops, PREVIEW.replace("make plan", "make apply"), [entry("tofu-plan", "VULTR_API_KEY")])
    result = run(ops)
    assert result.returncode == 1
    assert "step 4 runs a mutating command in preview environment tofu-plan" in result.stderr


def test_trigger_rejects_a_mutating_environment_on_pull_request_target(ops):
    text = PREVIEW.replace("tofu-plan", "deploy").replace("VULTR_API_KEY", "CI_SSH_PRIVATE_KEY")
    workflow(ops, text, [entry("deploy", "CI_SSH_PRIVATE_KEY")])
    result = run(ops)
    assert result.returncode == 1
    assert "mutating environment deploy must not run on pull_request_target" in result.stderr


def test_trigger_rejects_secrets_on_plain_pull_request(ops):
    workflow(ops, PREVIEW.replace("pull_request_target", "pull_request"), [entry("tofu-plan", "VULTR_API_KEY")])
    result = run(ops)
    assert result.returncode == 1 and "must not run on pull_request" in result.stderr


def test_preview_accepts_validated_pull_request_target(ops):
    workflow(ops, PREVIEW, [entry("tofu-plan", "VULTR_API_KEY")])
    result = run(ops)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("change", "message"), [
    (lambda text: text.replace("      - run: python3 scripts/validate-ops-environments.py --root pr --pr \"$BASE\" \"$HEAD\"\n", ""),
     "step 3 uses a secret before validate-ops-environments.py --pr"),
    (lambda text: text.replace("          path: pr\n", ""), "step 2 checks out the pull request head over the trusted tree"),
], ids=["no-validation", "head-over-trusted-tree"])
def test_preview_rejects_unvalidated_pull_request_input(ops, change, message):
    workflow(ops, change(PREVIEW), [entry("tofu-plan", "VULTR_API_KEY")])
    result = run(ops)
    assert result.returncode == 1 and message in result.stderr


def test_catalog_gap_is_reported(ops):
    incomplete = entry("tofu-apply", "STATE_PASSPHRASE")
    del incomplete["expires_at"]
    workflow(ops, APPLY, [incomplete])
    result = run(ops)
    assert result.returncode == 1
    assert "catalog.json: no gh-environment entry for VULTR_API_KEY in tofu-apply" in result.stderr
    assert "catalog.json: STATE_PASSPHRASE in tofu-apply has no expires_at" in result.stderr


def classify(ops: Path, base: str, head: str) -> tuple[int, dict]:
    result = run(ops, "--pr", base, head)
    return result.returncode, json.loads(result.stdout)


def test_untrusted_input_previews_a_boolean_toggle(ops):
    base = git(ops, "rev-parse", "HEAD")
    head = commit(ops, {"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("enable_hysteria = false", "enable_hysteria = true")})
    code, verdict = classify(ops, base, head)
    assert code == 0 and verdict["verdict"] == "preview"
    assert verdict["toggles"] == [{"path": "config/tfvars/upcloud/p0-upcloud.tfvars", "field": "enable_hysteria",
                                   "from": "false", "to": "true"}]


@pytest.mark.parametrize(("files", "reason"), [
    ({"config/inventories/current.ini": "[vpn]\np0 ansible_host=\"{{ lookup('pipe', 'id') }}\"\n"},
     "config/inventories/current.ini: changes to this path need the operator's merge"),
    ({"config/inventories/current.ini": "[vpn]\np0 ansible_host=192.0.2.9\n", "config/known_hosts": "other key\n"},
     "config/known_hosts: changes to this path need the operator's merge"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("ssh_port = 22", "ssh_port = 2222")},
     "field ssh_port needs the operator's merge"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("enable_hysteria = false", 'enable_hysteria = "${file("x")}"')},
     "enable_hysteria must stay a plain boolean"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS + "enable_backups = true\n"}, "lines were added or removed"),
    ({"config/tfvars/upcloud/new-node.tfvars": TFVARS}, "A change needs the operator's merge"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": None}, "D change needs the operator's merge"),
    ({".sops.yaml": "creation_rules: []\n"}, ".sops.yaml: A change needs the operator's merge"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("enable_hysteria = false", "enable_hysteria = true\rssh_port = 2222")},
     "control or non-ASCII bytes need the operator's merge"),
    ({"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("enable_hysteria = false", "enable_hysteria = true\u2028ssh_port = 2222")},
     "control or non-ASCII bytes need the operator's merge"),
], ids=["jinja-inventory", "target-and-pin", "other-field", "non-boolean", "new-line", "new-target", "deletion", "recipients",
        "carriage-return", "unicode-separator"])
def test_untrusted_input_defers_everything_else(ops, files, reason):
    base = git(ops, "rev-parse", "HEAD")
    head = commit(ops, files)
    code, verdict = classify(ops, base, head)
    assert code == 1 and verdict["verdict"] == "defer" and verdict["toggles"] == []
    assert any(reason in line for line in verdict["reasons"]), verdict["reasons"]


def test_untrusted_input_defers_a_symlinked_toggle_file_and_rename(ops):
    base = git(ops, "rev-parse", "HEAD")
    (ops / "config/tfvars/upcloud/p0-upcloud.tfvars").unlink()
    (ops / "config/tfvars/upcloud/p0-upcloud.tfvars").symlink_to("/etc/passwd")
    head = commit(ops, {})
    code, verdict = classify(ops, base, head)
    assert code == 1 and any("T change" in reason or "symlink" in reason for reason in verdict["reasons"])
    moved = commit(ops, {"config/tfvars/upcloud/p0-upcloud.tfvars": None, "config/tfvars/upcloud/renamed.tfvars": TFVARS})
    code, verdict = classify(ops, base, moved)
    assert code == 1 and verdict["verdict"] == "defer"


def test_untrusted_input_defers_a_head_that_does_not_descend_from_base(ops):
    base = git(ops, "rev-parse", "HEAD")
    git(ops, "checkout", "-q", "--orphan", "other")
    head = commit(ops, {"config/tfvars/upcloud/p0-upcloud.tfvars": TFVARS.replace("false", "true", 1)})
    code, verdict = classify(ops, base, head)
    assert code == 1 and "head does not descend from the trusted base" in verdict["reasons"]


def test_pin_must_be_reachable_from_public_main(ops, tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    git(public, "init", "-q", "-b", "main")
    published = commit(public, {"README": "a\n"})
    git(public, "checkout", "-q", "-b", "fork")
    forked = commit(public, {"README": "b\n"})
    git(public, "checkout", "-q", "main")
    for revision, code in ((published, 0), (forked, 1)):
        (ops / "upstream.lock").write_text(f"repository=https://example.invalid/public\nrevision={revision}\n")
        result = run(ops, "--public-repo", str(public), "--public-ref", "main")
        assert result.returncode == code, result.stderr
    assert "upstream.lock: revision is not reachable from main of the public repository" in result.stderr
    base = git(ops, "rev-parse", "HEAD")
    head = commit(ops, {"upstream.lock": f"repository=https://example.invalid/public\nrevision={forked}\n"})
    result = run(ops, "--pr", base, head, "--public-repo", str(public), "--public-ref", "main")
    assert result.returncode == 1 and "not reachable" in json.loads(result.stdout)["reasons"][0]
