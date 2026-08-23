"""Verdict matrix for scripts/client-drift.py (REQ-DRIFT-CHECK).

The identity computation shells out to git and Terraform; tests inject
fakes for both and exercise the verdict logic plus CLI exit codes.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "client-drift.py"


@pytest.fixture()
def drift():
    spec = importlib.util.spec_from_file_location("client_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(source: str, outputs: str, hosts=None) -> dict:
    return {
        "status": "delivered",
        "hosts": hosts if hosts is not None else ["upcloud:prod"],
        "last_payload_identity": {"source": source, "outputs": outputs},
    }


def test_current_when_identity_matches(drift, monkeypatch):
    monkeypatch.setattr(drift, "_source_digest", lambda: "a" * 64)
    monkeypatch.setattr(drift, "_outputs_digest", lambda hosts: "b" * 64)
    monkeypatch.setattr(drift, "_registry_entry", lambda c: _entry("a" * 64, "b" * 64))
    assert drift._verdict("phone") == (
        "current",
        "payload identity matches the last delivery",
    )


def test_stale_when_outputs_change(drift, monkeypatch):
    monkeypatch.setattr(drift, "_source_digest", lambda: "a" * 64)
    monkeypatch.setattr(drift, "_outputs_digest", lambda hosts: "c" * 64)
    monkeypatch.setattr(drift, "_registry_entry", lambda c: _entry("a" * 64, "b" * 64))
    verdict, detail = drift._verdict("phone")
    assert verdict == "stale"
    assert "outputs" in detail


def test_stale_when_source_changes(drift, monkeypatch):
    monkeypatch.setattr(drift, "_source_digest", lambda: "d" * 64)
    monkeypatch.setattr(drift, "_outputs_digest", lambda hosts: "b" * 64)
    monkeypatch.setattr(drift, "_registry_entry", lambda c: _entry("a" * 64, "b" * 64))
    verdict, detail = drift._verdict("phone")
    assert verdict == "stale"
    assert "source" in detail


def test_unknown_without_registry_entry(drift, monkeypatch):
    monkeypatch.setattr(drift, "_registry_entry", lambda c: None)
    verdict, detail = drift._verdict("ghost")
    assert verdict == "unknown"
    assert "no client_registry entry" in detail


def test_unknown_without_recorded_delivery(drift, monkeypatch):
    monkeypatch.setattr(
        drift, "_registry_entry", lambda c: _entry("", "", hosts=[])
    )
    verdict, _ = drift._verdict("phone")
    assert verdict == "unknown"


def test_unknown_on_invalid_host_pair(drift, monkeypatch):
    monkeypatch.setattr(drift, "_source_digest", lambda: "a" * 64)
    monkeypatch.setattr(
        drift,
        "_registry_entry",
        lambda c: _entry("a" * 64, "b" * 64, hosts=["upcloud"]),
    )
    assert drift._verdict("phone")[0] == "unknown"


def test_cli_exit_codes(drift, monkeypatch, capsys):
    matrix = {"current": 0, "stale": 1, "unknown": 2}
    monkeypatch.setattr(sys, "argv", ["client-drift.py", "phone"])
    for expected_verdict in ("current", "stale", "unknown"):
        monkeypatch.setattr(
            drift,
            "_verdict",
            lambda c, v=expected_verdict: (v, "detail"),
        )
        assert drift.main() == matrix[expected_verdict]


def test_print_identity_output(tmp_path: Path) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--print-identity" in result.stdout
