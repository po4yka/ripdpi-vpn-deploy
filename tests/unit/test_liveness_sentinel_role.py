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


def test_probe_prefers_the_role_prefix_and_falls_back_to_path(tmp_path, monkeypatch):
    probe = load("vpn_protocol_liveness", ROOT / "scripts/vpn-protocol-liveness.py")
    assert probe.ENGINE_BIN == Path("/opt/ripdpi-liveness-sentinel/bin")
    assert probe.engine("xray") == "xray"
    (tmp_path / "xray").write_text("#!/bin/sh\n")
    monkeypatch.setattr(probe, "ENGINE_BIN", tmp_path)
    assert probe.engine("xray") == "xray"  # not executable yet
    (tmp_path / "xray").chmod(0o755)
    assert probe.engine("xray") == str(tmp_path / "xray")
    assert probe.engine("sing-box") == "sing-box"


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
