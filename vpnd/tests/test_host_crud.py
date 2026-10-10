"""Host registry CLI calls across independent processes and private homes."""

from pathlib import Path
import json
import os
import subprocess
import sys

LAUNCHER = Path(__file__).resolve().parents[2] / "scripts/vpnd.py"


def invoke(root, args):
    for provider in ("upcloud", "hetzner", "vultr"):
        (root / "terraform/providers" / provider).mkdir(parents=True, exist_ok=True)
    (root / "ansible").mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / ".config"), VPND_LOG="error")
    return subprocess.run(
        [sys.executable, str(LAUNCHER), "--root", str(root), "--provider", "upcloud", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


# Rust test: vpnd/tests/host_crud.rs::host_cli_persists_add_show_overwrite_and_remove
def test_host_cli_persists_add_show_overwrite_and_remove(tmp_path):
    assert "no hosts registered" in invoke(tmp_path, ["host", "list"]).stderr
    assert (
        invoke(
            tmp_path,
            [
                "host",
                "add",
                "test-host",
                "--env",
                "staging",
                "--provider",
                "hetzner",
                "--ipv4",
                "192.0.2.1",
                "--ipv6",
                "2001:db8::1",
            ],
        ).returncode
        == 0
    )
    output = invoke(tmp_path, ["host", "show", "test-host"])
    assert output.returncode == 0
    host = json.loads(output.stdout)
    assert (
        host["env"] == "staging"
        and host["provider"] == "hetzner"
        and host["ipv4"] == "192.0.2.1"
        and host["ipv6"] == "2001:db8::1"
    )
    assert "test-host" in invoke(tmp_path, ["host", "list"]).stdout
    assert (
        invoke(
            tmp_path, ["host", "add", "test-host", "--env", "prod", "--provider", "vultr"]
        ).returncode
        == 0
    )
    host = json.loads(invoke(tmp_path, ["host", "show", "test-host"]).stdout)
    assert host["provider"] == "vultr" and host["ipv4"] is None
    assert invoke(tmp_path, ["host", "remove", "test-host"]).returncode == 0
    assert invoke(tmp_path, ["host", "show", "test-host"]).returncode != 0
    assert invoke(tmp_path, ["host", "remove", "test-host"]).returncode != 0
    assert "no hosts registered" in invoke(tmp_path, ["host", "list"]).stderr


# Rust test: vpnd/tests/host_crud.rs::json_flag_emits_machine_readable_list_and_show
def test_json_flag_emits_machine_readable_list_and_show(tmp_path):
    empty = invoke(tmp_path, ["host", "list", "--json"])
    assert empty.returncode == 0 and json.loads(empty.stdout) == []
    assert (
        invoke(
            tmp_path,
            [
                "host",
                "add",
                "phone",
                "--env",
                "prod",
                "--provider",
                "upcloud",
                "--ipv4",
                "203.0.113.9",
            ],
        ).returncode
        == 0
    )
    output = invoke(tmp_path, ["host", "list", "--json"])
    assert output.returncode == 0
    hosts = json.loads(output.stdout)
    assert (
        len(hosts) == 1
        and hosts[0]["name"] == "phone"
        and hosts[0]["env"] == "prod"
        and hosts[0]["ipv4"] == "203.0.113.9"
        and hosts[0]["deployed_with"] is None
    )
    output = invoke(tmp_path, ["host", "show", "phone", "--json"])
    assert output.returncode == 0
    assert output.stdout.count("\n") == 1 and json.loads(output.stdout)["provider"] == "upcloud"
    assert invoke(tmp_path, ["host", "show", "phone"]).stdout.count("\n") > 1


def test_host_explain_never_changes_registry(tmp_path):
    assert (
        invoke(
            tmp_path, ["--explain", "host", "add", "one", "--env", "test", "--provider", "upcloud"]
        ).returncode
        == 0
    )
    assert json.loads(invoke(tmp_path, ["host", "list", "--json"]).stdout) == []
    assert (
        invoke(
            tmp_path, ["host", "add", "one", "--env", "test", "--provider", "upcloud"]
        ).returncode
        == 0
    )
    assert invoke(tmp_path, ["host", "remove", "one", "--explain"]).returncode == 0
    assert len(json.loads(invoke(tmp_path, ["host", "list", "--json"]).stdout)) == 1
