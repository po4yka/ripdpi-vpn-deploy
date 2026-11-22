---
task_id: TFR-1795328481774241
change: tfr-1795328481774241-encrypted-remote-state-w3
commit_sha: null
local: required
local_evidence: "make -k check -j 4: every target passed except task-check (stale board, regenerated, then pass) and three load-timing pytest failures that pass rerun alone; after review fixes, the state, cron and docs tests (136) and make docs-check pass"
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No Ansible input changes.
staging: not_applicable
staging_evidence: Staging workspaces migrate with the same procedure and are covered by the live receipts.
live: required
live_evidence: "Operator kit receipts w3-scw-lock-probe-20261122, w3-migration-20261122 (four workspaces) and w3-restore-drill-20261122 (backup, version listing, locked restores, no-change plans, lineage refusal)"
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-STATE-ENCRYPTED | TFR-1795328555023000 | Stored objects of all four migrated workspaces carry only `encrypted_data` plus metadata (migration receipts); state and plan encryption enforced in every root, pinned by `test_state_encryption_is_enforced_and_restore_decrypts_the_same_way`; re-plan of all four workspaces after enforcement: no resource changes | pass |
| REQ-STATE-BACKEND | TFR-1795328567014606 | Default and named workspace keys (`state/<root>/…`, `state/workspaces/<ws>/state/<root>/…`) read back with the scoped identities during migration and restore; `test_terraform_env.py` backend-file refusals | pass |
| REQ-STATE-KEYS | TFR-1795328590452221 | Lock probe receipt (scoped plan identity cannot lock, apply identity cannot delete state or write outside `state/`); bucket policy adds `OperatorRestore` (version list/read) for the operator identity only | pass |
| REQ-STATE-SERIAL | TFR-1795328578453594 | `scripts/state-lock-probe.sh` against the Scaleway bucket: second writer refused while locked, release, reacquire, reader refused; `test_state_lock_probe.py` | pass |
| REQ-STATE-MIGRATION | TFR-1795328602611143 | Per-root receipts: p1-scaleway 34→35, p0-upcloud 42→43, observer-upcloud 31→32, p2-vultr 88→89; equal lineage and addresses; no resource changes | pass |
| REQ-STATE-RECOVERY | TFR-1795328613654811 | Restore drill on p1-scaleway with only the operator kit documents, GitHub unused: listing, same-lineage restore as the next serial (stored 37, 39, 41), no-resource-change plan, other-lineage version refused; `test_tf_state_restore.py`, `test_tf_state_backup.py` | pass |
