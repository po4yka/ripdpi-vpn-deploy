---
task_id: SEC-1787496881680472
change: sec-1787496881680472-sshd-config-ownership
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: covered by the live lockout rehearsal; check-mode adds no signal beyond molecule for this surface
staging: not_applicable
staging_evidence: no separate staging environment exists; the scratch-node lockout rehearsal is the staging equivalent
live: required
live_evidence: null
client: not_applicable
client_evidence: no client emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SSHD-SINGLE-OWNER | SEC-1787496118906968 | duplicate-directive negative test; effective-config diff before/after a managed edit | pending |
| REQ-SSHD-EFFECTIVE-VALIDATION | SEC-1787496118907241 | molecule case injecting an out-of-band conflicting drop-in failing at validation | pending |
| REQ-SSHD-ALGO-PIN | SEC-1787496118907162 | verify.yml assertion output of sshd -T algorithms on both distros | pending |

## Gates

- Local: baseline molecule matrix, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Live: scratch-node lockout rehearsal (custom port + pinned algorithms) followed by one fleet node converge.
