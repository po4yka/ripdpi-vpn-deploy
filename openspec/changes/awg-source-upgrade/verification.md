---
task_id: SCR-1791618073850409
change: awg-source-upgrade
commit_sha: 1148aa10fd754f046f66c166a78e313b5cd48273
local: passed
local_evidence: Complete make check passed with 7217 portable tests, 320 vpnd tests, 59 Bats cases and four Terraform mock suites; 50 focused tests and updated native ARM64 lab passed.
remote_ci: not_applicable
remote_ci_evidence: Owner requires local implementation acceptance; supplementary contract-sync has independent client drift documented below.
dry_run: not_applicable
dry_run_evidence: No inventory, private inputs or deployed hosts are used.
staging: not_applicable
staging_evidence: External 48-hour soak is outside the revised local candidate scope.
live: not_applicable
live_evidence: Production defaults remain unchanged; no rollout is part of this task.
client: passed
client_evidence: Real baseline/candidate Linux ARM64 cores passed all six matrices and warm/failure transactions; physical Android remains excluded and unclaimed.
artifact: passed
artifact_evidence: Exact pairs rebuilt with fixed signed Ubuntu package inputs and checksum-pinned Go; image 29916c582031af8f passed the disconnected lab with owned removal.
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
| REQ-PROTO-AWG-VERSION | SCR-1791618078367215 | Both exact source pairs rebuilt on ARM64 with checksum-pinned Go and fixed signed Ubuntu inputs; fresh upstream tag checks precede warm-cache reuse. | passed |
| REQ-PROTO-AWG-WIRE | SCR-1791618079169597 | Six real mixed/new pairing and shape cases, captured H1/H2/H4, sustained bidirectional TCP/UDP/DNS and three reconnects per case; complete lab passed in 183.383s. | passed |
| REQ-PROTO-AWG-ADOPT | SCR-1791618080142425 | Two owned daemons adopted executable/sandbox changes, real compiler/readiness failures compensated, unchanged publication preserved PIDs and the third tunnel retained traffic. | passed |
| REQ-PROTO-AWG-LOCAL | SCR-1791618081446678 | Local daemon admission, explicit public inputs, disconnected runtime, actual owned removal and delayed-creation cleanup; complete make check returned zero. | passed |

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
At client commit `aafb448a57e74cf0bc1804553271733ea705407b`, all 31 published
files exist but eight existing bundle schema/golden/negative-fixture blob hashes
differ from main. This independent cross-repository gap remains supplementary
CI evidence, not a reason to alter client payloads or relax checks here.

Production eligibility remains false. Captures cover bounded IPv4 H1/H2/H4
cases; H3/cookie behavior, IPv6 and physical Android acceptance are unclaimed.
The control tools retain the inherited `wireguard-tools v1.0.20210914` CLI label;
their source identity is the pinned v1.0.20241018 / c0b400c6 commit.
