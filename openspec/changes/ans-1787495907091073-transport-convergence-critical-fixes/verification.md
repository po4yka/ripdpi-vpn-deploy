---
task_id: "ANS-1787495907091073"
change: "ans-1787495907091073-transport-convergence-critical-fixes"
commit_sha: "bbc346415f412ab49f296db3927ff0fbefdaa8e0"
local: "blocked"
local_evidence: "2026-08-27: Rust debug/release each passed 173 tests, clippy/MSRV/deny passed; make validate and cloud-init schema passed. Full make check found two existing AWG installer fresh-directory failures under umask 077; root-cause correction and a complete rerun are pending."
remote_ci: "blocked"
remote_ci_evidence: "PR #108 is published. Expanded hosted Molecule coverage exposed runtime and scenario defects; final required-check success and main merge are still pending."
dry_run: "blocked"
dry_run_evidence: "Real strict secrets precheck passed, but SSH to all three inventory hosts timed out and Tailscale requires reauthentication. No full fleet playbook dry-run completed."
staging: "not_applicable"
staging_evidence: "no separate staging environment exists; CI molecule convergence per touched role covers the fixed behavior"
live: "blocked"
live_evidence: "No fleet convergence or live traffic/service acceptance ran: management access is unavailable. Local amd64 systemd containers on this arm64 Mac also fail pidfd_open with ENOSYS before roles execute; hosted amd64 Molecule is the runtime test lane, not live fleet proof."
client: "not_applicable"
client_evidence: "no client-facing emitter or vpnd surface changed"
artifact: "not_applicable"
artifact_evidence: "no build artifacts produced by this change"
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-WG-HOOK-PARSEABLE | ANS-1787496118906264 | split-hop-egress molecule assertion + live wg-quick up on staging-equivalent node | pending |
| REQ-EGRESS-HEALTH-GATE | ANS-1787496118906728 | warp-outbound molecule scenario with tunnel-down fixture | pending |
| REQ-SHARED-TLS-READABLE | ANS-1787496118906155 | hysteria-realm molecule shared-TLS path with real file modes | pending |
| REQ-MIRROR-PRESERVES-STATE | ANS-1787496118906173 | subscription-host molecule: revoked + .ssh survive triggered pull | pending |
| REQ-AWG-LIFECYCLE-RESTART | ANS-1787496118906083 | amneziawg molecule with stopped-instance handler flush | pending |
| REQ-CHECKMODE-SAFE-PROBES | ANS-1787496118906658 | firewall molecule under --check with UFW binary stub | pending |
| REQ-REVOCATION-CASE-INSENSITIVE | ANS-1787496118906250 | subscription-host uppercase-hash test case | pending |
| REQ-RENDERED-YAML-WELLFORMED | ANS-1787496118906948 | hysteria molecule render with fragment-bearing masquerade URL | pending |
| REQ-UNIT-DEPS-RESOLVE | ANS-1787496118906870 | amneziawg molecule unit-dependency assertion | pending |
| REQ-BOUNDED-CONNECTION-HOLD | ANS-1787496118906549 | honeypot molecule slow-reader fixture terminating at deadline | pending |

## Gates

- Local: per-role molecule scenarios, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: `make dry-run` completes on a UFW-preinstalled target.
- Live: one filtered-path node re-converged; split-hop bring-up and mirror pull observed.

## 2026-08-27 review

The original implementation was reopened after review found executable defects.
Local regressions do not substitute for the dry-run, staging, live, or hosted-CI categories above.
Archive and terminal closure remain blocked until all required evidence is complete.

### Shared local checks on the reviewed source

- `python3 -m pytest tests/unit -q`: 995 passed, 2 existing skips; one honeypot thread shutdown warning. The warning was reproduced only when the test fixture closes its listener while a daemon accept thread is running; it was not observed before cleanup. The stale collected-count documentation was corrected before this successful run.
- `bats tests/bats/`: 55 passed.
- `make tf-test`: 79 provider mock tests passed.
- `make snapshot-check`: 102 templates matched.
- `make validate`, actionlint, shellcheck, cargo-deny and Rust 1.88 MSRV check passed. YAML lint has one existing workflow line-length warning.
- Render, AWG version floor, Xray guards, secrets coverage, deploy-profile, example secrets schema and bundle schema checks passed.
- `make check` did not pass: its Docker cloud-init step lost the Colima connection. Per-role Molecule did not run. These checks must be rerun in a working container environment.
