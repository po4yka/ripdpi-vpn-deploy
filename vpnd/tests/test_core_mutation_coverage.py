"""Exercise inventory subprocess boundaries directly for mutation associations."""

import asyncio
import json
import os
import sys
import threading

import pytest

from artifact_helpers import context, executable, scaffold
from vpnd.runner import Cmd, ansible, make, process
from vpnd.state import Host


@pytest.mark.parametrize(
    "builder,name", [(ansible.verify, "verify"), (ansible.smoke, "smoke-test")]
)
def test_public_playbook_builders_keep_inventory_and_secret_delivery(tmp_path, builder, name):
    ctx = context(scaffold(tmp_path))
    command = builder(ctx)
    assert command.program == "ansible-playbook"
    assert command.argv == [
        str(ctx.ansible_dir / "playbooks" / f"{name}.yml"),
        "--inventory",
        str(ctx.ansible_dir / "inventory/generated.ini"),
    ]
    assert command.directory == ctx.root
    assert dict(command.environment) == {
        "ANSIBLE_CONFIG": str(ctx.ansible_cfg()),
        "VPN_SECRETS_FILE": str(ctx.secrets_file),
    }
    assert str(ctx.secrets_file) not in command.redacted_explain()


def inventory_program(tmp_path, monkeypatch, inventory):
    scaffold(tmp_path)
    marker = tmp_path / "inventory-call.json"
    executable(
        tmp_path,
        "ansible-inventory",
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(json.dumps({{'args': sys.argv[1:], 'cwd': os.getcwd(), 'config': os.environ.get('ANSIBLE_CONFIG')}}))\n"
        f"print({json.dumps(inventory)!r})\n",
    )
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return context(tmp_path), marker


def inventory():
    return {
        "vpn": {"hosts": ["selected", "second", "foreign"]},
        "_meta": {
            "hostvars": {
                "selected": {
                    "env": "test",
                    "provider": "upcloud",
                    "ansible_host": "203.0.113.8",
                    "vpn_service_address": "192.0.2.1",
                },
                "second": {"env": "test", "provider": "upcloud", "ansible_host": "192.0.2.2"},
                "foreign": {"env": "test", "provider": "hetzner", "ansible_host": "192.0.2.3"},
            }
        },
    }


def test_inventory_scope_uses_selected_provider_and_service_address(tmp_path, monkeypatch):
    ctx, marker = inventory_program(tmp_path, monkeypatch, inventory())
    selected = asyncio.run(ansible.scoped_limit(ctx))
    assert selected == "second,selected"
    host = ("registered", Host("test", "upcloud", ipv4="192.0.2.1"))
    selected_host = asyncio.run(ansible.scoped_limit(ctx, host))
    assert selected_host == "selected"
    assert json.loads(marker.read_text()) == {
        "args": ["--inventory", str(ctx.ansible_dir / "inventory/generated.ini"), "--list"],
        "cwd": str(ctx.root),
        "config": str(ctx.ansible_cfg()),
    }
    assert os.environ["PATH"] == str(tmp_path / "bin")


def test_inventory_scope_refuses_ambiguous_service_address(tmp_path, monkeypatch):
    data = inventory()
    data["_meta"]["hostvars"]["second"]["vpn_service_address"] = "192.0.2.1"
    ctx, marker = inventory_program(tmp_path, monkeypatch, data)
    host = ("registered", Host("test", "upcloud", ipv4="192.0.2.1"))
    with pytest.raises(ValueError, match="exactly one matching inventory hosts, found 2"):
        asyncio.run(ansible.scoped_limit(ctx, host))
    assert marker.is_file()


def test_inventory_scope_explain_does_not_spawn_inventory_program(tmp_path, monkeypatch):
    ctx, marker = inventory_program(tmp_path, monkeypatch, inventory())
    ctx.explain = True
    selected = asyncio.run(ansible.scoped_limit(ctx))
    assert selected == "<validated inventory host keys>"
    assert not marker.exists()


def test_make_secret_path_rejects_all_c0_and_c1_controls_without_disclosing_value():
    for code in [*range(32), *range(127, 160)]:
        value = "/tmp/fixture-private-" + chr(code) + ".yaml"
        with pytest.raises(ValueError) as failure:
            make.validate_kv("SECRETS_FILE", value)
        assert "fixture-private-" not in str(failure.value)


def test_make_identifier_allowlist_accepts_uppercase_ascii():
    for key, value in [("ENV", "StageA"), ("PRESET", "TCPA-1"), ("TAG", "READY_tag")]:
        make.validate_kv(key, value)


def test_late_cancellation_checks_stop_under_the_shared_spawn_lock(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    stopped = threading.Event()
    spawned, results, errors = [], [], []
    original_spawn = process.subprocess.Popen

    def observe_spawn(*args, **kwargs):
        spawned.append(True)
        return original_spawn(*args, **kwargs)

    class HeldLock:
        def __enter__(self):
            entered.set()
            released = release.wait(5)
            assert released, "shared spawn lock was never released"

        def __exit__(self, *args):
            return False

    command = Cmd.new("sh").args(["-c", ":"])
    monkeypatch.setattr(process.subprocess, "Popen", observe_spawn)

    def work():
        try:
            results.append(command._worker(stopped, True, True, HeldLock()))
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    try:
        reached_lock = entered.wait(3)
        assert reached_lock, "worker bypassed the shared spawn lock"
        stopped.set()
    finally:
        release.set()
        worker.join(timeout=3)
    assert not worker.is_alive(), "stopped worker did not finish"
    assert not errors and not spawned
    assert results == [(0, b"", b"")]


def test_async_capture_passes_its_shared_spawn_lock_to_the_real_worker(monkeypatch):
    command = Cmd.new("sh").args(["-c", ":"])
    observed = []
    original_worker = command._worker

    def observe_worker(stopped, capture, detailed, spawn_lock=None):
        assert spawn_lock is not None, "capture dropped the shared cancellation lock"
        observed.append(spawn_lock)
        return original_worker(stopped, capture, detailed, spawn_lock)

    monkeypatch.setattr(command, "_worker", observe_worker)
    output = asyncio.run(command.capture_detailed())
    assert output.rc == 0 and output.stdout == output.stderr == ""
    assert len(observed) == 1
