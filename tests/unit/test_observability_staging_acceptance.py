"""Fixed, resumable staging observability acceptance coordinator."""

from __future__ import annotations

import ast
import importlib.util
import hashlib
import json
from pathlib import Path
import ssl
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
        "candidate_control_plane_vars",
        "candidate_control_plane_secrets",
        "deadman_vars",
        "deadman_secrets",
        "canary_vars",
        "canary_secrets",
        "canary_old_generation",
        "rollback_manifest",
        "invalid_control_plane_vars",
        "silence_owner",
        "hetzner_binding",
        "primary_old_token",
        "secondary_old_token",
        "observations",
    ):
        value: object = {"schema_version": 1}
        if name.endswith("old_token"):
            value = "123456:fixture-token"
        if name == "canary_old_generation":
            value = {"schema_version": 1, "generation": "e" * 64}
        if name == "rollback_manifest":
            value = {
                "schema_version": 1,
                "host": "control-a",
                "component": "control-plane",
                "previous_generation": "f" * 64,
                "vars_sha256": "1" * 64,
                "secrets_sha256": "2" * 64,
            }
        if name == "candidate_control_plane_vars":
            value = {
                "observability_control_plane": {
                    "enabled": True,
                    "config_root": "/etc/observability-control-plane",
                    "ingress_port": 9443,
                    "prometheus_listen": "127.0.0.1:9090",
                    "remote_write_path_prefix": "/remote-write/v1/nodes",
                }
            }
        if name == "invalid_control_plane_vars":
            value = {
                "observability_control_plane": {
                    "enabled": True,
                    "config_root": "/etc/observability-control-plane",
                    "ingress_port": 9443,
                    "prometheus_listen": "0.0.0.0:9090",
                    "remote_write_path_prefix": "/remote-write/v1/nodes",
                }
            }
        if name == "silence_owner":
            value = {"schema_version": 1, "owner": "operator-a"}
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


def test_candidate_operator_uses_distinct_candidate_inputs(
    monkeypatch, acceptance
) -> None:
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
                    "component": "control-plane",
                    "host": "control-a",
                    "state": "rotated",
                    "controller_source_revision": "a" * 40,
                    "controller_deployable_digest": "b" * 64,
                }
            ).encode(),
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module._operator(
        acceptance["manifest"],
        "rotate",
        "control-plane",
        confirm=True,
        variables=acceptance["manifest"]["inputs"]["candidate_control_plane_vars"],
        secrets=acceptance["manifest"]["inputs"][
            "candidate_control_plane_secrets"
        ],
    )

    argv = calls[0]
    assert argv[argv.index("--vars") + 1].endswith("candidate_control_plane_vars.json")
    assert argv[argv.index("--secrets") + 1].endswith(
        "candidate_control_plane_secrets.json"
    )


def test_candidate_operator_requests_typed_role_guard_refusal(
    monkeypatch, acceptance
) -> None:
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
                    "component": "control-plane",
                    "host": "control-a",
                    "state": "role-guard-refused",
                    "controller_source_revision": "a" * 40,
                    "controller_deployable_digest": "b" * 64,
                }
            ).encode(),
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module._operator(
        acceptance["manifest"],
        "rotate",
        "control-plane",
        confirm=True,
        variables=acceptance["manifest"]["inputs"]["invalid_control_plane_vars"],
        secrets=acceptance["manifest"]["inputs"][
            "candidate_control_plane_secrets"
        ],
        expect_role_guard_refusal=True,
    )

    assert result["state"] == "role-guard-refused"
    assert "--expect-role-guard-refusal" in calls[0]


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

    preceding = module.ACCEPTANCE_CHECKS.index("primary-lifecycle")
    for _ in range(preceding):
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
    assert journal["completed_checks"] == list(module.ACCEPTANCE_CHECKS[:preceding])
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


def test_fixed_sequence_covers_required_matrix_before_human_and_cleanup_rows() -> None:
    module = _load()

    assert module.ACCEPTANCE_CHECKS[:6] == (
        "fresh-metrics",
        "ingestion-negative",
        "agent-wal",
        "staleness",
        "grouping-inhibition",
        "finite-silence",
    )
    assert module.ACCEPTANCE_CHECKS[-4:] == (
        "old-material-rejection",
        "invalid-candidate-refusal",
        "valid-candidate-activation",
        "control-plane-rollback",
    )
    assert module.STEPS[-1] == "component-removal"
    assert module.INPUT_KEYS >= {
        "canary_old_generation",
        "candidate_control_plane_vars",
        "candidate_control_plane_secrets",
        "invalid_control_plane_vars",
        "silence_owner",
    }
    assert module.STEP_RESTORES["agent-wal"] == "start-control-plane-ingress"
    assert (
        module.STEP_RESTORES["valid-candidate-activation"]
        == "restore-prior-control-plane-generation"
    )


def test_matrix_remote_programs_are_fixed_and_syntax_valid() -> None:
    module = _load()
    programs = {
        "ingestion": module._ingestion_negative_program(),
        "wal": module._wal_metrics_program(),
        "stale-inject": module._stale_producer_program("inject"),
        "stale-restore": module._stale_producer_program("restore"),
        "alerts": module._alert_evidence_program(
            exact=("ObservabilityWatchdogEvidenceStale",), wait_seconds=120
        ),
        "grouping": module._grouping_inhibition_program("canary-a"),
        "silence": module._finite_silence_program(
            "operator-a", "canary-a", "0" * 16
        ),
        "silence-restore": module._finite_silence_restore_program(
            "operator-a", "canary-a", "0" * 16
        ),
        "old-sender": module._old_sender_rejection_program("e" * 64),
        "generation": module._control_plane_generation_program(),
    }
    for name, program in programs.items():
        compile(program, f"<{name}>", "exec")

    ingestion = programs["ingestion"].decode()
    assert "rejected-cross-node" in ingestion
    assert 'http_rejected(parsed.path,method="GET"' in ingestion
    assert 'http_rejected("/api/v1/query"' in ingestion
    assert "transport_or_http_rejected(parsed.path,identity=False)" in ingestion
    assert "transport_or_http_rejected(parsed.path,tls=False)" in ingestion
    assert ingestion.index("valid=status(parsed.path)") < ingestion.index(
        "def http_rejected"
    )

    stale = programs["stale-inject"].decode()
    pending = stale.index('"phase":"pending"')
    stop_timer = stale.index('"stop","vpn-watchdog.timer"')
    holding = stale.index('"phase":"holding"', stop_timer)
    mutate = stale.index("os.utime(path", holding)
    assert pending < stop_timer < holding < mutate

    silence = programs["silence"].decode()
    assert "state\")!=\"suppressed\"" in silence
    assert "seconds=20000" in silence
    assert '"unknown":"value"' in silence
    assert "sender,silence" in silence
    assert "staging-finite-0000000000000000" in silence
    assert "gateway_silences" in programs["silence-restore"].decode()


@pytest.mark.parametrize("error", [OSError, ssl.SSLError, ConnectionResetError])
def test_negative_ingestion_transport_errors_are_rejections(error) -> None:
    module = _load()
    tree = ast.parse(module._ingestion_negative_program())
    rejected = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "transport_or_http_rejected"
    )
    namespace = {"ssl": ssl}
    exec(compile(ast.Module([rejected], type_ignores=[]), "<rejected>", "exec"), namespace)

    def fail(*_args, **_kwargs):
        raise error

    namespace["status"] = fail
    assert namespace["transport_or_http_rejected"]("/negative") is True


def test_authenticated_negative_ingestion_requires_explicit_http_rejection() -> None:
    module = _load()
    tree = ast.parse(module._ingestion_negative_program())
    rejected = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "http_rejected"
    )
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module([rejected], type_ignores=[]), "<http-rejected>", "exec"),
        namespace,
    )

    namespace["status"] = lambda *_args, **_kwargs: 403
    assert namespace["http_rejected"]("/negative") is True
    namespace["status"] = lambda *_args, **_kwargs: None
    assert namespace["http_rejected"]("/negative") is False
    namespace["status"] = lambda *_args, **_kwargs: 204
    assert namespace["http_rejected"]("/negative") is False

    def fail(*_args, **_kwargs):
        raise ConnectionResetError

    namespace["status"] = fail
    with pytest.raises(ConnectionResetError):
        namespace["http_rejected"]("/negative")


def test_positive_ingestion_write_is_not_wrapped_as_negative_probe() -> None:
    module = _load()
    tree = ast.parse(module._ingestion_negative_program())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "valid" for target in node.targets)
    )

    assert isinstance(assignment.value, ast.Call)
    assert isinstance(assignment.value.func, ast.Name)
    assert assignment.value.func.id == "status"


def test_staleness_fault_is_held_through_independent_evidence_then_restored(
    monkeypatch, acceptance
) -> None:
    module = _load()
    calls: list[str] = []

    def remote(_manifest, role, program, _timeout):
        source = program.decode()
        if role == "canary" and "action='inject'" in source:
            calls.append("inject")
            return b'{"schema_version":1,"state":"held"}'
        if role == "control-plane" and "ObservabilityWatchdogEvidenceStale" in source:
            calls.append("stale-observed")
            return b'{"schema_version":1,"state":"verified"}'
        if role == "canary" and "action='restore'" in source:
            calls.append("stale-restored")
            return b'{"schema_version":1,"state":"restored"}'
        if role == "canary" and "action='stop'" in source:
            calls.append("agent-stopped")
            return b'{"schema_version":1,"state":"stoped"}'
        if role == "control-plane" and "ObservabilityExpectedTargetMissing" in source:
            calls.append("missing-observed")
            return b'{"schema_version":1,"state":"verified"}'
        if role == "canary" and "action='start'" in source:
            calls.append("agent-started")
            return b'{"schema_version":1,"state":"started"}'
        if role == "control-plane" and "vpn_observability_adapter" in source:
            calls.append("fresh")
            return b'{"schema_version":1,"state":"advancing"}'
        raise AssertionError("unexpected remote program")

    monkeypatch.setattr(module, "_remote", remote)
    monkeypatch.setattr(module, "_require_healthy", lambda *_args: None)

    assert (
        module._default_execute(
            "staleness", acceptance["manifest"], {"deadline_seconds": 700}
        )
        == "observed"
    )
    assert calls == [
        "inject",
        "stale-observed",
        "stale-restored",
        "agent-stopped",
        "missing-observed",
        "agent-started",
        "fresh",
    ]


def test_staleness_restores_durable_fault_when_evidence_fails(
    monkeypatch, acceptance
) -> None:
    module = _load()
    calls: list[str] = []

    def remote(_manifest, role, program, _timeout):
        source = program.decode()
        if role == "canary" and "action='inject'" in source:
            calls.append("inject")
            return b'{"schema_version":1,"state":"held"}'
        if role == "control-plane" and "ObservabilityWatchdogEvidenceStale" in source:
            calls.append("evidence-failed")
            raise module.AcceptanceError("bounded remote action failed")
        if role == "canary" and "action='restore'" in source:
            calls.append("restore")
            return b'{"schema_version":1,"state":"restored"}'
        raise AssertionError("unexpected remote program")

    monkeypatch.setattr(module, "_remote", remote)
    monkeypatch.setattr(module, "_require_healthy", lambda *_args: None)

    with pytest.raises(module.AcceptanceError, match="bounded remote action failed"):
        module._default_execute(
            "staleness", acceptance["manifest"], {"deadline_seconds": 700}
        )
    assert calls == ["inject", "evidence-failed", "restore"]


def test_interrupted_finite_silence_uses_approval_bound_authority_cleanup(
    monkeypatch, acceptance
) -> None:
    module = _load()
    manifest, digest = module.load_manifest(acceptance["manifest_path"])
    journal = module.new_journal(manifest, digest)
    journal["current_step"] = {
        "name": "finite-silence",
        "started_at": "2026-09-29T01:00:00Z",
    }
    _private(acceptance["journal"], journal)
    programs: list[str] = []

    def remote(_manifest, role, program, _timeout):
        assert role == "control-plane"
        programs.append(program.decode())
        return b'{"schema_version":1,"state":"restored"}'

    monkeypatch.setattr(module, "_remote", remote)

    with pytest.raises(module.AcceptanceError, match="interrupted step restored"):
        module.advance(
            acceptance["manifest_path"],
            acceptance["journal"],
            acceptance["receipts"],
            executor=lambda *_: pytest.fail("forward executor called"),
        )

    approval = json.loads(
        Path(acceptance["manifest"]["approvals"]["finite-silence"]).read_text()
    )
    binding = hashlib.sha256(module._canonical(approval)).hexdigest()[:16]
    assert len(programs) == 1
    assert f"reason='staging-finite-{binding}'" in programs[0]
    assert "row[\"owner\"]==owner" in programs[0]
    assert "row[\"scope\"]==scope" in programs[0]
    assert 'request("/v1/silences/"+identifier' in programs[0]


def test_old_material_row_rejects_sender_and_both_telegram_authorities(
    monkeypatch, acceptance
) -> None:
    module = _load()
    tokens: list[str] = []
    remote = iter(
        (
            json.dumps({"schema_version": 1, "state": "rejected"}).encode(),
            json.dumps({"schema_version": 1, "state": "advancing"}).encode(),
        )
    )
    monkeypatch.setattr(module, "_remote", lambda *_args, **_kwargs: next(remote))
    monkeypatch.setattr(module, "_old_sender_generation", lambda _manifest: "e" * 64)

    def token_rejected(path: Path) -> bool:
        tokens.append(path.name)
        return True

    monkeypatch.setattr(module, "_token_rejected", token_rejected)
    assert (
        module._default_execute(
            "old-material-rejection",
            acceptance["manifest"],
            {"deadline_seconds": 60},
        )
        == "observed"
    )
    assert tokens == ["primary_old_token.json", "secondary_old_token.json"]


def test_invalid_candidate_refuses_without_generation_change(
    monkeypatch, acceptance
) -> None:
    module = _load()
    expected = "f" * 64
    state = {
        "schema_version": 1,
        "state": "verified",
        "current": expected,
        "previous": "0" * 64,
        "tsdb_device": 1,
        "tsdb_inode": 2,
        "schedule_count": 3,
    }
    monkeypatch.setattr(module, "_rollback_generation", lambda _manifest: expected)
    monkeypatch.setattr(
        module,
        "_remote",
        lambda *_args, **_kwargs: json.dumps(state).encode(),
    )
    operations: list[tuple[str, str | None, bool]] = []

    def operator(_manifest, command, _component, **kwargs):
        operations.append(
            (
                command,
                kwargs.get("variables"),
                kwargs.get("expect_role_guard_refusal", False),
            )
        )
        return {
            "state": (
                "rendered-check" if command == "render" else "role-guard-refused"
            )
        }

    monkeypatch.setattr(module, "_operator", operator)
    monkeypatch.setattr(module, "_require_healthy", lambda *_args: None)
    assert (
        module._default_execute(
            "invalid-candidate-refusal",
            acceptance["manifest"],
            {"deadline_seconds": 600},
        )
        == "observed"
    )
    assert operations == [
        (
            "render",
            acceptance["manifest"]["inputs"]["candidate_control_plane_vars"],
            False,
        ),
        (
            "rotate",
            acceptance["manifest"]["inputs"]["invalid_control_plane_vars"],
            True,
        ),
    ]


def test_invalid_candidate_requires_exactly_one_mutation_from_rendered_candidate(
    monkeypatch, acceptance
) -> None:
    module = _load()
    path = Path(acceptance["manifest"]["inputs"]["invalid_control_plane_vars"])
    value = json.loads(path.read_text())
    value["observability_control_plane"]["ingress_port"] = 9444
    _private(path, value)
    monkeypatch.setattr(
        module,
        "_remote",
        lambda *_args, **_kwargs: json.dumps(
            {
                "schema_version": 1,
                "state": "verified",
                "current": "f" * 64,
                "previous": "0" * 64,
                "tsdb_device": 1,
                "tsdb_inode": 2,
                "schedule_count": 3,
            }
        ).encode(),
    )
    monkeypatch.setattr(module, "_rollback_generation", lambda _manifest: "f" * 64)
    monkeypatch.setattr(
        module,
        "_operator",
        lambda *_args, **_kwargs: pytest.fail("operator called"),
    )

    with pytest.raises(module.AcceptanceError, match="invalid candidate rejected"):
        module._default_execute(
            "invalid-candidate-refusal",
            acceptance["manifest"],
            {"deadline_seconds": 600},
        )


def test_invalid_candidate_does_not_credit_untyped_operator_failure(
    monkeypatch, acceptance
) -> None:
    module = _load()
    expected = "f" * 64
    state = {
        "schema_version": 1,
        "state": "verified",
        "current": expected,
        "previous": "0" * 64,
        "tsdb_device": 1,
        "tsdb_inode": 2,
        "schedule_count": 3,
    }
    monkeypatch.setattr(module, "_rollback_generation", lambda _manifest: expected)
    monkeypatch.setattr(
        module,
        "_remote",
        lambda *_args, **_kwargs: json.dumps(state).encode(),
    )

    def operator(_manifest, command, _component, **_kwargs):
        if command == "render":
            return {"state": "rendered-check"}
        raise module.AcceptanceError("bounded lifecycle action failed")

    monkeypatch.setattr(module, "_operator", operator)

    with pytest.raises(module.AcceptanceError, match="bounded lifecycle action failed"):
        module._default_execute(
            "invalid-candidate-refusal",
            acceptance["manifest"],
            {"deadline_seconds": 600},
        )


def test_valid_candidate_activation_precedes_exact_rollback(
    monkeypatch, acceptance
) -> None:
    module = _load()
    expected = "f" * 64
    candidate = "3" * 64

    def state(current: str, previous: str | None) -> bytes:
        return json.dumps(
            {
                "schema_version": 1,
                "state": "verified",
                "current": current,
                "previous": previous,
                "tsdb_device": 1,
                "tsdb_inode": 2,
                "schedule_count": 3,
            }
        ).encode()

    responses = iter(
        (
            state(expected, "0" * 64),
            state(candidate, expected),
            json.dumps({"state": "advancing"}).encode(),
            state(candidate, expected),
            state(expected, candidate),
            json.dumps({"state": "advancing"}).encode(),
        )
    )
    monkeypatch.setattr(module, "_rollback_generation", lambda _manifest: expected)
    monkeypatch.setattr(module, "_remote", lambda *_args, **_kwargs: next(responses))
    operations: list[tuple[str, str | None, str | None]] = []

    def operator(_manifest, command, _component, **kwargs):
        operations.append(
            (command, kwargs.get("variables"), kwargs.get("secrets"))
        )
        return {}

    monkeypatch.setattr(module, "_operator", operator)
    monkeypatch.setattr(module, "_require_healthy", lambda *_args: None)

    assert (
        module._default_execute(
            "valid-candidate-activation",
            acceptance["manifest"],
            {"deadline_seconds": 600},
        )
        == "observed"
    )
    assert (
        module._default_execute(
            "control-plane-rollback",
            acceptance["manifest"],
            {"deadline_seconds": 600},
        )
        == "observed"
    )
    assert operations == [
        (
            "rotate",
            acceptance["manifest"]["inputs"]["candidate_control_plane_vars"],
            acceptance["manifest"]["inputs"][
                "candidate_control_plane_secrets"
            ],
        ),
        (
            "rollback",
            acceptance["manifest"]["inputs"]["control_plane_vars"],
            acceptance["manifest"]["inputs"]["control_plane_secrets"],
        ),
    ]


def test_interrupted_candidate_activation_restores_last_known_good_inputs(
    monkeypatch, acceptance
) -> None:
    module = _load()
    calls: list[tuple[str | None, str | None]] = []

    def operator(_manifest, command, component, **kwargs):
        assert command == "rollback"
        assert component == "control-plane"
        calls.append((kwargs.get("variables"), kwargs.get("secrets")))
        return {"state": "rolled-back"}

    monkeypatch.setattr(module, "_operator", operator)
    module._default_restore(
        "valid-candidate-activation",
        module.STEP_RESTORES["valid-candidate-activation"],
        acceptance["manifest"],
        {"deadline_seconds": 600},
    )

    assert calls == [
        (
            acceptance["manifest"]["inputs"]["control_plane_vars"],
            acceptance["manifest"]["inputs"]["control_plane_secrets"],
        )
    ]


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
