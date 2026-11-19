---
task_id: MON-1795086847564764
change: mon-1795086847564764-observability-retention-delivery-d6
commit_sha: 65a34e46
local: passed
local_evidence: Implementation at 10d01ccb and 65a34e46. Focused pytest of the observability, monitoring, Makefile, docs, governance and agent-instruction test files plus the new retention test exit 0 (1405 passed); `tests/unit/test_observability_operator.py` exit 0 (145 passed); `scripts/render-snapshots.py` exit 0 (no template output changed); `make docs-check` exit 0; `ansible-lint --offline ansible/roles/monitoring` exit 0; yamllint exit 0; `./taskctl openspec cli validate --strict` exit 0. `make check` was not run.
remote_ci: required
remote_ci_evidence: Not run; no push is authorized.
dry_run: not_applicable
dry_run_evidence: Retention flags are exercised by render tests; no deploy controller change.
staging: required
staging_evidence: Not run and not authorized. MON-1795086987482765 stays open. It needs (1) the relay change owned by MON-1794126016474351 that returns the Telegram message id in the drill receipt, (2) explicit operator authorization for `make observability-drill OBSERVABILITY_ENVIRONMENT=staging ... OBSERVABILITY_DRILL_RECEIPT=<new private path>` and (3) a human check that the message arrived. No receipt is recorded here.
live: not_applicable
live_evidence: Live delivery is not required; staging receipt satisfies the capability.
client: not_applicable
client_evidence: Server-side operator notification only.
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RET-TABLE | MON-1795086901615679 | `test_documented_retention_table_is_complete_and_finite`, `test_retention_check_fails_for_a_missing_or_unbounded_class` (row removed, unlimited, zero, raw retained) | passed (local, 10d01ccb) |
| REQ-RET-ENFORCED | MON-1795086931324175 | `test_rendered_configuration_carries_the_documented_retention` (Prometheus, vmagent, relay, journald, logrotate rendered with defaults); `scripts/render-snapshots.py` exit 0 | passed (local, 10d01ccb) |
| REQ-RET-FIELDREPORT | MON-1795086873036849 | table row `none` checked by the retention test; the ingest state listing is pending D2 (no ingest exists yet) | partial: table passed (local, 10d01ccb), listing pending D2 |
| REQ-DELIVERY-RECEIPT | MON-1795086987482765 | schema and drill: `test_drill_reports_a_schema_valid_receipt_without_token_or_chat_id`, `test_receipt_contract_forbids_identifiers_and_malformed_values`, `test_drill_rejects_a_malformed_telegram_message_id`, `test_make_drill_forwards_the_receipt_path_literally`; staging receipt not recorded | partial: local contract passed (65a34e46), staging receipt pending |
