---
task_id: ANS-1787495907091073
change: ans-1787495907091073-transport-convergence-critical-fixes
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
staging: not_applicable
staging_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
live: not_applicable
live_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
client: not_applicable
client_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
artifact: not_applicable
artifact_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-WG-HOOK-PARSEABLE | ANS-1787496118906264 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-EGRESS-HEALTH-GATE | ANS-1787496118906728 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-SHARED-TLS-READABLE | ANS-1787496118906155 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-MIRROR-PRESERVES-STATE | ANS-1787496118906173 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-AWG-LIFECYCLE-RESTART | ANS-1787496118906083 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-CHECKMODE-SAFE-PROBES | ANS-1787496118906658 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-REVOCATION-CASE-INSENSITIVE | ANS-1787496118906250 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-RENDERED-YAML-WELLFORMED | ANS-1787496118906948 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-UNIT-DEPS-RESOLVE | ANS-1787496118906870 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-BOUNDED-CONNECTION-HOLD | ANS-1787496118906549 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |

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
