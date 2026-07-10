from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "hysteria-gecko-evidence.py"


def phase(name: str, obfs_type: str, successes: int, *, invalid_failures: int = 0) -> dict:
    starts = {"salamander-a1": "2026-07-10T00:00:00Z", "gecko-b": "2026-07-10T01:00:00Z", "salamander-a2": "2026-07-10T02:00:00Z"}
    finishes = {"salamander-a1": "2026-07-10T00:10:00Z", "gecko-b": "2026-07-10T01:10:00Z", "salamander-a2": "2026-07-10T02:10:00Z"}
    return {"schema_version": 1, "phase": name, "obfs_type": obfs_type, "scope": "udp-443-salamander-1200", "vantage_id": "filtered-cgnat-a", "canary_id": "canary-a", "client_version": "v2.9.2", "client_sha256": "a" * 64, "canary_endpoint_hmac_sha256": "b" * 64, "control_endpoint_hmac_sha256": "c" * 64, "target_endpoint_hmac_sha256": "d" * 64, "client_transport_hmac_sha256": "e" * 64, "obfs_password_hmac_sha256": "9" * 64, "client_config_hmac_sha256": ("f" if obfs_type == "salamander" else "0") * 64, "gecko_min_packet_size": 512 if obfs_type == "gecko" else None, "gecko_max_packet_size": 1200 if obfs_type == "gecko" else None, "started_at": starts[name], "finished_at": finishes[name], "attempts": 10, "hysteria_successes": successes, "control_successes": 9, "network_failures": 10 - successes - invalid_failures, "invalid_failures": invalid_failures, "failure_classes": {"network": 10 - successes - invalid_failures, "authentication": invalid_failures, "tls": 0, "malformed_config": 0, "local_process": 0}, "latency_ms": {"min": 20, "median": 30, "max": 40}}


def run_evaluate(tmp_path: Path, docs: list[dict]) -> tuple[subprocess.CompletedProcess[str], Path]:
    inputs = []
    for index, doc in enumerate(docs):
        path = tmp_path / f"phase-{index}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        inputs.append(path)
    output = tmp_path / "evidence.json"
    proc = subprocess.run([sys.executable, str(TOOL), "evaluate", *(str(path) for path in inputs), "--output", str(output)], capture_output=True, text=True)
    return proc, output


def test_evaluate_confirms_the_required_aba_pattern(tmp_path: Path) -> None:
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 2), phase("gecko-b", "gecko", 8), phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["verdict"] == "confirmed"
    assert report["reason_codes"] == []


def test_evaluate_rejects_invalid_failures_and_identity_drift(tmp_path: Path) -> None:
    invalid = phase("salamander-a1", "salamander", 1, invalid_failures=1)
    proc, output = run_evaluate(tmp_path, [invalid, phase("gecko-b", "gecko", 9), phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 1
    assert "invalid_failure_class" in json.loads(output.read_text(encoding="utf-8"))["reason_codes"]
    gecko = phase("gecko-b", "gecko", 9)
    gecko["vantage_id"] = "filtered-cgnat-b"
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 1), gecko, phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 1
    assert "identity_mismatch" in json.loads(output.read_text(encoding="utf-8"))["reason_codes"]

    gecko = phase("gecko-b", "gecko", 9)
    gecko["obfs_password_hmac_sha256"] = "8" * 64
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 1), gecko, phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 1
    assert "identity_mismatch" in json.loads(output.read_text(encoding="utf-8"))["reason_codes"]

    a2 = phase("salamander-a2", "salamander", 1)
    a2["client_config_hmac_sha256"] = "7" * 64
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 1), phase("gecko-b", "gecko", 9), a2])
    assert proc.returncode == 1
    assert "salamander_config_mismatch" in json.loads(output.read_text(encoding="utf-8"))["reason_codes"]

    gecko = phase("gecko-b", "gecko", 9)
    gecko["control_endpoint_hmac_sha256"] = "9" * 64
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 1), gecko, phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 1
    assert "identity_mismatch" in json.loads(output.read_text(encoding="utf-8"))["reason_codes"]


def test_validate_binds_report_to_scope_and_sha256(tmp_path: Path) -> None:
    proc, output = run_evaluate(tmp_path, [phase("salamander-a1", "salamander", 1), phase("gecko-b", "gecko", 9), phase("salamander-a2", "salamander", 1)])
    assert proc.returncode == 0
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    valid = subprocess.run([sys.executable, str(TOOL), "validate", str(output), "--scope", "udp-443-salamander-1200", "--sha256", digest, "--gecko-min-packet-size", "512", "--gecko-max-packet-size", "1200"], capture_output=True, text=True)
    invalid = subprocess.run([sys.executable, str(TOOL), "validate", str(output), "--scope", "another-scope", "--sha256", digest], capture_output=True, text=True)
    wrong_bounds = subprocess.run([sys.executable, str(TOOL), "validate", str(output), "--scope", "udp-443-salamander-1200", "--sha256", digest, "--gecko-min-packet-size", "513", "--gecko-max-packet-size", "1200"], capture_output=True, text=True)
    assert valid.returncode == 0, valid.stderr
    assert invalid.returncode == 1
    assert wrong_bounds.returncode == 1


def test_client_config_identity_requires_native_password_and_gecko_bounds(tmp_path: Path) -> None:
    inspect_client_config = runpy.run_path(str(TOOL))["inspect_client_config"]
    identity_key = b"test-identity-key-that-is-at-least-32-bytes"
    salamander = tmp_path / "salamander.yaml"
    salamander.write_text("server: canary.invalid:443\nobfs:\n  type: salamander\n  salamander:\n    password: shared-secret\n", encoding="utf-8")
    gecko = tmp_path / "gecko.yaml"
    gecko.write_text("server: canary.invalid:443\nobfs:\n  type: gecko\n  gecko:\n    password: shared-secret\n    minPacketSize: 512\n    maxPacketSize: 1200\n", encoding="utf-8")

    salamander_identity = inspect_client_config(salamander, "salamander", identity_key)
    gecko_identity = inspect_client_config(gecko, "gecko", identity_key)

    assert salamander_identity["obfs_password_hmac_sha256"] == gecko_identity["obfs_password_hmac_sha256"]
    assert gecko_identity["gecko_min_packet_size"] == 512
    assert gecko_identity["gecko_max_packet_size"] == 1200


def test_validate_recomputes_verdict_instead_of_trusting_confirmed_string(tmp_path: Path) -> None:
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps({"schema_version": 1, "verdict": "confirmed", "reason_codes": [], "scope": "scope", "vantage_id": "vantage", "canary_id": "canary", "client_version": "v2.9.2", "client_sha256": "a" * 64, "canary_endpoint_hmac_sha256": "b" * 64, "control_endpoint_hmac_sha256": "c" * 64, "target_endpoint_hmac_sha256": "d" * 64, "client_transport_hmac_sha256": "e" * 64, "obfs_password_hmac_sha256": "f" * 64, "gecko_min_packet_size": 512, "gecko_max_packet_size": 1200, "phases": []}), encoding="utf-8")
    digest = hashlib.sha256(forged.read_bytes()).hexdigest()

    result = subprocess.run([sys.executable, str(TOOL), "validate", str(forged), "--scope", "scope", "--sha256", digest], capture_output=True, text=True)

    assert result.returncode == 1
    assert "invalid_phases" in result.stderr


def test_credential_rotation_runs_hysteria_preflight_before_render() -> None:
    playbook = (ROOT / "ansible" / "playbooks" / "rotate-credentials.yml").read_text(encoding="utf-8")

    preflight = playbook.index("tasks_from: preflight.yml")
    assert preflight < playbook.index("- name: Re-render Xray config")
    assert preflight < playbook.index("- name: Re-render Hysteria config")
