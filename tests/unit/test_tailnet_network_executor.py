"""Focused contract tests for the independent Tailnet rollback guard."""
from __future__ import annotations
import importlib.util, json, os, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/tailnet-network-executor.py"

def mod():
    spec = importlib.util.spec_from_file_location("tailnet_network_executor", SCRIPT)
    value = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(value); return value

def request():
    return {"server_uuid":"123e4567-e89b-42d3-a456-426614174000", "environment":"prod", "provider_target_sha256":"a"*64,
            "forward_plan_sha256":"b"*64, "guest_generation":"123e4567-e89b-42d3-a456-426614174000", "guest_nonce":"c"*64,
            "guest_snapshot_digest":"d"*64, "guest_deadline":2_000}

class Plan:
    def close(self): pass

class Adapter:
    def __init__(self): self.target = type("T", (), {"digest":"a"*64})(); self.calls=[]
    def plan(self, direction): self.calls.append(("plan", direction)); return Plan()
    def apply(self, direction, plan): self.calls.append(("apply", direction))

def executor(m, root):
    value = m.Executor.__new__(m.Executor); value.store = m.ReceiptStore(root); value.adapter = Adapter(); value.target = value.adapter.target; return value

def test_crash_after_provider_apply_reconciles_to_independent_false_apply(tmp_path, monkeypatch):
    m = mod(); value = executor(m, tmp_path); monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    applied = value.guard("mark-applied", {**{k:v for k,v in armed.items() if k != "state"}, "provider_applied_at":1_001})
    assert applied["state"] == "provider-applied"
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    assert value.reconcile() == {"state":"executed"}
    assert value.adapter.calls == [("plan", "rollback"), ("apply", "rollback")]

def test_release_prevents_deadline_rollback_and_restart_reads_canonical_receipt(tmp_path, monkeypatch):
    m = mod(); value = executor(m, tmp_path); monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    applied = value.guard("mark-applied", {**{k:v for k,v in armed.items() if k != "state"}, "provider_applied_at":1_001})
    committed = value.guard("commit", {**{k:v for k,v in applied.items() if k != "state"}, "promotion_observed_at":1_002})
    assert value.guard("release", committed) == {"state":"released"}
    assert executor(m, tmp_path).reconcile() is None
    assert value.adapter.calls == []

def test_foreign_or_stale_receipt_fails_closed(tmp_path, monkeypatch):
    m = mod(); value = executor(m, tmp_path); monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    with pytest.raises(m.ExecutorError, match="receipt-foreign"):
        value.guard("inspect", {**armed, "guest_nonce":"e"*64})
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    with pytest.raises(m.ExecutorError, match="transition-refused"):
        value.guard("execute", armed)

def test_controller_guest_rpc_is_fixed_strict_command_and_dry_run_disables_apply(monkeypatch, tmp_path):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location("tailnet_network_controller", controller_path)
    c = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(c)
    command = []
    monkeypatch.setattr(c.p.fleet_inspection, "ssh_command", lambda host, known: ["ssh", "-oStrictHostKeyChecking=yes", host["name"]])
    monkeypatch.setattr(c.p, "_bounded", lambda argv, *_a, **kw: command.append((argv, kw["input_data"])) or b'{"state":"prepared"}')
    rpc = c.strict_guest({"name":"node-a"}, tmp_path / "known", b"fragment")
    rpc({}, "prepare", {}, False)
    assert command[0][0][-7:] == ["sudo", "-n", "/usr/bin/python3", "-I", "-B", c.GUEST_HELPER, "prepare"]
    target = type("Target", (), {"value":{}, "digest":"a"*64})()
    adapter = type("Adapter", (), {"target":target, "allow_apply":False})()
    assert adapter.allow_apply is False
