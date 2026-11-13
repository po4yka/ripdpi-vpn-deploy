"""The liveness-sentinel role, the disposable executor and the native probe agree on one set of engine pins and one prefix."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
ROLE = ROOT / "ansible/roles/liveness-sentinel"
PINS = ROOT / "contract/liveness-runtime-pins.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disposable_flow_and_role_read_the_same_pin_file_and_no_digest_is_duplicated():
    pins = json.loads(PINS.read_text())
    disposable = load("provision_disposable", ROOT / "scripts/provision-disposable-liveness-runtime.py")
    for name, engine in pins["engines"].items():
        for arch, item in engine["archives"].items():
            assert disposable.ENGINES[name]["archives"][arch] == (item["name"], item["sha256"])
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
    assert "contract/liveness-runtime-pins.json" in (ROLE / "defaults/main.yml").read_text()
    for path in [*ROLE.rglob("*.yml"), ROOT / "scripts/provision-disposable-liveness-runtime.py"]:
        text = path.read_text()
        for engine in pins["engines"].values():
            for item in engine["archives"].values():
                assert item["sha256"] not in text, path


def test_probe_uses_the_role_prefix_exclusively_when_it_exists(tmp_path, monkeypatch):
    probe = load("vpn_protocol_liveness", ROOT / "scripts/vpn-protocol-liveness.py")
    assert probe.ENGINE_BIN == Path("/opt/ripdpi-liveness-sentinel/bin")
    monkeypatch.setattr(probe, "ENGINE_BIN", tmp_path / "absent")
    assert probe.engine("xray") == "xray"  # no role directory: legacy PATH lookup
    monkeypatch.setattr(probe, "ENGINE_BIN", tmp_path)
    # The directory exists but holds no engine: never fall back to another PATH binary.
    assert probe.engine("xray") == str(tmp_path / "xray")
    assert probe.command_version([probe.engine("sing-box"), "version"]) == "missing"
    (tmp_path / "xray").write_text("#!/bin/sh\necho Xray 1.2.3\n")
    (tmp_path / "xray").chmod(0o755)
    assert probe.xray_version() == "1.2.3"


def test_role_prefix_matches_the_probe_and_the_live_node_b_is_the_only_enabled_host_profile():
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    probe = load("vpn_protocol_liveness_prefix", ROOT / "scripts/vpn-protocol-liveness.py")
    assert Path(defaults["liveness_sentinel_prefix"], "bin") == probe.ENGINE_BIN
    enabled = sorted(
        path.name
        for path in (ROOT / "ansible/group_vars").glob("*.yml")
        if (yaml.safe_load(path.read_text()) or {}).get("vpn", {}).get("enable_liveness_sentinel") is True
    )
    assert enabled == ["vpn-split-hop-egress-live.yml"]


def _tasks(name: str) -> list[dict]:
    return yaml.safe_load((ROLE / "tasks" / name).read_text())


def _index(tasks: list[dict], needle: str) -> int:
    return next(i for i, task in enumerate(tasks) if needle in yaml.safe_dump(task))


def test_awg_admission_precedes_every_host_change_and_uses_the_site_predicate():
    enable = _tasks("enable.yml")
    assert _index(enable, "awg-preflight.yml") < _index(enable, "ansible.builtin.apt")
    preflight = _tasks("awg-preflight.yml")
    describe = preflight[_index(preflight, "describe")]
    assert describe["check_mode"] is False and describe["delegate_to"] == "localhost"
    # Same enablement predicate as the amneziawg import in site.yml, which defaults to enabled.
    guard = yaml.safe_dump(enable[_index(enable, "family amneziawg")])
    assert "default(true)" in guard and "vpn_subscription_only" in guard
    assert "vpn.enable_amneziawg | default(true)" in (ROOT / "ansible/playbooks/site.yml").read_text()


def test_awg_task_file_admits_ancestry_and_validates_the_toolchain_id_before_use():
    awg = _tasks("awg.yml")
    assert _index(awg, "runtime-release/tasks/consumer-authority.yml") < _index(awg, "Create the content-addressed correction directory")
    assert _index(awg, "toolchainId | default('') is match") < _index(awg, "/bin/awg")


def test_engine_digest_is_checked_by_a_task_that_is_not_retried():
    block = next(task for task in _tasks("engine.yml") if "block" in task)["block"]
    download = block[_index(block, "get_url")]
    assert "checksum" not in download["ansible.builtin.get_url"]
    assert download["retries"] == 5
    check = block[_index(block, "differs from its pinned digest")]
    assert "retries" not in check and "until" not in check
