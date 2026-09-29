from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/observability-staging-cleanup.py"
ACCEPTANCE = ROOT / "scripts/observability-staging-acceptance.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "observability_staging_cleanup", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _journal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": "MON-1790650904289505",
        "change": "staging-observability-telegram-acceptance",
        "status": "ready-for-cleanup",
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "completed_checks": [
            "agent-wal",
            "canary-sender-rotation",
            "control-host-loss",
            "control-plane-rollback",
            "control-service-loss",
            "deadman-lifecycle",
            "deadman-service-loss",
            "finite-silence",
            "fresh-metrics",
            "grouping-inhibition",
            "ingestion-negative",
            "invalid-candidate-refusal",
            "old-material-rejection",
            "primary-authority-loss",
            "primary-bot-rotation",
            "primary-lifecycle",
            "secondary-bot-rotation",
            "staleness",
            "valid-candidate-activation",
        ],
        "human_observations": {
            "deadman_loss_primary": True,
            "primary_authority_loss_secondary": True,
            "primary_lifecycle": True,
            "secondary_lifecycle": True,
        },
        "components_removed": True,
    }


def test_cleanup_contract_matches_acceptance_terminal_rows() -> None:
    cleanup = _load()
    spec = importlib.util.spec_from_file_location(
        "observability_staging_acceptance_for_cleanup", ACCEPTANCE
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)

    assert cleanup.COMPLETED_CHECKS == tuple(sorted(acceptance.ACCEPTANCE_CHECKS))


def _providers() -> list[dict[str, object]]:
    return [
        {
            "provider": "upcloud",
            "account_id": "account-a",
            "project_id": None,
            "environment": "staging",
            "state_path": "/private/upcloud.tfstate",
            "state_sha256": "1" * 64,
            "destroy_plan_sha256": "a" * 64,
            "terraform_addresses": [
                "terraform_data.ssh_port",
                "upcloud_firewall_rules.vpn",
                "upcloud_server.vpn",
            ],
            "provider_resources": [
                {
                    "terraform_address": "upcloud_server.vpn",
                    "kind": "server",
                    "provider_id": "00ed52e0-c885-48e9-9504-6f4bb95090f7",
                    "location": None,
                    "absence_owner": None,
                },
                {
                    "terraform_address": "upcloud_server.vpn",
                    "kind": "storage",
                    "provider_id": "01ed52e0-c885-48e9-9504-6f4bb95090f7",
                    "location": None,
                    "absence_owner": None,
                },
            ],
        },
        {
            "provider": "hetzner",
            "account_id": "42",
            "project_id": None,
            "environment": "staging",
            "state_path": "/private/hetzner.tfstate",
            "state_sha256": "2" * 64,
            "destroy_plan_sha256": "b" * 64,
            "terraform_addresses": [
                "hcloud_firewall.vpn",
                "hcloud_firewall_attachment.vpn",
                "hcloud_server.vpn",
                "hcloud_ssh_key.admin",
                "terraform_data.ssh_port",
            ],
            "provider_resources": [
                {
                    "terraform_address": "hcloud_server.vpn",
                    "kind": "server",
                    "provider_id": "4201",
                    "location": None,
                    "absence_owner": None,
                },
                {
                    "terraform_address": "hcloud_firewall.vpn",
                    "kind": "firewall",
                    "provider_id": "4202",
                    "location": None,
                    "absence_owner": None,
                },
                {
                    "terraform_address": "hcloud_ssh_key.admin",
                    "kind": "ssh-key",
                    "provider_id": "4203",
                    "location": None,
                    "absence_owner": None,
                },
            ],
        },
        {
            "provider": "scaleway",
            "account_id": "org-a",
            "project_id": "11111111-1111-4111-8111-111111111111",
            "environment": "staging",
            "state_path": "/private/scaleway.tfstate",
            "state_sha256": "3" * 64,
            "destroy_plan_sha256": "c" * 64,
            "terraform_addresses": [
                "scaleway_instance_ip.ipv4[0]",
                "scaleway_instance_security_group.vpn",
                "scaleway_instance_server.vpn",
                "terraform_data.ssh_port",
            ],
            "provider_resources": [
                {
                    "terraform_address": "scaleway_instance_server.vpn",
                    "kind": "server",
                    "provider_id": "22222222-2222-4222-8222-222222222222",
                    "location": "fr-par-1",
                    "absence_owner": None,
                },
                {
                    "terraform_address": "scaleway_instance_ip.ipv4[0]",
                    "kind": "ip",
                    "provider_id": "33333333-3333-4333-8333-333333333333",
                    "location": "fr-par-1",
                    "absence_owner": None,
                },
                {
                    "terraform_address": "scaleway_instance_security_group.vpn",
                    "kind": "security-group",
                    "provider_id": "44444444-4444-4444-8444-444444444444",
                    "location": "fr-par-1",
                    "absence_owner": None,
                },
            ],
        },
    ]


def _manifest(module) -> dict[str, object]:
    journal = _canonical(_journal())
    providers = _providers()
    scope = module.cleanup_scope_sha256(providers)
    return {
        "schema_version": 1,
        "task_id": "MON-1790650904289505",
        "change": "staging-observability-telegram-acceptance",
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "acceptance_journal_sha256": hashlib.sha256(journal).hexdigest(),
        "snapshot_sha256": "d" * 64,
        "created_at": "2026-09-29T10:00:00Z",
        "expires_at": "2026-09-29T12:00:00Z",
        "providers": providers,
        "approval": {
            "approval_id": "cleanup-20260929",
            "approved_at": "2026-09-29T10:01:00Z",
            "expires_at": "2026-09-29T12:00:00Z",
            "rollback_retention_closed": True,
            "scope_sha256": scope,
        },
    }


def test_acceptance_journal_requires_exact_completed_contract() -> None:
    module = _load()
    module.validate_acceptance_journal(_journal())
    broken = _journal()
    broken["completed_checks"] = broken["completed_checks"][:-1]
    with pytest.raises(module.CleanupError, match="acceptance journal rejected"):
        module.validate_acceptance_journal(broken)


def test_manifest_binds_exact_staging_scope_and_later_approval() -> None:
    module = _load()
    value = _manifest(module)
    module.validate_manifest(
        value, now=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc)
    )
    value["providers"][1]["terraform_addresses"].append(
        "hcloud_floating_ip.honeypot_ipv4[0]"
    )
    value["providers"][1]["terraform_addresses"].sort()
    with pytest.raises(module.CleanupError, match="approval scope"):
        module.validate_manifest(
            value, now=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc)
        )


@pytest.mark.parametrize("environment", ["prod", "ci-staging-old", "Staging"])
def test_manifest_rejects_every_environment_except_exact_staging(
    environment: str,
) -> None:
    module = _load()
    value = _manifest(module)
    value["providers"][0]["environment"] = environment
    value["approval"]["scope_sha256"] = module.cleanup_scope_sha256(value["providers"])
    with pytest.raises(module.CleanupError, match="environment"):
        module.validate_manifest(
            value, now=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc)
        )


def test_delete_plan_must_delete_exact_frozen_address_set() -> None:
    module = _load()
    expected = _providers()[1]["terraform_addresses"]
    plan = {
        "resource_changes": [
            {"address": address, "change": {"actions": ["delete"]}}
            for address in expected
        ]
    }
    module.validate_destroy_plan(plan, expected)
    plan["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
    with pytest.raises(module.CleanupError, match="delete-only"):
        module.validate_destroy_plan(plan, expected)


def test_nonempty_state_must_be_bound_to_manifest() -> None:
    module = _load()
    with pytest.raises(module.CleanupError, match="nonempty unbound state"):
        module.validate_state_binding(
            b'{"version":4,"resources":[{}]}', None, "/private/upcloud.tfstate"
        )
    empty = b'{"version":4,"resources":[]}'
    module.validate_state_binding(empty, None, "/private/upcloud.tfstate")


def test_receipt_is_redacted_and_contains_no_resource_or_state_identity() -> None:
    module = _load()
    receipt = module.build_receipt(
        manifest=_manifest(module),
        manifest_bytes=_canonical(_manifest(module)),
        completed_at=datetime(2026, 9, 29, 11, 0, tzinfo=timezone.utc),
    )
    encoded = _canonical(receipt).decode()
    assert receipt["status"] == "provider-absence-verified"
    assert receipt["local_retirement"] == "permitted"
    for forbidden in (
        "00ed52e0",
        "4201",
        "22222222",
        "/private/",
        "terraform_addresses",
        "provider_id",
        "account_id",
        "project_id",
    ):
        assert forbidden not in encoded


def test_provider_absence_requires_404_for_every_direct_identity() -> None:
    module = _load()
    provider = _providers()[0]

    def status(_provider, resource):
        return 404 if resource["kind"] == "server" else 200

    with pytest.raises(module.CleanupError, match="provider absence ambiguous"):
        module.verify_provider_absence(provider, status)
    module.verify_provider_absence(provider, lambda _provider, _resource: 404)


def test_state_extraction_binds_upcloud_root_storage_and_all_addresses() -> None:
    module = _load()
    raw = _canonical(
        {
            "version": 4,
            "resources": [
                {
                    "mode": "managed",
                    "type": "terraform_data",
                    "name": "ssh_port",
                    "provider": 'provider["terraform.io/builtin/terraform"]',
                    "instances": [{"attributes": {"id": "local"}}],
                },
                {
                    "mode": "managed",
                    "type": "upcloud_firewall_rules",
                    "name": "vpn",
                    "provider": 'provider["registry.terraform.io/upcloudltd/upcloud"]',
                    "instances": [{"attributes": {"id": "server-a"}}],
                },
                {
                    "mode": "managed",
                    "type": "upcloud_server",
                    "name": "vpn",
                    "provider": 'provider["registry.terraform.io/upcloudltd/upcloud"]',
                    "instances": [
                        {
                            "attributes": {
                                "id": "server-a",
                                "template": [{"id": "storage-a"}],
                            }
                        }
                    ],
                },
            ],
        }
    )
    scope = module.extract_provider_scope(
        "upcloud", raw, account_id="account-a", project_id=None
    )
    assert scope["terraform_addresses"] == [
        "terraform_data.ssh_port",
        "upcloud_firewall_rules.vpn",
        "upcloud_server.vpn",
    ]
    assert {
        (item["kind"], item["provider_id"]) for item in scope["provider_resources"]
    } == {
        ("server", "server-a"),
        ("storage", "storage-a"),
    }


def test_seal_requires_approval_bound_to_snapshot_and_exact_scope() -> None:
    module = _load()
    created = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    snapshot = {
        "schema_version": 1,
        "task_id": "MON-1790650904289505",
        "change": "staging-observability-telegram-acceptance",
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "acceptance_journal_sha256": hashlib.sha256(_canonical(_journal())).hexdigest(),
        "created_at": "2026-09-29T10:00:00Z",
        "providers": _providers(),
        "scope_sha256": module.cleanup_scope_sha256(_providers()),
    }
    raw = _canonical(snapshot)
    approval = {
        "schema_version": 1,
        "task_id": "MON-1790650904289505",
        "change": "staging-observability-telegram-acceptance",
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "acceptance_journal_sha256": snapshot["acceptance_journal_sha256"],
        "scope_sha256": snapshot["scope_sha256"],
        "approval_id": "cleanup-20260929",
        "approved_at": "2026-09-29T10:10:00Z",
        "expires_at": "2026-09-29T12:00:00Z",
        "rollback_retention_closed": True,
    }
    manifest = module.seal_manifest(
        snapshot,
        raw,
        approval,
        now=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc),
    )
    assert manifest["snapshot_sha256"] == approval["snapshot_sha256"]
    approval["scope_sha256"] = "0" * 64
    with pytest.raises(module.CleanupError, match="approval scope"):
        module.seal_manifest(
            snapshot,
            raw,
            approval,
            now=created.replace(hour=11),
        )


def test_provider_http_disables_proxy_and_refuses_redirect(monkeypatch) -> None:
    module = _load()
    captured = []

    class Built:
        pass

    monkeypatch.setattr(
        module.urllib.request,
        "build_opener",
        lambda *handlers: captured.extend(handlers) or Built(),
    )
    assert isinstance(module._api_opener(), Built)
    proxy = next(
        item for item in captured if isinstance(item, urllib.request.ProxyHandler)
    )
    redirect = next(item for item in captured if isinstance(item, module._NoRedirect))
    assert proxy.proxies == {}
    assert (
        redirect.redirect_request(None, None, 302, "redirect", {}, "https://other")
        is None
    )

    class Redirecting:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "redirect",
                {},
                io.BytesIO(b"{}"),
            )

    monkeypatch.setattr(module, "_api_opener", lambda: Redirecting())
    monkeypatch.setattr(
        module,
        "_auth_headers",
        lambda provider: {"Authorization": "Bearer secret"},
    )
    with pytest.raises(module.CleanupError, match="redirect"):
        module._http_json("upcloud", "https://api.upcloud.com/1.3/account")


def test_source_identity_drift_refuses_before_provider_action(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=f"{'f' * 40} {'e' * 64}\n", stderr=""
        ),
    )
    with pytest.raises(module.CleanupError, match="source identity drift"):
        module._verify_source(_journal())


@pytest.mark.parametrize(
    "porcelain", (b" M scripts/modified.py\0", b"?? scripts/unreviewed.py\0")
)
def test_source_cleanliness_refuses_tracked_and_untracked_drift(
    monkeypatch, porcelain
) -> None:
    module = _load()

    def fake_run(argv, **_kwargs):
        if argv[0].endswith("deploy-source-identity.sh"):
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{'a' * 40} {'b' * 64}\n"
            )
        if argv[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(argv, 0, stdout=porcelain)
        return subprocess.CompletedProcess(argv, 0, stdout="a" * 40 + "\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(module.CleanupError, match="clean protected-main source"):
        module._verify_source(_journal())


def test_progress_is_monotonic_and_binds_partial_destroy_recovery() -> None:
    module = _load()
    manifest = _manifest(module)
    manifest_raw = _canonical(manifest)
    journal_raw = _canonical(_journal())
    progress = module.build_progress(manifest, manifest_raw, journal_raw)
    module.validate_progress(progress, manifest, manifest_raw, journal_raw)
    progress = module.advance_progress(progress, "upcloud", "apply-started")
    progress = module.advance_progress(progress, "upcloud", "absent")
    assert progress["providers"][0] == {"provider": "upcloud", "phase": "absent"}
    with pytest.raises(module.CleanupError, match="transition"):
        module.advance_progress(progress, "upcloud", "pending")


def test_partial_apply_recovery_distinguishes_absent_present_and_mixed() -> None:
    module = _load()
    provider = _providers()[0]
    assert module.provider_presence(provider, lambda _scope, _resource: 404) == "absent"
    assert (
        module.provider_presence(provider, lambda _scope, _resource: 200) == "present"
    )
    assert (
        module.provider_presence(
            provider,
            lambda _scope, resource: 404 if resource["kind"] == "server" else 200,
        )
        == "ambiguous"
    )


def test_expired_authority_allows_absence_recovery_but_not_pending_delete() -> None:
    module = _load()
    manifest = _manifest(module)
    recovered_at = datetime(2026, 9, 29, 13, 0, tzinfo=timezone.utc)
    module.validate_manifest(manifest, now=recovered_at, allow_expired=True)
    with pytest.raises(module.CleanupError, match="expired"):
        module.validate_manifest(manifest, now=recovered_at)


def test_makefile_exposes_literal_confirmed_cleanup_surface() -> None:
    source = (ROOT / "Makefile").read_text()
    block = source[source.index("observability-staging-cleanup:\n") :]
    block = block[: block.index("\n\n")]
    assert "scripts/observability-staging-cleanup.py run" in block
    assert '"$${OBSERVABILITY_STAGING_CLEANUP_MANIFEST_LITERAL}"' in block
    assert '"$${OBSERVABILITY_STAGING_CLEANUP_JOURNAL_LITERAL}"' in block
    assert '"$${OBSERVABILITY_STAGING_CLEANUP_RECEIPT_LITERAL}"' in block
    assert "--confirm" in block


def test_makefile_cleanup_rejects_extra_fields_and_command_line_credentials() -> None:
    common = [
        "make",
        "-n",
        "observability-staging-cleanup",
        "OBSERVABILITY_STAGING_CLEANUP_MANIFEST=/private/manifest.json",
        "OBSERVABILITY_STAGING_CLEANUP_JOURNAL=/private/journal.json",
        "OBSERVABILITY_STAGING_CLEANUP_RECEIPT=/private/receipt.json",
    ]
    extra = subprocess.run(
        [*common, "ARBITRARY_COMMAND=id"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    credential = subprocess.run(
        [*common, "HCLOUD_TOKEN=not-ambient"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert extra.returncode != 0
    assert "accepts only private artifact paths" in extra.stderr
    assert credential.returncode != 0
    assert "credentials must come from the environment" in credential.stderr
