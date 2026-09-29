"""Fixed, resumable staging observability acceptance coordinator."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "observability-staging-acceptance.py"
CLEANUP_SCRIPT = ROOT / "scripts" / "observability-staging-cleanup.py"


def _load():
    spec = importlib.util.spec_from_file_location("observability_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_cleanup():
    spec = importlib.util.spec_from_file_location(
        "observability_staging_cleanup_contract", CLEANUP_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.fixture
def acceptance(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    inventory = root / "inventory.ini"
    inventory.write_text(
        """[vpn]
canary-a ansible_host=canary.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=vpn
[vpn-observability-control]
control-a ansible_host=control.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=control-plane
[vpn-observability-deadman]
deadman-a ansible_host=deadman.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=deadman
""",
        encoding="utf-8",
    )
    inventory.chmod(0o600)
    known_hosts = root / "known_hosts"
    known_hosts.write_text("fixture.invalid ssh-ed25519 AAAA\n", encoding="utf-8")
    known_hosts.chmod(0o600)
    inputs = {}
    for name in (
        "control_plane_vars",
        "control_plane_secrets",
        "deadman_vars",
        "deadman_secrets",
        "canary_vars",
        "canary_secrets",
        "rollback_manifest",
        "hetzner_binding",
        "primary_old_token",
        "secondary_old_token",
        "observations",
    ):
        value: object = {"schema_version": 1}
        if name.endswith("old_token"):
            value = "123456:fixture-token"
        if name == "observations":
            value = {
                "schema_version": 1,
                "rows": {
                    step: {
                        "observed": False,
                        "started_at": None,
                        "observed_at": None,
                        "receipt_sha256": None,
                    }
                    for step in _load().OBSERVATION_STEPS
                },
            }
        if name == "hetzner_binding":
            value = {
                "schema_version": 1,
                "provider": "hetzner",
                "environment": "staging",
                "account_id": "c" * 64,
                "state_sha256": "d" * 64,
                "terraform_address": "hcloud_server.vpn",
                "server_id": 123,
            }
        inputs[name] = str(_private(root / f"{name}.json", value))
    approvals = {}
    for step in _load().STEPS:
        approvals[step] = str(
            _private(
                root / f"approval-{step}.json",
                {
                    "schema_version": 1,
                    "task_id": "MON-1790650904289505",
                    "change": "staging-observability-telegram-acceptance",
                    "action": step,
                    "target": _load().STEP_TARGETS[step],
                    "restore_action": _load().STEP_RESTORES[step],
                    "approved": True,
                    "approved_at": "2026-09-29T00:00:00Z",
                    "expires_at": "2030-09-29T00:00:00Z",
                    "deadline_seconds": _load().STEP_MIN_DEADLINES[step],
                    "cancellation_condition": "restore-and-stop",
                },
            )
        )
    manifest = {
        "schema_version": 1,
        "task_id": "MON-1790650904289505",
        "change": "staging-observability-telegram-acceptance",
        "environment": "staging",
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "inventory": str(inventory),
        "known_hosts": str(known_hosts),
        "hosts": {
            "canary": "canary-a",
            "control-plane": "control-a",
            "deadman": "deadman-a",
        },
        "inputs": inputs,
        "approvals": approvals,
    }
    manifest_path = _private(root / "manifest.json", manifest)
    journal = root / "journal.json"
    receipts = root / "receipts"
    receipts.mkdir(mode=0o700)
    return {
        "root": root,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "journal": journal,
        "receipts": receipts,
    }


def test_manifest_is_staging_only_exact_and_private(acceptance) -> None:
    module = _load()
    value, digest = module.load_manifest(acceptance["manifest_path"])

    assert value["environment"] == "staging"
    assert value["hosts"] == {
        "canary": "canary-a",
        "control-plane": "control-a",
        "deadman": "deadman-a",
    }
    assert len(digest) == 64

    value["environment"] = "prod"
    _private(acceptance["manifest_path"], value)
    with pytest.raises(module.AcceptanceError, match="manifest rejected"):
        module.load_manifest(acceptance["manifest_path"])


def test_public_or_symlinked_manifest_refuses_before_executor(acceptance) -> None:
    module = _load()
    acceptance["manifest_path"].chmod(0o644)
    with pytest.raises(module.AcceptanceError, match="private manifest required"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: pytest.fail("executor called"),
        )


def test_advance_runs_only_the_fixed_next_step_and_publishes_redacted_receipt(
    acceptance,
) -> None:
    module = _load()
    calls: list[str] = []

    result = module.advance(
        acceptance["manifest_path"],
        acceptance["journal"],
        acceptance["receipts"],
        executor=lambda step, *_: calls.append(step) or "observed",
    )

    assert calls == [module.STEPS[0]]
    assert result["completed_step"] == module.STEPS[0]
    journal = json.loads(acceptance["journal"].read_text())
    assert journal["completed_checks"] == [module.STEPS[0]]
    assert journal["current_step"] is None
    receipt = json.loads(
        module._receipt_path(acceptance["receipts"], module.STEPS[0]).read_text()
    )
    assert set(receipt) == {
        "schema_version",
        "action",
        "result",
        "started_at",
        "completed_at",
        "source_revision",
        "deployable_digest",
    }
    serialized = json.dumps(receipt)
    assert "invalid" not in serialized
    assert "token" not in serialized
    assert "ansible_host" not in serialized
    assert stat.S_IMODE(acceptance["journal"].stat().st_mode) == 0o600


def test_running_journal_recovers_fixed_step_and_stops(acceptance) -> None:
    module = _load()
    manifest, digest = module.load_manifest(acceptance["manifest_path"])
    journal = module.new_journal(manifest, digest)
    journal["current_step"] = {
        "name": "control-service-loss",
        "started_at": "2026-09-29T01:00:00Z",
    }
    _private(acceptance["journal"], journal)
    recovered: list[tuple[str, str]] = []

    with pytest.raises(module.AcceptanceError, match="interrupted step restored"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: pytest.fail("forward executor called"),
            restorer=lambda step, restore, *_: recovered.append((step, restore)),
        )

    assert recovered == [
        ("control-service-loss", module.STEP_RESTORES["control-service-loss"])
    ]
    stored = json.loads(acceptance["journal"].read_text())
    assert stored["status"] == "incomplete"
    assert stored["current_step"] is None


def test_completed_receipt_reconciles_interrupted_journal_without_repeating_action(
    acceptance,
) -> None:
    module = _load()
    module.advance(
        acceptance["manifest_path"],
        acceptance["journal"],
        acceptance["receipts"],
        executor=lambda *_: "observed",
    )
    manifest, digest = module.load_manifest(acceptance["manifest_path"])
    journal = module.new_journal(manifest, digest)
    journal["current_step"] = {
        "name": module.STEPS[0],
        "started_at": "2026-09-29T01:00:00Z",
    }
    _private(acceptance["journal"], journal)

    result = module.advance(
        acceptance["manifest_path"],
        acceptance["journal"],
        acceptance["receipts"],
        executor=lambda *_: pytest.fail("forward executor called"),
        restorer=lambda *_: pytest.fail("restorer called"),
    )

    assert result["completed_step"] == module.STEPS[0]
    assert json.loads(acceptance["journal"].read_text())["completed_checks"] == [
        module.STEPS[0]
    ]


def test_approval_drift_or_short_deadline_refuses_before_executor(acceptance) -> None:
    module = _load()
    approval_path = Path(acceptance["manifest"]["approvals"][module.STEPS[0]])
    approval = json.loads(approval_path.read_text())
    approval["target"] = "other-host"
    approval["deadline_seconds"] = 1
    _private(approval_path, approval)

    with pytest.raises(module.AcceptanceError, match="approval rejected"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: pytest.fail("executor called"),
        )


def test_terminal_journal_matches_cleanup_contract(acceptance) -> None:
    module = _load()
    observations_path = Path(acceptance["manifest"]["inputs"]["observations"])

    for step in module.STEPS:
        advance = lambda *_: "observed"
        if step in module.OBSERVATION_STEPS:
            with pytest.raises(
                module.AcceptanceError, match="human observation required"
            ):
                module.advance(
                    acceptance["manifest_path"],
                    acceptance["journal"],
                    acceptance["receipts"],
                    executor=advance,
                )
            journal = json.loads(acceptance["journal"].read_text())
            receipt_path = module._receipt_path(acceptance["receipts"], step)
            receipt = json.loads(receipt_path.read_text())
            observations = json.loads(observations_path.read_text())
            observations["rows"][step] = {
                "observed": True,
                "started_at": journal["current_step"]["started_at"],
                "observed_at": receipt["completed_at"],
                "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            }
            _private(observations_path, observations)
            advance = lambda *_: pytest.fail("completed row was re-executed")
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=advance,
            restorer=lambda *_: pytest.fail("completed row was restored"),
        )

    journal = json.loads(acceptance["journal"].read_text())
    assert journal["status"] == "ready-for-cleanup"
    assert journal["components_removed"] is True
    assert journal["completed_checks"] == sorted(module.ACCEPTANCE_CHECKS)
    assert journal["human_observations"] == {
        "primary_lifecycle": True,
        "secondary_lifecycle": True,
        "deadman_loss_primary": True,
        "primary_authority_loss_secondary": True,
    }
    assert set(journal) == {
        "schema_version",
        "task_id",
        "change",
        "source_revision",
        "deployable_digest",
        "status",
        "completed_checks",
        "human_observations",
        "components_removed",
    }
    _load_cleanup().validate_acceptance_journal(journal)


def test_debug_environment_refuses_before_private_input(
    monkeypatch, acceptance
) -> None:
    module = _load()
    monkeypatch.setenv("ANSIBLE_DEBUG", "true")
    with pytest.raises(module.AcceptanceError, match="debug output forbidden"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: pytest.fail("executor called"),
        )


@pytest.mark.parametrize(
    "porcelain", (b" M scripts/modified.py\0", b"?? scripts/unreviewed.py\0")
)
def test_dirty_source_refuses_before_live_action(
    monkeypatch, acceptance, porcelain
) -> None:
    module = _load()

    def dirty_run(argv, **_kwargs):
        if argv[0].endswith("deploy-source-identity.sh"):
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{'a' * 40} {'b' * 64}\n"
            )
        if argv[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(argv, 0, stdout=porcelain)
        return subprocess.CompletedProcess(argv, 0, stdout="a" * 40 + "\n")

    monkeypatch.setattr(module.subprocess, "run", dirty_run)
    with pytest.raises(module.AcceptanceError, match="clean protected-main source"):
        module._source_identity(acceptance["manifest"])


def test_critical_lifecycle_is_fixed_to_real_interval_and_primary_route() -> None:
    module = _load()
    source = module._critical_lifecycle_program().decode("utf-8")

    assert '"severity":"critical"' in source
    assert '"name":"telegram-primary"' in source
    assert "time.monotonic() + 3700" in source
    assert 'resolved["endsAt"]' in source


def test_fault_evidence_programs_require_delivery_and_fresh_recovery() -> None:
    module = _load()
    firing = module._deadman_evidence_program(
        incident=True,
        delivery="firing",
        wait_seconds=600,
        require_advancing=False,
    ).decode()
    recovery = module._deadman_evidence_program(
        incident=False,
        delivery="recovery",
        wait_seconds=300,
        require_advancing=True,
    ).decode()
    primary = module._primary_alert_evidence_program(
        "ObservabilityDeadmanReverseMissing", active=True, wait_seconds=600
    ).decode()

    assert 'value.get("incident") is True' in firing
    assert "value.get(\"last_delivery\")=='firing'" in firing
    assert 'second["last_pulse"]<=first' in recovery
    assert 'item.get("receivers")==[{"name":"telegram-primary"}]' in primary


def test_degraded_status_cannot_credit_rotation(monkeypatch, acceptance) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_operator",
        lambda *_args, **_kwargs: {"state": "degraded"},
    )
    with pytest.raises(module.AcceptanceError, match="component recovery rejected"):
        module._require_healthy(acceptance["manifest"], "control-plane")


def test_agent_operator_uses_canary_inputs(monkeypatch, acceptance) -> None:
    module = _load()
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "schema_version": 1,
                    "component": "agent",
                    "host": "canary-a",
                    "state": "rotated",
                    "controller_source_revision": "a" * 40,
                    "controller_deployable_digest": "b" * 64,
                }
            ).encode(),
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module._operator(acceptance["manifest"], "rotate", "agent", confirm=True)

    argv = calls[0]
    assert argv[argv.index("--secrets") + 1].endswith("canary_secrets.json")
    assert argv[argv.index("--vars") + 1].endswith("canary_vars.json")
    assert "--confirm" in argv


def test_hetzner_fault_refuses_server_id_not_bound_to_staging_state(
    monkeypatch, acceptance
) -> None:
    module = _load()
    token = "t" * 24
    binding_path = Path(acceptance["manifest"]["inputs"]["hetzner_binding"])
    binding = json.loads(binding_path.read_text())
    state = {
        "resources": [
            {
                "mode": "managed",
                "type": "hcloud_server",
                "name": "vpn",
                "instances": [{"attributes": {"id": 999}}],
            }
        ]
    }
    state_raw = json.dumps(state, sort_keys=True).encode("utf-8")
    binding["account_id"] = hashlib.sha256(
        b"hcloud-account-binding\0" + token.encode()
    ).hexdigest()
    binding["state_sha256"] = hashlib.sha256(state_raw).hexdigest()
    _private(binding_path, binding)
    monkeypatch.setenv("HCLOUD_TOKEN", token)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["terraform-env.sh"], 0, stdout=state_raw
        ),
    )

    with pytest.raises(module.AcceptanceError, match="provider binding rejected"):
        module._hetzner_action(acceptance["manifest"], "poweroff")


def test_human_observation_is_required_for_live_rows(acceptance) -> None:
    module = _load()

    module.advance(
        acceptance["manifest_path"],
        acceptance["journal"],
        acceptance["receipts"],
        executor=lambda *_: "observed",
    )
    with pytest.raises(module.AcceptanceError, match="human observation required"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: "observed",
        )

    journal = json.loads(acceptance["journal"].read_text())
    assert journal["status"] == "active"
    assert journal["completed_checks"] == ["fresh-metrics"]
    assert journal["current_step"]["name"] == "primary-lifecycle"
    assert module._receipt_path(acceptance["receipts"], "primary-lifecycle").exists()


def test_human_observation_must_bind_current_row_start(acceptance) -> None:
    module = _load()
    path = Path(acceptance["manifest"]["inputs"]["observations"])
    value = json.loads(path.read_text())
    value["rows"]["primary-lifecycle"] = {
        "observed": True,
        "started_at": "2026-09-29T01:00:00Z",
        "observed_at": "2026-09-29T01:01:00Z",
        "receipt_sha256": "e" * 64,
    }
    _private(path, value)

    with pytest.raises(module.AcceptanceError, match="human observation required"):
        module._observations(
            acceptance["manifest"],
            step="primary-lifecycle",
            started_at="2026-09-29T02:00:00Z",
            receipt_sha256="e" * 64,
            completed_at="2026-09-29T01:00:30Z",
        )


def test_makefile_exposes_one_literal_staging_acceptance_target() -> None:
    source = (ROOT / "Makefile").read_text()
    assert "observability-staging-acceptance:" in source
    block = source[source.index("observability-staging-acceptance:") :]
    block = block[: block.index("\n\n")]
    assert "scripts/observability-staging-acceptance.py advance" in block
    assert '"$${OBSERVABILITY_STAGING_ACCEPTANCE_MANIFEST_LITERAL}"' in block
    assert '"$${OBSERVABILITY_STAGING_ACCEPTANCE_JOURNAL_LITERAL}"' in block
    assert '"$${OBSERVABILITY_STAGING_ACCEPTANCE_RECEIPTS_LITERAL}"' in block
    assert "--confirm" in block
