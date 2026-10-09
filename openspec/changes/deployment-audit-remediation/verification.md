---
task_id: SEC-1791471757439452
change: deployment-audit-remediation
commit_sha: bc3d11afbf91e036f910e3c8245a6d06de2d0327
local: passed
local_evidence: Full build-gated make check passed with the pinned mise toolchain and installed SOPS/age binaries; 5475 Python tests, 56 Bats tests, 205 Rust release tests, 108 Terraform mock tests, 52 policy tests and 148 snapshots passed.
remote_ci: passed
remote_ci_evidence: Exact source revision bc3d11afbf91e036f910e3c8245a6d06de2d0327 completed 79 successful checks and one neutral Trivy comparison; run 37884851139 includes 21 native Linux tests and all runtime scenarios.
dry_run: not_applicable
dry_run_evidence: Source PR only; isolated controller orchestration exercises positive and failure paths without live inventory or SSH. No remote dry-run acceptance is claimed.
staging: not_applicable
staging_evidence: No provider rollout is included in this source remediation PR; hosted native and Molecule checks are distinct from provider acceptance.
live: not_applicable
live_evidence: Production rollout is outside this source remediation PR.
client: not_applicable
client_evidence: No client traffic acceptance is claimed by source remediation.
artifact: passed
artifact_evidence: Source revision bc3d11afbf91e036f910e3c8245a6d06de2d0327 contains all six review corrections and integrates main without conflicts; full local and hosted source gates passed.
---

# Verification

The observations below apply to the recorded source revision, including all six
review corrections and integration of main revision
67aab6ed33f8e0b0de8709ea604bcb6f219a5162.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-SECRETS | SEC-1791471911428987 | Redacted runtime callbacks and real Ansible regressions; full local and hosted gates | passed |
| REQ-AUDIT-SECRETS | SEC-1791471912312773 | Private malformed-input diagnostics and real CI credential generation against the schema | passed |
| REQ-AUDIT-POLICY | SEC-1791471912312773 | 108 Terraform mock tests, 52 Rego tests and saved-plan identity/rejection regressions | passed |
| REQ-AUDIT-RUNTIME | SEC-1791471911428987 | Reviewed snapshots, native forwarding checks and successful hosted runtime scenarios | passed |
| REQ-AUDIT-RUNTIME | SEC-1791471912312773 | Native honeypot and seed mount/key-digest checks; full local and hosted gates | passed |
| REQ-AUDIT-LIFECYCLE | SEC-1791471911428987 | Effective service ownership and maintenance regressions; full local and hosted gates | passed |
| REQ-AUDIT-OPERATORS | SEC-1791471912998245 | Canonical controller, exact-host selection, complete drift comparison and CI orchestration regressions | passed |
| REQ-AUDIT-ROLLBACK | SEC-1791471911428987 | Real Ansible validation/activation failure restoration and hosted failure scenarios | passed |
| REQ-AUDIT-OPERATORS | SEC-1791471913677997 | Independent infrastructure/runtime reviews, full make check and exact-source hosted results | passed |

## Observed source checks

- `make check` completed successfully under the machine-wide build gate, with
  two Cargo jobs and serial Make. The pinned mise tools remained active; SOPS
  and age resolved to installed binaries rather than inactive mise shims in
  tests that intentionally isolate HOME.
- Python: 5,475 passed, 22 subtests passed, 21 native tests excluded from the
  portable lane. Hosted native Linux: all 21 passed. No silent skips were used.
- Shell: all 56 Bats tests passed. Rust: release Clippy with warnings denied and
  all 205 release tests passed, plus the MSRV and dependency-policy checks.
- Terraform: 108 mock tests passed across four provider roots. Rego: 52 passed.
  All 148 templates rendered and matched reviewed snapshots. These checks do
  not claim provider or deployed firewall acceptance.
- Hosted source revision `bc3d11afbf91e036f910e3c8245a6d06de2d0327`: 79 checks
  succeeded; all required checks and runtime scenarios completed successfully.
  Trivy was neutral because six baseline scan configurations were missing,
  preventing GitHub from calculating the PR alert delta. A complete comparative
  Trivy result is not claimed.

## Fresh-node deployment integration

Both credentialed workflows use the same protected fresh-node lifecycle:
provider-imported private SSH identity seed, digest verification before first
contact, recovery exercises, confirmed Tailnet and SSH ownership, canonical
deployment, actual protocol promotion and exact-resource teardown. Each matrix
profile owns a new guest. Private failure recovery is encrypted to an operator
recipient; plaintext state and credentials are not uploaded.

The hosted native lane exercised the real loopback SSH sentinel, wrong-pin
refusal and owned cleanup; the real seed disk mount, identity verification and
unmount path; and actual cryptographic credential generation against the schema.
Portable tests cover positive orchestration, failure cleanup and repeated soft
cancellation. These observations do not replace a live provider run.

The protected environment lacked the four required CI secrets when inspected.
No credentialed deployment, production change or client traffic acceptance was
performed. The CI runbook documents those prerequisites and the separate live
acceptance commands. The task remains in review with the source PR.

## Review

Independent infrastructure and runtime reviews covered the final implementation.
Their findings were repaired and regression-tested, including seed bootstrap
failure propagation, exact disk cleanup, structural SNI parsing, cancellation
handling and the SSH sentinel's native startup prerequisites. The final narrow
security review found no actionable issues. Hard runner termination can still
interrupt cleanup and requires the documented provider inspection.

The review follow-up made address cleanup idempotent for an absent owned /32,
kept standalone split-hop forwarding active, streamed the canonical read-only
Xray validator without requiring an installed helper, restored bootstrap waiting
before recovery installation, and published categorical CI startup failures
without replacing detailed executor results. Repository evidence is self-contained.
Executable regressions cover each behavior and independent review found no
remaining actionable defects. Hosted honeypot and split-hop Molecule scenarios
passed on this revision. The local arm64 Molecule attempt could not create the
pinned image because its manifest lacks that architecture; no local role-runtime
pass is claimed.
