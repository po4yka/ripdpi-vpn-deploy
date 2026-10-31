---
task_id: CIC-1793457997498773
change: cic-1793457997498773-merge-every-pull-request-by-rebase-and-keep-lifecycle-commits-in-one-pull-request
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Repository policy, CI check and tasking tooling only; no deployment input changes.
staging: not_applicable
staging_evidence: No staging host is involved.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client artifact or contract changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RPOL-MERGE | CIC-1793458205564841 | policy contract test pins rebase-only settings and ruleset; PR-title tests cover valid, invalid and co-authored commit ranges; the PR title job passes on this pull request's own commits | required |
| REQ-RPOL-MERGE | CIC-1793458391172583 | `make repository-policy-plan` shows only the merge-method diff; `make repository-policy-apply` readback verified (authorized live step) | required |
| REQ-CIC-1793457997498773-001 | CIC-1793458297726343 | taskctl tests: done closure without any remote ref, collapsed transitions still rejected by the purge audit | required |
| REQ-CIC-1793457997498773-001 | CIC-1793458391172583 | README, CONTRIBUTING and skills name the rebase-only lifecycle; `./taskctl validate` accepts the refreshed asset lock; focused pytest, docs-check, make check and exact-head CI | required |
| REQ-CIC-1793437852879654-001 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
| REQ-CIC-1793437852879654-002 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
| REQ-CIC-1793437852879654-003 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
