"""Use the pinned Xray authentication identity for per-device admission."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from transport_semantics import PLACEHOLDER, cohort_errors

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "00000000-0000-4000-8000-0000000000ab"
ALIASES = [IDENTITY.upper(), "00000000-0000-4fff-8000-0000000000ab"]
DISTINCT = "00000000-0000-4000-8000-0000000000ac"
REFUSAL = ("xray.clients", "duplicate UUID authentication identity")


def devices(second):
    return {"xhttp_path": "/4b8e2c1d", "clients": [
        {"name": "first", "uuid": IDENTITY, "short_id": "aa"},
        {"name": "second", "uuid": second, "short_id": "bb"},
    ]}


@pytest.mark.parametrize("second", ALIASES, ids=["case", "reserved-bytes"])
@pytest.mark.parametrize("cohorts", [False, True])
def test_uuid_authentication_aliases_refuse_without_rewriting(second, cohorts):
    document = devices(second)
    if cohorts:
        document["cohorts"] = [{"name": name, "clients": [name]}
                               for name in ("first", "second")]
    original = deepcopy(document)
    assert cohort_errors(document) == [REFUSAL]
    assert document == original


def test_distinct_uuid_authentication_identities_remain_independently_admitted():
    document = devices(DISTINCT)
    assert not cohort_errors(document)
    for removed in ("first", "second"):
        retained = {"clients": [client for client in document["clients"] if client["name"] != removed]}
        assert not cohort_errors(retained)
        assert len(retained["clients"]) == 1


def test_lenient_example_uuid_placeholders_are_not_authentication_identities():
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    placeholder = example["xray"]["clients"][0]["uuid"]
    assert PLACEHOLDER.fullmatch(placeholder)
    document = devices(placeholder)
    document["clients"][0]["uuid"] = placeholder
    assert not cohort_errors(document, allow_placeholders=True)


@pytest.mark.parametrize("second", [*ALIASES, DISTINCT], ids=["case", "reserved-bytes", "distinct"])
@pytest.mark.parametrize("check_mode", [False, True])
def test_actual_controller_uuid_admission_precedes_mutation(tmp_path, second, check_mode):
    document = devices(second)
    marker = tmp_path / "mutation"
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable,
                 "role_path": str(ROOT / "ansible/roles/xray"),
                 "transport_input_sections": ["xray"], "xray": document,
                 "vpn": {"enable_xray_reality": True}},
        "tasks": [{"ansible.builtin.import_tasks": str(ROOT / "ansible/playbooks/tasks/transport-input-preflight.yml")},
                  {"name": "Publish mutation marker", "ansible.builtin.copy": {"dest": str(marker), "content": "mutated"}}],
    }]))
    argv = ["ansible-playbook", "-i", "localhost,", str(play)]
    if check_mode:
        argv.append("--check")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    accepted = second == DISTINCT
    assert (result.returncode == 0) is accepted
    assert marker.exists() is (accepted and not check_mode)
    if not accepted:
        assert "Publish mutation marker" not in result.stdout
    assert all(client["uuid"] not in result.stdout + result.stderr for client in document["clients"])


@pytest.mark.parametrize("second", ALIASES, ids=["case", "reserved-bytes"])
def test_uuid_refusal_diagnostics_are_categorical(second):
    document = devices(second)
    result = subprocess.run([sys.executable, str(ROOT / "scripts/transport_semantics.py"), "--section=xray"],
                            input=json.dumps({"secrets": {"xray": document}}),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "xray.clients: duplicate UUID authentication identity\n"
