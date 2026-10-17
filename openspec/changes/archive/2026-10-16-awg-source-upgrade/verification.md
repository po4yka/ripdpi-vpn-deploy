---
task_id: SCR-1791618073850409
change: awg-source-upgrade
commit_sha: fc8938d9563e9cf61ead73f9bcdf07c90507fa6d
local: not_applicable
local_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
staging: not_applicable
staging_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
live: not_applicable
live_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
client: not_applicable
client_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
artifact: not_applicable
artifact_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
---

# Verification

## Scope

The owner required completion without external infrastructure on 2026-10-15
and authorized revised descriptions and acceptance. This delivers a real local
source-candidate build and interoperability lab. Physical Android, external
staging, production promotion and automatic production-role data-plane readiness
are outside this scope and are not represented as passing Docker evidence.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-VERSION | SCR-1791618078367215 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-WIRE | SCR-1791618079169597 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-ADOPT | SCR-1791618080142425 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-LOCAL | SCR-1791618081446678 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |

## Current observed checks

- Source commit: `1148aa10fd754f046f66c166a78e313b5cd48273`.
- Focused launcher, source-pin and version-floor suite: 50 passed. Regressions
  exercise delayed container visibility, transient removal failure, explicitly
  unknown cleanup, current lightweight/annotated tags with warm Git bundles,
  unsafe cache ownership, exact package snapshot inputs and toolchain corruption.
- Ruff check and format passed for changed Python files.
- `make test-awg-source-candidate` inside the actual machine-wide build-gate
  session rebuilt both real pairs. The fresh APT layer used the signed Ubuntu
  snapshot at `20261015T000000Z`; checksum-pinned CA bootstrap enabled HTTPS
  without relaxing TLS, archive signatures or package hashes.
- Image `ripdpi-awg-source-candidate:29916c582031af8f` completed the full Linux
  ARM64 lab in 183.383s without skips. The owned container was removed and the
  command returned zero. Its configuration digest is
  `b6fc98fd9df5fc061c112465c5b09620a0667f5b163c612492ba74d249a7d676`.
- A separate real Docker race check first observed name absence, then started a
  real owned container, and confirmed that bounded cleanup detected and removed
  the late creation. Portable unknown-outcome coverage asserts an explicit error;
  absence alone never establishes successful cleanup.
- The first updated native attempt stopped on a GitHub SSH transport timeout.
  The next complete run freshly revalidated all four refs and passed; cached
  inputs never bypassed the remote-ref check.
- `GOMAXPROCS=2 mise exec -- make -j1 check` inside the held build-gate session
  passed with exit zero: 7217 portable tests, 22 subtests, 320 vpnd tests,
  59 Bats cases, 18 provider lifecycle cases and 215 Terraform mock cases across
  four providers. Lint/security/schema/profile gates, parser compatibility,
  Terraform policies, 163 snapshots and vpnd transfer/parity checks passed.
  The canonical portable lane deselected 145 unrelated native-runtime cases;
  this does not claim execution of every native suite.
- This Mac used existing direct SOPS/age binaries for HOME-isolated fixtures and
  a temporary Terraform filesystem mirror authenticated against checked-in
  package hashes. No provider versions or validation gates were relaxed. The
  build-gate shell was exited after the complete command returned zero.
- Security review: APPROVE for the scoped local candidate lab. No private
  inputs, public listeners, production pins or production device material changed.
  Privileged local Docker remains the documented isolation boundary.

## Review corrections and remaining boundaries

Uncertain startup now polls only its preallocated name within one deadline;
observed creation is removed, while exhaustion explicitly reports unconfirmed
cleanup and the owned identity. Package inputs use the fixed signed snapshot.
Every invocation checks current upstream tags before cached source reuse.

The local-only source manifest lives beside the integration files. Published
`contract/` files are unchanged from main, removing the lab manifest's unintended
Android-vendoring requirement without changing contract-sync enforcement.
The producer dual-stack contract landed on main in
`1840d373acb00a9aa11073ca14db45a902f5f7f8`. Integrating that main revision
restores byte identity across all 31 non-README artifacts already published by
the Android client; the earlier eight-file drift is resolved without changing
the sync workflow. The obsolete Android mirror correction is removed from its
follow-up PR, which retains only separately authorized UI CI fixes.

The combined tree passes all 160 focused source-candidate, source-pin, version
floor, bundle schema, instruction and Make gate tests. Every executable lab
input, including the shared receipt publisher and service template, remains
byte-identical to the source used for the 183.383s native acceptance above.
Hosted run `38863940278` completed every check on combined-tree source
`47d045bc8ce3c0fae1ce4440e6af0bf31ebb9e41`: 93 successful checks, one advisory
neutral check, zero failures or active checks. Contract-sync, both native Linux
suites, full-stack/failure Molecule lanes and the required-check aggregate passed.

Production eligibility remains false. Captures cover bounded IPv4 H1/H2/H4
cases; H3/cookie behavior, IPv6 and physical Android acceptance are unclaimed.
The control tools retain the inherited `wireguard-tools v1.0.20210914` CLI label;
their source identity is the pinned v1.0.20241018 / c0b400c6 commit.
