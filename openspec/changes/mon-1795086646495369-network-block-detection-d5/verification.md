---
task_id: MON-1795086646495369
change: mon-1795086646495369-network-block-detection-d5
commit_sha: 07c33a5a
local: passed
local_evidence: Implementation at 07c33a5a. Focused pytest of 8 files (alert rules with promtool 3.15.1, expected targets, Telegram delivery, control-plane render, fleet rotation, docs index, agent instructions, retention) has 314 passed and 1 failure, `test_alertmanager_v0281_enforces_the_webhook_request_timeout`, which asserts the native lane's ALERTMANAGER_BIN (environment gap, not a regression); `tests/unit/test_fleet_rotation.py` exit 0 (52 passed); `scripts/fleet-rotate.sh --plan --dry-run --block-hints` on a scratch plan printed the hint and exit 0, and without `--dry-run` refused with `block-hints-require-dry-run` and exit 1, leaving no journal (`d5-fleet-rotate-wrapper.log`); a mutated stage_mix expectation makes `promtool test rules` exit 1, so the divergence case is live; `make snapshot-check` exit 0; `make docs-check` exit 0; `ansible-lint --offline` and yamllint on observability_control_plane exit 0; `./taskctl openspec cli validate --strict` exit 0. `make check` was not run. Logs are in the session run directory runs-d2d4d5 (d5-*.log).
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
| REQ-BLOCK-HINT | MON-1795086713751110 | `test_plan_mode_shows_block_hints_and_starts_no_rotation` (Alertmanager and Prometheus exports; health, rotation and audit are fail-stubs; no journal), `test_block_hints_are_refused_outside_plan_mode`, `test_block_hint_fields_with_control_characters_are_not_printed`, `test_malformed_block_hints_refuse` | passed (local, 07c33a5a) |
| REQ-BLOCK-RUNBOOK | MON-1795086734829714 | per-rule annotation, action length and runbook anchor checks in `tests/unit/test_observability_control_plane_alerting.py`; `### field-report-network-block` in `docs/how-to/monitoring-alerts.md`; thresholds and decision flow in `docs/reference/observability-operations.md` | passed (local, 07c33a5a) |

## Not done here

- Remote CI: no push is authorized.
- Staging and client: D7 owns firing the alert on staging with real RIPDPI R3 reports.
