---
task_id: SCR-1791618073850409
change: awg-source-upgrade
commit_sha: 99f730fbcae34134cedcc22cd80694c1c707f760
local: passed
local_evidence: Full make check passed (7206 portable tests, 320 vpnd tests, 59 Bats cases, four Terraform providers), plus 45 focused tests, Ruff, 163 snapshots and complete ARM64 source-candidate lab.
remote_ci: not_applicable
remote_ci_evidence: Owner requires implementation acceptance without external infrastructure; PR checks remain supplementary.
dry_run: not_applicable
dry_run_evidence: No inventory, private inputs or deployed hosts are used.
staging: not_applicable
staging_evidence: External 48-hour soak explicitly excluded from this revised local candidate task.
live: not_applicable
live_evidence: Production defaults remain unchanged; no rollout is part of this task.
client: passed
client_evidence: Exact real baseline and candidate Linux cores with generated local keys and authenticated bidirectional traffic; physical Android is excluded and unclaimed.
artifact: passed
artifact_evidence: Both exact source pairs built with checksum-pinned Go 1.27.1; full disconnected Linux ARM64 lab passed with owned container removal.
---

# Verification

## Scope revision

The owner required local completion without external infrastructure on
2026-10-15 and authorized revisions to task descriptions and acceptance.
The resulting deliverable is a real local source-upgrade candidate lab.
Physical Android, external staging and production promotion are excluded,
not treated as equivalent to Docker or automatically completed.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-VERSION | SCR-1791618078367215 | Exact candidate/control tags and commits; checksum-pinned Go; both real pairs built on Linux ARM64. | passed |
| REQ-PROTO-AWG-WIRE | SCR-1791618079169597 | Six actual mixed/new pairing and shape cases, captures, reconnects and bidirectional TCP/UDP/DNS; complete lab passed in 176.624s. | passed |
| REQ-PROTO-AWG-ADOPT | SCR-1791618080142425 | Two actual owned daemons, executable/sandbox adoption, failed build/readiness compensation, idempotency and independent third tunnel; complete lab passed. | passed |
| REQ-PROTO-AWG-LOCAL | SCR-1791618081446678 | Local-only daemon admission, explicit public build context, disconnected runtime and owned cleanup; full make check returned zero. | passed |

## Observed local checks

- Focused portable source-pins, version-floor, source-integrity and launcher
  tests: 45 passed, including startup-timeout ownership cleanup.
- Ruff passed for every new Python file; staged gitleaks reported no leaks.
- `mise exec -- make snapshot-check`: all 163 template snapshots match.
- OpenSpec strict validation passed after the local-scope rewrite.
- `make test-awg-source-candidate` inside the machine-wide build-gate session:
  complete real Linux ARM64 lab passed in 176.624s with no skipped cases. Image
  `ripdpi-awg-source-candidate:c3ba0aa65c21ec0c` bound the exact source/bundle inputs.
  Both source pairs compiled; all six pairing/profile cases passed captures,
  sustained bidirectional TCP/UDP/DNS and three client reconnects. Two owned
  daemons adopted candidate bytes and a real UTS sandbox, real compiler and
  authenticated-readiness failures compensated, unchanged publication preserved
  PIDs, and the independent tunnel retained its process and traffic.
- The owned lab container was removed and the command returned zero. Initial
  attempts exposed Buildx CLI, artifact-route, startup-bus and reconnect-probe
  prerequisites; these were corrected without a skipped or weakened wire case.
- Control tools report the inherited `wireguard-tools v1.0.20210914` CLI label;
  its fork source identity is the pinned v1.0.20241018 / c0b400c6 commit. Both Go
  binaries report their exact selected tags and candidate tools report v3.1.20260812.
- The first aggregate `make check` failed on GitHub HTTPS provider acquisition
  (validation metadata for hcloud and the Scaleway package download). No gate
  was skipped. All four existing Darwin ARM64 provider packages were copied
  read-only into a temporary filesystem mirror after their complete package
  `h1` hashes matched the checked-in lock files. Terraform accepted the pinned
  mirror. The next sequential run reached Python tests, where HOME-isolated
  SOPS fixtures rejected the workstation mise shim configuration. That run was
  interrupted; the unchanged first failing test passed with existing direct
  SOPS/age binary directories in PATH and Python 3.12. The full rerun with this
  corrected tool environment passed with exit zero.
- `mise exec -- make -j1 check` inside the machine-wide build gate passed:
  7206 portable tests and 22 subtests, 320 vpnd tests, 59 Bats cases, 18 provider
  lifecycle tests, all four Terraform provider mock suites (215 cases),
  Terraform policy checks, lint/security/schema/profile gates and 163 snapshots.
  The canonical portable lane deselected 145 native-runtime tests by design;
  the separate real AWG source-candidate lab passed in full, and this does not
  claim execution of every unrelated native suite. The held build-gate shell
  was exited after the complete gate returned zero.
- Security review: APPROVE for this local candidate lab. No private inputs,
  public listeners, production pins or per-device production material changed.
  Privileged local Docker remains the documented lab isolation boundary.
- Production eligibility remains false. Captures cover H1/H2/H4 on the bounded
  IPv4 Linux matrix; physical Android and external-path acceptance are unclaimed.
