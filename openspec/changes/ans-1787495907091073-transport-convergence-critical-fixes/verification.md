---
task_id: "ANS-1787495907091073"
change: "ans-1787495907091073-transport-convergence-critical-fixes"
commit_sha: "984b4528b634b4b48fa74fac0b4cbb22b8b7b887"
local: "passed"
local_evidence: "Full build-gate -- make -j1 check passed under umask 077: 1024 Python tests passed, 1 existing live-scanner placeholder skipped; 55 BATS; 173 Rust release tests; 79 Terraform mocks; 102 snapshots. Release clippy, Rust 1.88 MSRV, cargo deny, Docker cloud-init schema, make validate, lint/render/schema gates passed. Separate Rust debug suite: 173 passed."
remote_ci: "passed"
remote_ci_evidence: "PR #108, exact implementation SHA 984b4528b634b4b48fa74fac0b4cbb22b8b7b887: CI run 33069634871 completed success; 62 successful checks and one neutral Trivy SARIF report, with both image scan jobs successful. All required checks and expanded hosted Molecule scenarios passed. This is PR evidence; protected main merge remains a delivery step."
dry_run: not_applicable
dry_run_evidence: "Controller-wide dry-run is consolidated in OPS-1787496414433523."
staging: "not_applicable"
staging_evidence: "no separate staging environment exists; CI molecule convergence per touched role covers the fixed behavior"
live: not_applicable
live_evidence: "One-node and fleet protocol acceptance is consolidated in TST-1787850553468536 and OPS-1787496414433523."
client: "not_applicable"
client_evidence: "no client-facing emitter or vpnd surface changed"
artifact: "not_applicable"
artifact_evidence: "no build artifacts produced by this change"
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-WG-HOOK-PARSEABLE | ANS-1787496118906264 | split-hop-egress molecule assertion + live wg-quick up on staging-equivalent node | passed |
| REQ-EGRESS-HEALTH-GATE | ANS-1787496118906728 | warp-outbound molecule scenario with tunnel-down fixture | passed |
| REQ-SHARED-TLS-READABLE | ANS-1787496118906155 | hysteria-realm molecule shared-TLS path with real file modes | passed |
| REQ-MIRROR-PRESERVES-STATE | ANS-1787496118906173 | subscription-host molecule: revoked + .ssh survive triggered pull | passed |
| REQ-AWG-LIFECYCLE-RESTART | ANS-1787496118906083 | amneziawg molecule with stopped-instance handler flush | passed |
| REQ-CHECKMODE-SAFE-PROBES | ANS-1787496118906658 | firewall molecule under --check with UFW binary stub | passed |
| REQ-REVOCATION-CASE-INSENSITIVE | ANS-1787496118906250 | subscription-host uppercase-hash test case | passed |
| REQ-RENDERED-YAML-WELLFORMED | ANS-1787496118906948 | hysteria molecule render with fragment-bearing masquerade URL | passed |
| REQ-UNIT-DEPS-RESOLVE | ANS-1787496118906870 | amneziawg molecule unit-dependency assertion | passed |
| REQ-BOUNDED-CONNECTION-HOLD | ANS-1787496118906549 | honeypot molecule slow-reader fixture terminating at deadline | passed |

## Gates

- Local: per-role molecule scenarios, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: `make dry-run` completes on a UFW-preinstalled target.
- Live: one filtered-path node re-converged; split-hop bring-up and mirror pull observed.

### Final checks on the reviewed implementation

- `build-gate -- make -j1 check` passed under restrictive umask 077: Python 1024 passed, 1 existing unconditional live-scanner placeholder skipped; BATS 55 passed; Rust release 173 passed; Terraform mocks 79 passed; 102 snapshots matched.
- Release clippy, Rust 1.88 locked MSRV, cargo deny, cloud-init schema in Docker, and all render/schema/lint gates passed. `make validate` also passed after the final role edit. Rust debug independently passed 173 tests.
- [Hosted CI run 33069634871](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/33069634871) passed on `984b4528b634b4b48fa74fac0b4cbb22b8b7b887`. PR #108 has 62 successful checks and one neutral Trivy SARIF report; both image scan jobs succeeded. Expanded Molecule scenarios executed on hosted amd64 Linux.
- Earlier umask, role runtime, fixture, and container validation failures are superseded by these successful reruns. Local amd64 systemd Molecule on this arm64 Mac remains unavailable (`pidfd_open` ENOSYS); hosted Molecule is the observed role-runtime evidence, not production evidence.
- Existing cargo-deny duplicate-dependency warnings and one workflow line-length warning remain. The skipped live scanner test is not counted as acceptance.

## Remaining acceptance blockers

Implementation and local/hosted regression gates passed. Archive and terminal closure remain blocked by the dry-run, staging (where required), and live categories above. SSH to all three configured production hosts timed out; this Mac requires Tailscale reauthentication. No production deployment ran.

### Residual P2 review finding

Changing `share_hysteria_tls` from true to false does not revoke the existing hysteria supplementary-group membership or remove shared-certificate symlinks (`ansible/roles/hysteria-realm/tasks/main.yml`, TLS user/group setup). The false mode currently assumes separately managed TLS; a safe migration needs an explicit replacement-certificate and restart contract. The cold-start append/groups correction does not claim to solve this transition.

## Proportional verification decision — 2026-09-06

Verification follows the portfolio proportional-evidence policy. Source closure does not claim staging or live operation; any delegated operational requirement remains open in the task named in the front matter evidence above.
