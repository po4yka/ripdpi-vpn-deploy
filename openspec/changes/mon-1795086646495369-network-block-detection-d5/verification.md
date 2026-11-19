---
task_id: MON-1795086646495369
change: mon-1795086646495369-network-block-detection-d5
commit_sha: 07c33a5a
local: passed
local_evidence: Second security review fixes at ad98147c, c29c085c and cba6b1e8 pass the local checks in the section of that name at cba6b1e8. Implementation at 07c33a5a. Focused pytest of 8 files (alert rules with promtool 3.15.1, expected targets, Telegram delivery, control-plane render, fleet rotation, docs index, agent instructions, retention) has 314 passed and 1 failure, `test_alertmanager_v0281_enforces_the_webhook_request_timeout`, which asserts the native lane's ALERTMANAGER_BIN (environment gap, not a regression); `tests/unit/test_fleet_rotation.py` exit 0 (52 passed); `scripts/fleet-rotate.sh --plan --dry-run --block-hints` on a scratch plan printed the hint and exit 0, and without `--dry-run` refused with `block-hints-require-dry-run` and exit 1, leaving no journal (`d5-fleet-rotate-wrapper.log`); a mutated stage_mix expectation makes `promtool test rules` exit 1, so the divergence case is live; `make snapshot-check` exit 0; `make docs-check` exit 0; `ansible-lint --offline` and yamllint on observability_control_plane exit 0; `./taskctl openspec cli validate --strict` exit 0. `make check` was not run. Logs are in the session run directory runs-d2d4d5 (d5-*.log).
remote_ci: required
remote_ci_evidence: Not run; no push is authorized.
dry_run: not_applicable
dry_run_evidence: No deploy controller change; fleet-rotate hint is read-only.
staging: required
staging_evidence: Not run; no staging deployment is authorized. Needed (D7): a staging collector receiving sentinel probe series and field-report series that fires FieldReportNetworkBlocked, and the delivered Telegram message.
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: required
client_evidence: Not run; RIPDPI R3 must supply real failure-stage reports through D7.
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-BLOCK-ALERT | MON-1795086667788936 | promtool divergence case: sentinel 1, 70 percent of 6000 attempts per hour fail, fires at 60m with protocol, asn, country, node and value, stage_mix and rotation_hint annotations; silent at 10m | passed (local, 07c33a5a) |
| REQ-BLOCK-NOT-SERVER | MON-1795086687652889 | promtool server-down case: sentinel 0 with the same client failures gives no FieldReportNetworkBlocked; the client failure alert still fires. No new server alert was added: protocol outages stay with the existing probe and liveness alerts | passed (local, 07c33a5a) |
| REQ-BLOCK-LOWSAMPLE | MON-1795086687652889 | promtool low-sample case: 100 percent failures with 60 attempts per hour (floor 100) give no alert | passed (local, 07c33a5a) |
| REQ-BLOCK-ORIGIN | MON-1795086667788936 | promtool case `untrusted-origin` in `test_promtool_rule_cases_cover_firing_stale_recovery_and_absent`; relay owner tests in `test_observability_control_plane_render.py` | passed (local, cba6b1e8) |
| REQ-BLOCK-HINT | MON-1795086713751110 | `test_plan_mode_shows_block_hints_and_starts_no_rotation` (Alertmanager and Prometheus exports; health, rotation and audit are fail-stubs; no journal), `test_block_hints_are_refused_outside_plan_mode`, `test_block_hint_fields_with_control_characters_are_not_printed`, `test_malformed_block_hints_refuse` | passed (local, 07c33a5a) |
| REQ-BLOCK-RUNBOOK | MON-1795086734829714 | per-rule annotation, action length and runbook anchor checks in `tests/unit/test_observability_control_plane_alerting.py`; `### field-report-network-block` in `docs/how-to/monitoring-alerts.md`; thresholds and decision flow in `docs/reference/observability-operations.md` | passed (local, 07c33a5a) |

## Not done here

- Remote CI: no push is authorized.
- Staging and client: D7 owns firing the alert on staging with real RIPDPI R3 reports.

## Second security review (1a159bc1..0f3b138b)

An independent security review of the whole field-analytics range returned REQUEST CHANGES. The findings that this change owns are fixed below, each in its own commit with a regression test that fails before the fix. Verdict after the fixes: APPROVE for local evidence; staging, remote CI and Molecule stay open as listed above.

- Finding 1 (MEDIUM), fixed in cba6b1e8 with the relay rules owned by D3: `FieldReportNetworkBlocked` read `min by (environment, protocol) (vpn_protocol_probe_success)` without an origin filter and summed field reports across nodes. Probe series now reach Prometheus only from the collector agent, and both field-report rules read only `field_report.source_nodes`; the `untrusted-origin` promtool case fires both alerts before the fix.
- Finding 4 (MEDIUM, accepted with bounds), fixed in c29c085c: the alert needs `block_min_reports` distinct reports (default 10) besides the attempts floor, and its `rotation_hint` and runbook state that the client side is unauthenticated input to confirm from a second source. The `single-report` promtool case fires before the fix.
- Finding 8, fixed in ad98147c: `block_hints` crashed on `{"data": []}` and a numeric `stage_mix`; both are type-checked now. Three new cases in `test_fleet_rotation.py` fail before.

At cba6b1e8 (logs in the session run directory runs-secfix-d7, verify-*.log): focused pytest of 17 files (contract, ingest, rotation, exporters, relay render, alert rules with promtool 3.15.1, observability contract, agent render, retention, secrets schema, audit hooks, agent instructions, governance, docs index, journald, operator) exit 0, 895 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and hysteria exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract fixture validates and every negative fixture is rejected exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1 to D5 and D7; `./taskctl validate` exit 0. Each fix commit carries a regression test that failed on the code before it (red runs in the same directory). `make molecule-test` and `make check` were not run.
