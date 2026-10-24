---
task_id: XRY-1792776853872491
change: xray-reviewed-pin-status
commit_sha: 6d65d28b07376ecd226eb7635608d6279bb6cf21
local: passed
local_evidence: Four pin parser regressions and the Xray breaking-change guard passed. The full canonical make check passed with exit 0 on 2026-10-24 in the pinned environment, including validation, 10280 Python tests, 45 subtests, 70 Bats tests, 387 vpnd tests and documentation checks. The local stage deselected its 253 native-runtime cases by the existing partition; hosted native runtime integration passed.
remote_ci: required
remote_ci_evidence: Head 6d65d28b07376ecd226eb7635608d6279bb6cf21 completed 97 successful checks and one neutral result. Client contract-sync and its aggregate check remain failed until the paired client contract reaches its default branch. Final exact-head hosted acceptance remains open.
dry_run: not_applicable
dry_run_evidence: Local source parity only.
staging: not_applicable
staging_evidence: No release promotion; the existing staging gate remains required for future rollout.
live: not_applicable
live_evidence: No deployed pin or runtime change.
client: not_applicable
client_evidence: Client security rebuild is owned by the paired implementation task.
artifact: required
artifact_evidence: Reviewed pin and current release must remain distinct in the reference.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-XRAY-REVIEWED-PIN | XRY-1792776944051255 | Pin parser regressions, release guard and full local make check passed; final hosted gate remains open | Local passed; hosted required |
