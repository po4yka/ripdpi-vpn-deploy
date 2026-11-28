---
task_id: OPS-1795704918170150
change: ops-1795704918170150-pre-admission-address-check
commit_sha: 6e2568ce4430ab300229814382dfb2006851cec9
local: required
local_evidence: "make -k -j 4 check: every target passed except test-unit; its failures were harness copies of tests/conftest.py (fixed) and load-induced timeouts that also fail on origin/main or pass serially. tests/unit/test_address_admission.py and test_emit_bundle_host_selection.py pass."
remote_ci: passed
remote_ci_evidence: "ci workflow run https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/46147749765 passed on main 6e2568ce44, which contains PR 777, including contract-sync after the client vendored the node-address-check contract."
dry_run: not_applicable
dry_run_evidence: Planning only; no deploy controller change is made yet.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: not_applicable
client_evidence: No client change.
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---

# Verification

Local and remote CI evidence are recorded; staging evidence remains required.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ADMIT-REACH | OPS-1795705312358436 | `tests/unit/test_address_admission.py` (pass, closed /24 block, missing result) | local pass |
| REQ-ADMIT-REACH | OPS-1795705349825337 | `test_emit_bundle_host_selection.py::test_refused_node_address_never_appears_in_a_bundle` | local pass |
| REQ-ADMIT-NO-ICMP-ONLY | OPS-1795705412632581 | `docs/how-to/deploy.md`; `test_admission_decision[icmp-only-is-not-evidence]` and the two ICMP scenarios | local pass |
