---
task_id: OPS-1795093095746075
change: ops-1795093095746075-known-good-tag-per-node
commit_sha: f9d6a5139500016f895d25e4eececafb298df40a
local: passed
local_evidence: "tests/unit/test_known_good.py plus the two make_strict_gates receipt and inventory tests: 11 passed; vpnd test_deploy_lifecycle -k tag_on_success: 1 passed; scripts/drift-since-tag.sh --repo-only lists one deployable commit since the latest tag"
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy ci run 45410025050 on main at f9d6a5139: completed with success. That revision holds the change (566baae52, whose own main run failed in unrelated pytest group 4 and image-scan jobs)."
dry_run: not_applicable
dry_run_evidence: The change adds a local receipt write after verify and a local tag gate; it changes no node state.
staging: not_applicable
staging_evidence: No staging-only path; the tag gate and receipt writer run on the operator workstation.
live: passed
live_evidence: "make tag-known-good with two inventories (core fleet and the split-hop pair) at f9d6a5139 found fresh receipts with the checkout digest for all five vpn hosts and cut vpn-deploy-known-good-2026-11-25-1406 from the per-node receipts in KNOWN_GOOD_RECEIPTS_DIR"
client: not_applicable
client_evidence: No emitted client document or bundle contract changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093593849458 | `tests/unit/test_known_good.py`; `tests/unit/test_make_strict_gates.py::test_verify_records_a_receipt_only_after_source_drift_passes`, `::test_tag_known_good_requires_every_listed_inventory` | pass |
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093606367202 | `vpnd/tests/test_deploy_lifecycle.py::test_skip_precheck_and_tag_on_success_flow_into_their_targets`; device lifecycle and migration tests | pass |
| REQ-AUDIT-KNOWN-GOOD | OPS-1795093619046117 | `bash scripts/drift-since-tag.sh --repo-only` lists only deployable commits; `make docs-check` | pass |
