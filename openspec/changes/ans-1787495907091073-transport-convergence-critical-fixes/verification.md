---
task_id: ANS-1787495907091073
change: ans-1787495907091073-transport-convergence-critical-fixes
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule convergence per touched role covers the fixed behavior
live: required
live_evidence: null
client: not_applicable
client_evidence: no client-facing emitter or vpnd surface changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
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
