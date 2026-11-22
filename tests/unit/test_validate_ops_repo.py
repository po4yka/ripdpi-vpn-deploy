"""The ops repository validator refuses plaintext secrets, loose pins and unmapped catalog entries."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate-ops-repo.py"
TEMPLATE = ROOT / "templates/ops-repo"
OPERATOR = "age1operatorrecipientfixture"
CI = "age1cirecipientfixture"


def run(ops: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(ops)], capture_output=True, text=True, check=False)


def sops_document(*recipients: str) -> str:
    entries = "".join(f"    - recipient: {key}\n      enc: synthetic-wrapped-key\n" for key in recipients)
    return f"vpn:\n  password: ENC[AES256_GCM,data:synthetic,type:str]\nsops:\n  age:\n{entries}  version: 3.9.0\n"


@pytest.fixture
def ops(tmp_path: Path) -> Path:
    root = tmp_path / "ops"
    shutil.copytree(TEMPLATE, root)
    (root / "upstream.lock").write_text(
        "repository=https://github.com/po4yka/ripdpi-vpn-deploy\nrevision=" + "a" * 40 + "\n")
    (root / "config").mkdir()
    (root / "config/.sops.yaml").write_text(
        f"creation_rules:\n  - path_regex: config/.*\\.sops\\.yaml$\n    age: >-\n      {OPERATOR},\n      {CI}\n")
    (root / "config/prod.secrets.sops.yaml").write_text(sops_document(OPERATOR, CI))
    (root / "catalog.json").write_text(json.dumps({"credentials": [{"id": "ci-age", "authority": "gh-environment"}]}))
    return root


def test_template_with_a_pinned_revision_and_encrypted_documents_passes(ops: Path) -> None:
    result = run(ops)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("revision", ["main", "v1.0.0", "a" * 12, "A" * 40])
def test_pin_must_be_a_full_lowercase_commit_sha(ops: Path, revision: str) -> None:
    (ops / "upstream.lock").write_text(f"repository=https://github.com/po4yka/ripdpi-vpn-deploy\nrevision={revision}\n")
    result = run(ops)
    assert result.returncode == 1
    assert "upstream.lock: revision must be a full 40-character commit SHA" in result.stderr


def test_pin_must_name_the_public_repository(ops: Path) -> None:
    (ops / "upstream.lock").write_text("repository=https://github.com/example/fork\nrevision=" + "a" * 40 + "\n")
    assert "upstream.lock: repository must be" in run(ops).stderr


PEM = "-----BEGIN {} PRIVATE " + "KEY-----\nsynthetic"  # split so secret scanners skip this fixture


@pytest.mark.parametrize("marker", ["AGE-SECRET-KEY-1SYNTHETIC", PEM.format("OPENSSH"), PEM.format("ENCRYPTED")])
def test_private_key_material_names_the_path_but_not_the_content(ops: Path, marker: str) -> None:
    (ops / "plans").mkdir()
    (ops / "plans/notes.md").write_text(f"notes\n{marker}\n")
    result = run(ops)
    assert result.returncode == 1
    assert "plans/notes.md: private key material" in result.stderr
    assert "SYNTHETIC" not in result.stderr and "synthetic" not in result.stderr


@pytest.mark.parametrize("name", ["config/prod.secrets.yaml", "config/prod.secrets.sops.yaml.dec",
                                  "state/terraform.tfstate", "prod.tfplan", ".env"])
def test_plaintext_secret_state_and_plan_files_are_refused(ops: Path, name: str) -> None:
    path = ops / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("vpn:\n  password: synthetic-plaintext\n")
    result = run(ops)
    assert result.returncode == 1
    assert f"{name}: state, plan or decrypted secret file" in result.stderr


def test_sops_document_without_metadata_is_refused(ops: Path) -> None:
    (ops / "config/prod.secrets.sops.yaml").write_text("vpn:\n  password: synthetic-plaintext\n")
    assert "config/prod.secrets.sops.yaml: SOPS document without age metadata" in run(ops).stderr


def test_sops_recipient_outside_the_policy_is_refused(ops: Path) -> None:
    (ops / "config/prod.secrets.sops.yaml").write_text(sops_document(OPERATOR, "age1unlistedrecipient"))
    assert "encrypted to a recipient outside config/.sops.yaml" in run(ops).stderr


@pytest.mark.parametrize("entry", [{"id": "token"}, {"id": "token", "authority": "laptop"}, "token"])
def test_catalog_credentials_need_an_allowed_authority(ops: Path, entry: object) -> None:
    (ops / "catalog.json").write_text(json.dumps({"credentials": [entry]}))
    assert "catalog.json: credentials[0] has no allowed authority" in run(ops).stderr


def test_template_holds_only_documentation_addresses() -> None:
    documentation = ("192.0.2.", "198.51.100.", "203.0.113.")
    for path in TEMPLATE.rglob("*"):
        if path.is_file():
            for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", path.read_text()):
                assert address.startswith(documentation), (path, address)


def test_plaintext_deployment_sections_are_refused_whatever_the_file_name(ops: Path) -> None:
    (ops / "config/prod.yaml").write_text("xray:\n  uuid: synthetic-plaintext\n")
    (ops / "config/group_vars").mkdir()
    (ops / "config/group_vars/vpn.yml").write_text("vpn:\n  enable_xray_reality: true\n")
    result = run(ops)
    assert "config/prod.yaml: plaintext deployment secret sections" in result.stderr
    assert "group_vars" not in result.stderr


def test_plaintext_sops_json_and_any_dec_file_are_refused(ops: Path) -> None:
    (ops / "config/prod.secrets.sops.json").write_text('{"xray": {"uuid": "synthetic-plaintext"}}')
    (ops / "config/notes.dec").write_text("synthetic\n")
    result = run(ops)
    assert "config/prod.secrets.sops.json: SOPS document without age metadata" in result.stderr
    assert "config/notes.dec: state, plan or decrypted secret file" in result.stderr


@pytest.mark.parametrize("document", [
    sops_document(OPERATOR).replace("ENC[AES256_GCM,data:synthetic,type:str]", "synthetic-plaintext"),
    "xray:\n  uuid: ENC[AES256_GCM,data:synthetic,type:str]\nsops:\n  age:\n    recipient: x\n",
])
def test_copied_sops_block_does_not_hide_plaintext_or_malformed_metadata(ops: Path, document: str) -> None:
    (ops / "config/prod.secrets.sops.yaml").write_text(document)
    assert run(ops).returncode == 1


def test_empty_values_stay_valid_in_an_encrypted_document(ops: Path) -> None:
    (ops / "config/prod.secrets.sops.yaml").write_text(sops_document(OPERATOR).replace(
        "vpn:\n", "vpn:\n  salt: ''\n  optional: null\n"))
    assert run(ops).returncode == 0


@pytest.mark.parametrize("line", ["[Interface]\nPrivateKey = synthetic\n", PEM.replace("{} PRIVATE", "PGP PRIVATE").replace("KEY-----", "KEY BLOCK-----")])
def test_tunnel_and_pgp_private_keys_are_refused(ops: Path, line: str) -> None:
    (ops / "plans").mkdir()
    (ops / "plans/device.conf").write_text(line)
    assert "plans/device.conf: private key material" in run(ops).stderr


def test_symbolic_links_are_refused(ops: Path, tmp_path: Path) -> None:
    (tmp_path / "outside.yaml").write_text("synthetic\n")
    (ops / "config/linked.yaml").symlink_to(tmp_path / "outside.yaml")
    assert "config/linked.yaml: symbolic links are not allowed" in run(ops).stderr


def test_malformed_policy_is_a_finding_not_a_crash(ops: Path) -> None:
    (ops / "config/.sops.yaml").write_text("creation_rules:\n  - key_groups:\n      - age: [x]\n")
    result = run(ops)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert "config/.sops.yaml: rules must be mappings with an age recipient list" in result.stderr


def test_git_checkout_skips_ignored_runtime_files(ops: Path) -> None:
    (ops / "runtime").mkdir()
    (ops / "runtime/prod.secrets.yaml").write_text("xray:\n  uuid: synthetic-plaintext\n")
    subprocess.run(["git", "init", "-q", str(ops)], check=True)
    assert run(ops).returncode == 0
    (ops / ".gitignore").write_text("")
    assert "runtime/prod.secrets.yaml" in run(ops).stderr
