---
task_id: SCR-1795085709140075
change: scr-1795085709140075-field-contracts-d1
commit_sha: 207bb88153af9fe7b0748a2590cbb97acace1724
local: passed
local_evidence: At 207bb881, `python3 -m pytest tests/unit/test_bundle_schema.py tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_xhttp_alternate_profiles.py tests/unit/test_docs_index.py tests/unit/test_agent_instructions.py tests/unit/test_client_payload_recipient_boundaries.py tests/unit/test_device_migration_receipt.py tests/unit/test_client_drift.py` exit 0 (460 passed); every contract fixture validated by its validator (6 accepted, 31 negatives rejected); `make snapshot-check` exit 0; `make docs-check` exit 0; `./taskctl openspec cli validate scr-1795085709140075-field-contracts-d1 --strict --no-interactive` exit 0; `./taskctl validate` exit 0. The full `tests/unit` run had 161 failures and 54 errors, all in privileged or host-runtime tests; the same tests fail identically on a clean export of the base revision. `make check` was not run, because its unit stage carries those local host failures.
remote_ci: required
remote_ci_evidence: Not run; no push is authorized. The contract-sync workflow will fail until RIPDPI R2 vendors the new and changed contract files.
dry_run: not_applicable
dry_run_evidence: No deploy controller or rendered deployment input changes.
staging: not_applicable
staging_evidence: Contract-only change; staging proof is owned by D7.
live: not_applicable
live_evidence: Contract-only change; no live system is affected.
client: required
client_evidence: Pending RIPDPI R2, which vendors the schemas and fixtures byte-identically and runs the golden and negative fixtures.
artifact: required
artifact_evidence: Pending the verified merge SHA. Canonical files at 207bb88153af9fe7b0748a2590cbb97acace1724: contract/client-field-report.schema.json and contract/ripdpi-bundle.schema.json.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REPORT-SHAPE | SCR-1795085965580974 | `test_report_golden_validates_via_cli` and the `report-extra-*` cases of `test_report_negative_fixture_is_rejected_for_its_reason` (root, window, client, network, bucket) | passed (local, 207bb881) |
| REQ-REPORT-BUCKET | SCR-1795085995858987 | `report-failure-without-stage`, `report-success-with-stage`, `report-unknown-failure-stage`, `report-histogram-extra-bound` and `report-histogram-sum-mismatch` rejected for their named reasons | passed (local, 207bb881) |
| REQ-REPORT-PRIVACY | SCR-1795085995858987 | `report-server-ref-ipv4` (203.0.113.7), `report-server-ref-ipv6`, `report-server-ref-hostname` (node.example.org), `report-start-not-hour` (10:15:00Z) and `report-start-seconds` rejected; diagnostics do not echo values | passed (local, 207bb881) |
| REQ-REPORT-MINBUCKET | SCR-1795085995858987 | `report-attempts-below-5` rejected on `minimum` at `/buckets/2/attempts`; suppression rule stated in `docs/reference/ripdpi-bundle.md` | passed (local, 207bb881) |
| REQ-BUNDLE-V3 | SCR-1795086029049140 | `test_v2_golden_rejected_on_schema_version_only`, `neg-schema-version-2`, `neg-field-report-http-endpoint`, `test_field_report_endpoint_requires_plain_https`, `test_golden_full_validates_via_cli` | passed (local, 207bb881) |
| REQ-BUNDLE-HEALTH-TTL | SCR-1795086060772476 | `contract/ripdpi-bundle.health-expired.json` with `test_expired_health_fixture_is_the_expiry_case` and `test_expired_health_rule_is_documented` | passed (local, 207bb881) |
