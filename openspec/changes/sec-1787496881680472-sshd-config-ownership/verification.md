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
live: blocked
live_evidence: "Implementation committed; scratch-node custom-port/algorithm lockout rehearsal and one fleet converge require accessible nodes. All three matching server peers are offline. Legacy duplicated bootstrap directives intentionally fail and require node recreation or a separately reviewed migration."
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

## Observed implementation checks (2026-08-27)

`make check` exited 0: 1107 unit tests passed with one skipped test,
55 Bats checks, 83 Terraform mock tests, 45 Conftest tests, 102 snapshots,
strict Ansible lint, Rust MSRV and dependency checks, and 172 release tests.
The subsequent QR legacy-output regression slice passed 28 tests; full-stack
fixture guards passed for both inventories and the 14-test verification slice
passed with inherited privilege escalation enabled. Native Linux Molecule and
real staging/live acceptance are separate, still-required evidence.
