"""Certificate preflight must use the exact runtime variable order."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_backup_integrity_contract import configure, controller_adapter
from test_deploy_controller import commit_fixture, invoke, workspace, write


@pytest.mark.parametrize("limit", ["", "node-one"])
def test_deployment_checks_each_selected_host_with_ordered_variables(workspace, limit):
    record = workspace["root"].parent / "certificate-scopes.jsonl"
    write(workspace["root"] / "scripts/check-certs.sh", f"""#!{sys.executable}
import json, os, pathlib, yaml
paths = json.loads(os.environ['VPN_CERT_VARS_FILES'])
documents = [yaml.safe_load(pathlib.Path(path).read_text()) or {{}} for path in paths]
with pathlib.Path({str(record)!r}).open('a') as stream:
    stream.write(json.dumps({{'files': [pathlib.Path(path).name for path in paths],
        'vpn': [document.get('vpn') for document in documents],
        'provider': [document.get('provider') for document in documents]}}) + '\\n')
""", 0o700)
    commit_fixture(workspace)
    result = invoke(workspace, limit=limit)
    assert result.returncode == 0, result.stdout + result.stderr
    scopes = [json.loads(line) for line in record.read_text().splitlines()]
    assert len(scopes) == (1 if limit else 2)
    for index, scope in enumerate(scopes):
        cohort = "vpn-p0" if index == 0 else "vpn-p1p2"
        assert scope["files"] == [f"{index}-all.yml", f"{index}-vpn.yml", f"{index}-{cohort}.yml",
                                  f"{index}-metadata.json", "secrets.yaml"]
        assert scope["vpn"][2] == {"enable_xray_reality": index == 0}
        assert scope["provider"][3] == ("upcloud" if index == 0 else "vultr")


def test_backup_certificate_precheck_retains_approved_override_order(configure, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    controller_adapter(configure, monkeypatch)
    for name in ("SKIP_PRECHECK", "ANSIBLE_TAGS", "ANSIBLE_RUN_TAGS", "ANSIBLE_SKIP_TAGS", "ANSIBLE_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    source = tmp_path / "secrets.yaml"
    source.write_text("fixture_secret: synthetic-test-value\n")
    source.chmod(0o600)
    overrides = tmp_path / "approved.yaml"
    overrides.write_text("public_site_canonical_url: https://fixture.example.invalid\n")
    overrides.chmod(0o600)
    monkeypatch.setenv("BACKUP_CONFIGURE_EXTRA_VARS_FILE", str(overrides))
    scopes, commands = [], []

    def run(command, **kwargs):
        commands.append(command)
        if command[0].endswith("check-certs.sh"):
            paths = json.loads(kwargs["env"]["VPN_CERT_VARS_FILES"])
            assert paths[:-2] == configure.canonical_variables(Path(configure.__file__).resolve().parents[1], [])
            assert Path(paths[-2]).read_text() == source.read_text()
            assert Path(paths[-1]).read_text() == overrides.read_text()
            scopes.append(paths)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(configure.subprocess, "run", run)
    configure.controller("unused", "node-one", str(source))
    assert len(scopes) == 1
    assert commands[-1][0] == "ansible-playbook"
    assert all(not Path(path).exists() for path in scopes[0][-2:])
