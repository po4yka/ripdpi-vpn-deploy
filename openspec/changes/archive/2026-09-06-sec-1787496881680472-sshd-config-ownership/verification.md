---
task_id: SEC-1787496881680472
change: sec-1787496881680472-sshd-config-ownership
commit_sha: 501a27bbddd7e0c62378223ded801f6db77ef859
local: passed
local_evidence: the combined-tree make -j1 check passed with 2951 Python tests, one existing skip, 55 Bats tests, Rust release tests and Clippy; log SHA256 5daca6ec5b2403c80f3101956af6c463c4dbdfacb18b04c92b1ec03c7ff31af2
remote_ci: passed
remote_ci_evidence: "The source is present on protected main 0da5dae31e12242baebde842ab632cd1e1843140; exact-main CI passed all 75 jobs: https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/34030183169."
dry_run: not_applicable
dry_run_evidence: covered by the live lockout rehearsal; check-mode adds no signal beyond molecule for this surface
staging: not_applicable
staging_evidence: no separate staging environment exists; the scratch-node lockout rehearsal is the staging equivalent
live: not_applicable
live_evidence: "The real SSH staging rehearsal is consolidated in SEC-1787916931540401; this task makes no host rollout claim."
client: not_applicable
client_evidence: no client emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SSHD-SINGLE-OWNER | SEC-1787496118906968 | duplicate-directive negative tests and exact four-file ownership planner checks | passed |
| REQ-SSHD-EFFECTIVE-VALIDATION | SEC-1787496118907241 | assembled effective-policy checks across every publish and rollback prefix | passed |
| REQ-SSHD-ALGO-PIN | SEC-1787496118907162 | exact Ciphers, MACs and KexAlgorithms assertions in baseline and verify | passed |

## Gates

- Local: baseline molecule matrix, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Live: scratch-node lockout rehearsal (custom port + pinned algorithms) followed by one fleet node converge.

## Combined source candidate

The final source candidate reduces bootstrap ownership to the port and four
authentication primitives, keeps tunable hardening in the managed layer,
rejects cross-file duplicates, validates the assembled effective policy, and
pins exact algorithm sets in the managed template and post-converge verifier.
Focused SSH ownership and snapshot checks passed, as did production
`ansible-lint`, Python compilation, and independent review. These checks do not
replace the required scratch-node lockout rehearsal or fleet verification.

## Proportional verification decision — 2026-09-06

Verification follows the portfolio proportional-evidence policy. Source closure does not claim staging or live operation; any delegated operational requirement remains open in the task named in the front matter evidence above.
