"""Fleet rotation safety boundaries; external effects are isolated test doubles."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def rotation(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("fleet_rotation")


@pytest.fixture
def plan(tmp_path):
    value = {
        "schema_version": 1, "id": "rotation-a", "min_active": 1,
        "health": {"config": "liveness.yaml", "nodes": [
            {"current": "upcloud:blue", "inventory_alias": "node-a"},
            {"current": "vultr:blue", "inventory_alias": "node-b"},
            {"current": "hetzner:spare", "inventory_alias": "node-c"},
        ]},
        "rotations": [
            {"current": "upcloud:blue", "new_env": "green", "green_sops_file": "target-a.sops.yaml",
             "migration_plan": "migration-a.json", "migration_approval": "a" * 64},
            {"current": "vultr:blue", "new_env": "green", "new_zone": "zone-b", "green_sops_file": "target-b.sops.yaml",
             "migration_plan": "migration-b.json", "migration_approval": "b" * 64},
        ],
    }
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(value))
    return path


def journal_path(tmp_path):
    return tmp_path / ".omc/state/fleet-rotate-rotation-a.json"


def run(rotation, plan, tmp_path, monkeypatch, *, answers=(True, True), **kwargs):
    calls, health = [], []
    replies = iter(answers)

    def collect(config, nodes, *, excluded=()):
        health.append(copy.deepcopy([node for node in nodes if node["inventory_alias"] not in excluded]))
        return {node["inventory_alias"] for node in nodes} - set(excluded)

    monkeypatch.setattr(rotation, "healthy_survivors", collect)
    monkeypatch.setattr(rotation, "execute_rotation", lambda entry, root, lock: calls.append(entry))
    result = rotation.run_plan(plan, root=tmp_path, confirm=lambda _: next(replies), **kwargs)
    return result, calls, health


def test_real_success_and_boundary_resume(rotation, plan, tmp_path, monkeypatch):
    result, calls, health = run(rotation, plan, tmp_path, monkeypatch, answers=(True, False))
    assert result == 1
    assert [entry["current"] for entry in calls] == ["upcloud:blue"]
    saved = json.loads(journal_path(tmp_path).read_text())
    assert saved["next_idx"] == 1 and saved["in_flight"] is None
    assert [[node["inventory_alias"] for node in nodes] for nodes in health] == [
        ["node-b", "node-c"], ["node-b", "node-c"], ["node-c"],
    ]
    result, calls, health = run(rotation, plan, tmp_path, monkeypatch, resume=True)
    assert result == 0
    assert [entry["current"] for entry in calls] == ["vultr:blue"]
    assert all([node["inventory_alias"] for node in nodes] == ["node-c"] for nodes in health)
    saved = json.loads(journal_path(tmp_path).read_text())
    assert saved["next_idx"] == 2 and saved["in_flight"] is None


@pytest.mark.parametrize("mutation", ["order", "floor", "mapping", "config", "entry"])
def test_changed_plan_refuses_before_health(rotation, plan, tmp_path, monkeypatch, mutation):
    run(rotation, plan, tmp_path, monkeypatch, answers=(True, False))
    value = yaml.safe_load(plan.read_text())
    if mutation == "order":
        value["rotations"].reverse()
    elif mutation == "floor":
        value["min_active"] = 2
    elif mutation == "mapping":
        value["health"]["nodes"][-1]["inventory_alias"] = "other"
    elif mutation == "config":
        value["health"]["config"] = "other.yaml"
    else:
        value["rotations"][-1]["new_env"] = "other"
    plan.write_text(yaml.safe_dump(value))
    original = journal_path(tmp_path).read_bytes()
    monkeypatch.setattr(rotation, "healthy_survivors", lambda *_: pytest.fail("health before identity"))
    with pytest.raises(rotation.RotationError, match="plan-mismatch"):
        rotation.run_plan(plan, root=tmp_path, resume=True)
    assert journal_path(tmp_path).read_bytes() == original


def test_confirmation_rechecks_health(rotation, plan, tmp_path, monkeypatch):
    results = iter(({"node-b", "node-c"}, set()))
    monkeypatch.setattr(rotation, "healthy_survivors", lambda *_, **_kwargs: next(results))
    monkeypatch.setattr(rotation, "execute_rotation", lambda *_: pytest.fail("unhealthy execution"))
    with pytest.raises(rotation.RotationError, match="survivor-floor"):
        rotation.run_plan(plan, root=tmp_path, confirm=lambda _: True)
    assert json.loads(journal_path(tmp_path).read_text())["in_flight"] is None


def test_interrupted_child_never_replays(rotation, plan, tmp_path, monkeypatch):
    monkeypatch.setattr(rotation, "healthy_survivors", lambda _config, nodes, *, excluded=(): {n["inventory_alias"] for n in nodes} - set(excluded))
    def interrupted(*_):
        raise KeyboardInterrupt
    monkeypatch.setattr(rotation, "execute_rotation", interrupted)
    with pytest.raises(KeyboardInterrupt):
        rotation.run_plan(plan, root=tmp_path, confirm=lambda _: True)
    saved = journal_path(tmp_path).read_bytes()
    assert json.loads(saved)["in_flight"] == 0
    with pytest.raises(rotation.RotationError, match="in-flight"):
        rotation.run_plan(plan, root=tmp_path, resume=True)
    assert journal_path(tmp_path).read_bytes() == saved


def test_dry_run_has_no_state_or_health_reads(rotation, plan, tmp_path, monkeypatch):
    monkeypatch.setattr(rotation, "healthy_survivors", lambda *_: pytest.fail("health in dry-run"))
    assert rotation.run_plan(plan, root=tmp_path, dry_run=True) == 0
    assert not (tmp_path / ".omc").exists()


@pytest.mark.parametrize("document", ["{}", '{"next_idx":1}', '{"schema_version":1,"next_idx":-1}', '{bad'])
def test_legacy_or_malformed_journal_preserved(rotation, plan, tmp_path, document):
    path = journal_path(tmp_path)
    path.parent.parent.mkdir(mode=0o700)
    path.parent.mkdir(mode=0o700)
    path.write_text(document)
    path.chmod(0o600)
    with pytest.raises(rotation.RotationError, match="^invalid-journal$"):
        rotation.run_plan(plan, root=tmp_path, resume=True)
    assert path.read_text() == document


def test_existing_progress_not_overwritten(rotation, plan, tmp_path, monkeypatch):
    run(rotation, plan, tmp_path, monkeypatch, answers=(True, False))
    previous = journal_path(tmp_path).read_bytes()
    with pytest.raises(rotation.RotationError, match="already-exists"):
        rotation.run_plan(plan, root=tmp_path)
    assert journal_path(tmp_path).read_bytes() == previous


@pytest.mark.parametrize("kind", ["journal", "lock"])
def test_symlink_refuses_without_touching_target(rotation, plan, tmp_path, kind):
    path = journal_path(tmp_path)
    path.parent.parent.mkdir(mode=0o700)
    path.parent.mkdir(mode=0o700)
    target = tmp_path / "unrelated"
    target.write_text("preserve")
    (path if kind == "journal" else path.with_suffix(".lock")).symlink_to(target)
    category = "invalid-journal" if kind == "journal" else "state-lock-unavailable"
    with pytest.raises(rotation.RotationError, match=f"^{category}$"):
        rotation.run_plan(plan, root=tmp_path, resume=True)
    assert target.read_text() == "preserve"


def test_concurrent_lock_refuses(rotation, plan, tmp_path):
    with rotation.Journal(tmp_path, "rotation-a"), pytest.raises(rotation.RotationError, match="lock"):
        rotation.run_plan(plan, root=tmp_path)


def test_duplicate_yaml_keys_refuse(rotation, plan, tmp_path):
    plan.write_text(plan.read_text() + "min_active: 0\n")
    with pytest.raises(rotation.RotationError):
        rotation.run_plan(plan, root=tmp_path, dry_run=True)
    assert not (tmp_path / ".omc").exists()


def test_completion_write_failure_leaves_inflight(rotation, plan, tmp_path, monkeypatch):
    original = rotation.Journal.write
    def write(self, value):
        if value["next_idx"]:
            raise OSError("synthetic persistence failure")
        original(self, value)
    monkeypatch.setattr(rotation.Journal, "write", write)
    monkeypatch.setattr(rotation, "healthy_survivors", lambda _config, nodes, *, excluded=(): {n["inventory_alias"] for n in nodes} - set(excluded))
    calls = []
    monkeypatch.setattr(rotation, "execute_rotation", lambda entry, *_: calls.append(entry))
    with pytest.raises(OSError):
        rotation.run_plan(plan, root=tmp_path, confirm=lambda _: True)
    assert len(calls) == 1
    assert json.loads(journal_path(tmp_path).read_text())["in_flight"] == 0


def test_state_files_are_private(rotation, plan, tmp_path, monkeypatch):
    run(rotation, plan, tmp_path, monkeypatch, answers=(False,))
    path = journal_path(tmp_path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.with_suffix(".lock").stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


@pytest.fixture
def liveness(rotation, tmp_path, monkeypatch):
    helper = importlib.import_module("fleet_rotation_liveness")
    live = helper.liveness_module()
    monkeypatch.setattr(helper, "liveness_module", lambda: live)
    key = tmp_path / "key"
    key.write_text("test-only-key")
    key.chmod(0o600)
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[vpn]\nnode-c provider=hetzner env=spare ansible_host=100.64.0.1 "
                         "vpn_service_address=192.0.2.9 ansible_user=deploy ansible_port=2222\n"
                         f"[vpn:vars]\nansible_ssh_private_key_file={key}\n")
    monkeypatch.setenv("FLEET_INVENTORY", str(inventory))
    target = {"inventory_alias": "node-c", "public_service_address_sha256":
              hashlib.sha256(b"192.0.2.9").hexdigest(), "deployable_digest": "f" * 64,
              "applied_at": 1_700_000_000}
    config = {"schema_version": 2, "probe_url": "https://probe.example.org/check", "expected_status": 204,
              "expected_runtime": {"awg": "1.0.0", "awg_toolchain": "a" * 64},
              "policies": [{"id": "udp", "required_profiles": ["p2-amneziawg"], "min_failed_vantages": 1}],
              "sentinels": [{"id": "witness", "ssh_target": "sentinel-a", "vantage": "external",
                             "policy": "udp", "target": target,
                             "awg_target": {"provider": "hetzner", "environment": "spare", "instance": "awg0"}}]}
    config_path = tmp_path / "liveness.yaml"
    config_path.write_text(yaml.safe_dump(config))
    report = {"schema_version": 2, "sentinel": "witness", "observed_at": int(time.time()),
              "control": {"verdict": "ok"}, "runtime": config["expected_runtime"],
              "provenance": {"controller_revision": "b" * 40, "runner_sha256": "c" * 64,
                             "public_profile_digest": "d" * 64, "vantage": "external",
                             "client_generation_id": "7f574d16-931e-42b4-a940-853b92f53a14"},
              "target_identity": {**target, "required_profiles": ["p2-amneziawg"],
                                  "source_revision": "b" * 40, "runner_sha256": "c" * 64,
                                  "public_profile_digest": "d" * 64},
              "profiles": [{"profile": "p2-amneziawg", "verdict": "ok", "payload_transport": "tcp-https",
                            "target_address_family": "dualstack", "dns_through_tunnel": True,
                            "authenticated_handshake": True, "fresh_handshake": True,
                            "family_results": {family: {"verdict": "ok", "payload_transport": "tcp-https"}
                                               for family in ("ipv4", "ipv6")}}]}
    monkeypatch.setattr(live, "pull_report", lambda *_: ("witness", json.dumps(report), ""))
    return helper, live, config_path, config, report, [{"current": "hetzner:spare", "inventory_alias": "node-c"}]


def test_udp_only_survivor_uses_canonical_authenticated_evidence(liveness):
    helper, _live, path, _config, _report, nodes = liveness
    assert helper.healthy_survivors(path, nodes) == {"node-c"}


@pytest.mark.parametrize("mutation", ["stale", "future", "wrong-target", "runtime", "auth", "dns",
                                     "handshake", "control", "degraded", "family", "missing-profile"])
def test_canonical_invalid_or_degraded_reports_do_not_count(liveness, mutation):
    helper, _live, path, _config, report, nodes = liveness
    profile = report["profiles"][0]
    if mutation == "stale":
        report["observed_at"] -= 1000
    elif mutation == "future":
        report["observed_at"] += 1000
    elif mutation == "wrong-target":
        report["target_identity"]["deployable_digest"] = "0" * 64
    elif mutation == "runtime":
        report["runtime"]["awg"] = "0.0.1"
    elif mutation == "auth":
        profile["authenticated_handshake"] = False
    elif mutation == "dns":
        profile["dns_through_tunnel"] = False
    elif mutation == "handshake":
        profile["fresh_handshake"] = False
    elif mutation == "control":
        report["control"]["verdict"] = "unknown"
    elif mutation == "degraded":
        profile["verdict"] = "throttled"
    elif mutation == "family":
        profile["family_results"]["ipv6"]["verdict"] = "throttled"
    else:
        report["profiles"] = []
    assert helper.healthy_survivors(path, nodes) == set()


def test_wrong_public_target_refuses_before_probe(rotation, liveness, monkeypatch):
    helper, live, path, config, _report, nodes = liveness
    config["sentinels"][0]["target"]["public_service_address_sha256"] = "0" * 64
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(live, "pull_report", lambda *_: pytest.fail("unbound probe"))
    with pytest.raises(rotation.RotationError, match="public-target"):
        helper.healthy_survivors(path, nodes)


def test_wrong_alias_refuses_before_probe(rotation, liveness, monkeypatch):
    helper, live, path, _config, _report, nodes = liveness
    nodes[0]["inventory_alias"] = "other"
    monkeypatch.setattr(live, "pull_report", lambda *_: pytest.fail("unbound probe"))
    with pytest.raises(rotation.RotationError, match="inventory-binding"):
        helper.healthy_survivors(path, nodes)


def test_missing_witness_is_not_a_positive(rotation, liveness, monkeypatch):
    helper, live, path, _config, _report, nodes = liveness
    monkeypatch.setattr(live, "pull_report", lambda *_: ("witness", "", "unavailable"))
    assert helper.healthy_survivors(path, nodes) == set()


def test_new_live_generation_is_revalidated_not_frozen(liveness):
    helper, _live, path, config, report, nodes = liveness
    assert helper.healthy_survivors(path, nodes) == {"node-c"}
    config["sentinels"][0]["target"]["deployable_digest"] = "e" * 64
    report["target_identity"]["deployable_digest"] = "e" * 64
    path.write_text(yaml.safe_dump(config))
    assert helper.healthy_survivors(path, nodes) == {"node-c"}


def test_actual_directory_sync_failure_fences_resume(rotation, plan, tmp_path, monkeypatch):
    with rotation.Journal(tmp_path, "rotation-a") as journal:
        state = rotation.initial_state(rotation.load_plan(plan))
        journal.write(state)
        state["in_flight"] = 0
        journal.write(state)
        previous = journal.path.read_bytes()
        calls = 0
        original = journal.sync_directory
        def failing_sync():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic directory sync failure after replace")
            original()
        monkeypatch.setattr(journal, "sync_directory", failing_sync)
        state.update(next_idx=1, completed=rotation.load_plan(plan)["rotations"][:1], in_flight=None)
        with pytest.raises(OSError):
            journal.write(state)
        assert journal.pending_path.read_bytes() == previous
    with pytest.raises(rotation.RotationError, match="publication-uncertain"):
        rotation.run_plan(plan, root=tmp_path, resume=True)


def test_execute_real_child_forces_real_mode_and_propagates_failure(rotation, tmp_path, monkeypatch):
    script = tmp_path / "scripts/blue-green.sh"
    script.parent.mkdir()
    output = tmp_path / "execution.json"
    script.write_text("#!/usr/bin/env python3\nimport json,os\n"
                      f"open({str(output)!r},'w').write(json.dumps({{k:os.environ[k] for k in "
                      "['PROVIDER','ENV','BLUE_ENV','GREEN_ENV','GREEN_ZONE','DRY_RUN','SOPS_FILE','GREEN_SOPS_FILE','BLUE_COHORT','GREEN_COHORT','DEVICE_MIGRATION_PLAN','DEVICE_MIGRATION_APPROVAL']}))\n")
    script.chmod(0o700)
    monkeypatch.setenv("DRY_RUN", "1")
    from test_blue_green_lifecycle import migration_inputs
    inputs = migration_inputs(tmp_path, tmp_path, tmp_path / "source.sops.yaml", blue="blue")
    entry = {"current": "upcloud:blue", "new_env": "green", "green_sops_file": inputs["GREEN_SOPS_FILE"],
             "migration_plan": inputs["DEVICE_MIGRATION_PLAN"], "migration_approval": inputs["DEVICE_MIGRATION_APPROVAL"]}
    with rotation.Journal(tmp_path, "rotation-a") as journal:
        rotation.execute_rotation(entry, tmp_path, journal.lock)
        assert json.loads(output.read_text()) == {"PROVIDER": "upcloud", "ENV": "blue", "BLUE_ENV": "blue",
                                                 "GREEN_ENV": "green", "GREEN_ZONE": "", "DRY_RUN": "0",
                                                 "SOPS_FILE": str(tmp_path / "source.sops.yaml"), "BLUE_COHORT": "fullstack",
                                                 "GREEN_COHORT": "device-full-tailnet", **inputs}
        script.write_text("#!/bin/sh\nexit 9\n")
        with pytest.raises(rotation.RotationError, match="rotation-failed"):
            rotation.execute_rotation(entry, tmp_path, journal.lock)


def test_audit_occurs_only_after_durable_success(rotation, plan, tmp_path, monkeypatch):
    events = []
    def audit(root, action, _plan, entry=None):
        state = json.loads(journal_path(root).read_text())
        assert state["in_flight"] is None and state["next_idx"] > 0
        events.append(action)
    monkeypatch.setattr(rotation, "audit", audit)
    assert run(rotation, plan, tmp_path, monkeypatch)[0] == 0
    assert events == ["fleet-rotate-step", "fleet-rotate-step", "fleet-rotate-complete"]


def test_source_cannot_masquerade_as_survivor(rotation, liveness, monkeypatch):
    helper, live, path, _config, _report, nodes = liveness
    inventory = Path(os.environ["FLEET_INVENTORY"])
    inventory.write_text(inventory.read_text().replace("[vpn]\n", "[vpn]\n"
                         "node-a provider=upcloud env=blue ansible_host=100.64.0.2 "
                         "vpn_service_address=192.0.2.9 ansible_user=deploy ansible_port=2223\n"))
    nodes.insert(0, {"current": "upcloud:blue", "inventory_alias": "node-a"})
    monkeypatch.setattr(live, "pull_report", lambda *_: pytest.fail("aliased survivor probe"))
    with pytest.raises(rotation.RotationError, match="distinct-targets"):
        helper.healthy_survivors(path, nodes, excluded=("node-a",))


def cli_fixture(tmp_path, plan, liveness):
    _helper, _live, _path, _config, report, _nodes = liveness
    inventory = Path(os.environ["FLEET_INVENTORY"])
    inventory.write_text(inventory.read_text().replace("[vpn]\n", "[vpn]\n"
                         "node-a provider=upcloud env=blue ansible_host=192.0.2.1 "
                         "ansible_user=deploy ansible_port=2223\n"))
    value = yaml.safe_load(plan.read_text())
    value["health"]["nodes"] = [value["health"]["nodes"][0], value["health"]["nodes"][2]]
    value["rotations"] = value["rotations"][:1]
    from test_blue_green_lifecycle import migration_inputs
    inputs = migration_inputs(tmp_path, tmp_path, tmp_path / "source.sops.yaml", blue="blue")
    value["rotations"][0].update(green_sops_file=inputs["GREEN_SOPS_FILE"],
                                  migration_plan=inputs["DEVICE_MIGRATION_PLAN"])
    plan.write_text(yaml.safe_dump(value))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ssh = bindir / "ssh"
    ssh.write_text(f"#!{sys.executable}\nimport json\nprint({json.dumps(report)!r})\n")
    ssh.chmod(0o700)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    audit = scripts / "audit-log.sh"
    audit.write_text("#!/bin/sh\nexit 0\n")
    audit.chmod(0o700)
    child = scripts / "blue-green.sh"
    program = (f"import sys; from pathlib import Path; sys.path.insert(0,{str(ROOT / 'scripts')!r}); "
               f"import fleet_rotation as f; f.ROOT=Path({str(tmp_path)!r}); "
               f"sys.exit(f.main(['--plan',{str(plan)!r}]))")
    environment = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"]}
    return child, program, environment


def test_cli_positive_execution_preserves_child_prompts_and_journal(plan, liveness, tmp_path):
    child, program, environment = cli_fixture(tmp_path, plan, liveness)
    outcome = tmp_path / "child-answer"
    child.write_text(f"#!/bin/sh\nread -r answer\nprintf '%s' \"$answer\" > '{outcome}'\n")
    child.chmod(0o700)
    result = subprocess.run([sys.executable, "-c", program], input="yes\nchild-confirmation\n",
                            text=True, capture_output=True, env=environment, timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert outcome.read_text() == "child-confirmation"
    state = json.loads(journal_path(tmp_path).read_text())
    assert state["next_idx"] == 1 and state["in_flight"] is None


def test_cli_signal_retains_inflight_and_reaps_child(plan, liveness, tmp_path):
    child, program, environment = cli_fixture(tmp_path, plan, liveness)
    child_pid = tmp_path / "child-pid"
    child.write_text(f"#!{sys.executable}\nimport os,time\n"
                     f"open({str(child_pid)!r},'w').write(str(os.getpid()))\ntime.sleep(60)\n")
    child.chmod(0o700)
    process = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    try:
        process.stdin.write("yes\n")
        process.stdin.flush()
        deadline = time.monotonic() + 10
        while not child_pid.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert child_pid.exists(), process.poll()
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 128 + signal.SIGTERM, stdout + stderr
        assert json.loads(journal_path(tmp_path).read_text())["in_flight"] == 0
        with pytest.raises(ProcessLookupError):
            os.kill(int(child_pid.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_canonical_optional_awg_variants_can_be_null(liveness):
    helper, _live, path, _config, report, nodes = liveness
    report["profiles"][0]["variants"] = None
    assert helper.healthy_survivors(path, nodes) == {"node-c"}
