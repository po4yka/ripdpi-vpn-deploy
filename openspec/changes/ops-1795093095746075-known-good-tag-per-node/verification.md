---
task_id: OPS-1795093095746075
change: ops-1795093095746075-known-good-tag-per-node
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change adds a local receipt write after verify and a local tag gate; it changes no node state.
staging: not_applicable
staging_evidence: No staging-only path; the tag gate and receipt writer run on the operator workstation.
live: not_applicable
live_evidence: The first fleet tag follows a separate authorized rollout after merge; this change does not mutate infrastructure.
client: not_applicable
client_evidence: No emitted client document or bundle contract changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093593849458 | `tests/unit/test_known_good.py`; `tests/unit/test_make_strict_gates.py::test_verify_records_a_receipt_only_after_source_drift_passes`, `::test_tag_known_good_requires_every_listed_inventory` | pending |
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093606367202 | `vpnd/tests/test_deploy_lifecycle.py::test_skip_precheck_and_tag_on_success_flow_into_their_targets`; device lifecycle and migration tests | pending |
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093619046117 | `bash scripts/drift-since-tag.sh --repo-only` lists only deployable commits; `make docs-check` | pending |
