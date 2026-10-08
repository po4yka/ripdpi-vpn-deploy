"""Exercise secrets parsing through the actual shell probe, without networking."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def probe(tmp_path, document):
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "python3").symlink_to(sys.executable)
    for name, content in {
        "timeout": '#!/bin/sh\nshift\nexec "$@"\n',
        "openssl": '#!/bin/sh\nprintf "%s\\n" "-----BEGIN CERTIFICATE-----"\n',
    }.items():
        path = tools / name
        path.write_text(content)
        path.chmod(0o755)
    secrets = tmp_path / "synthetic.yaml"
    secrets.write_text(document)
    output = tmp_path / "report.json"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/probe-sni-survival.sh"), "192.0.2.10",
         "--secrets", str(secrets), "--out", str(output)],
        env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"], "SERVER_NAMES": ""},
        capture_output=True, text=True, timeout=10,
    )
    return result, output


@pytest.mark.parametrize("format_name", ["block", "flow", "json"])
def test_only_xray_server_names_become_probe_targets(tmp_path, format_name):
    value = {"xray": {"server_names": ["first.example.test", "xn--second.example.test"],
                      "clients": [{"name": "ci-test"}, {"name": "watchdog"}]},
             "another": {"server_names": ["unrelated.example.test"]}}
    document = (json.dumps(value) if format_name == "json" else
                yaml.safe_dump(value, sort_keys=False, default_flow_style=format_name == "flow"))
    result, output = probe(tmp_path, document)
    assert result.returncode == 0, result.stderr
    reports = json.loads(output.read_text())["results"]
    assert [entry["server_name"] for entry in reports] == value["xray"]["server_names"]
    for entry in reports:
        assert set(entry["variants"]) == {entry["server_name"], "www." + entry["server_name"]}


@pytest.mark.parametrize("names", [None, [], "example.test", [42], ["two names"], ["*.example.test"]])
def test_invalid_secret_names_fail_before_probing(tmp_path, names):
    result, output = probe(tmp_path, yaml.safe_dump({"xray": {"server_names": names}}))
    assert result.returncode != 0
    assert result.stderr.strip() == "invalid xray.server_names in secrets"
    assert not output.exists()


def test_malformed_secrets_are_not_echoed_to_diagnostics(tmp_path):
    result, output = probe(tmp_path, "xray: [private-synthetic-marker")
    assert result.returncode != 0
    assert "private-synthetic-marker" not in result.stdout + result.stderr
    assert result.stderr.strip() == "invalid xray.server_names in secrets"
    assert not output.exists()
