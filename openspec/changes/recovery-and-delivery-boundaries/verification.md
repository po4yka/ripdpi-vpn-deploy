---
task_id: OPS-1792305989358872
change: recovery-and-delivery-boundaries
commit_sha: null
local: required
local_evidence: Focused unit, Bats, Ansible lint and snapshot checks pass; full make check is queued behind the shared build slot.
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Both synthetic restore dry-run paths include current SSH, Tailnet and deployment admission inputs; 26 Bats cases pass.
staging: not_applicable
staging_evidence: User prohibits deployment; source-only remediation.
live: not_applicable
live_evidence: No deployment or production access is authorized.
client: not_applicable
client_evidence: Producer refusal is tested locally; real client deployment is outside scope.
artifact: required
artifact_evidence: Three reviewed template snapshots; real age and restic preservation tests; clean structured review and secret prescan.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DR-ENV-ISOLATION | OPS-1792306162286391 | Reserved alias entrypoint regressions | Pass locally |
| REQ-DR-STATE-ATOMIC | OPS-1792306163221571 | Real age synthetic failure and preservation tests | Pass locally |
| REQ-DR-SHARE-READ | OPS-1792306164184160 | Actual Ansible mode repair and native UID access | Portable checks pass; required native CI pending |
| REQ-DR-HOPPING-ADMISSION | OPS-1792306165929686 | Real materialization format-boundary tests | Pass locally |
| REQ-DR-RESTORE-COMPLETE | OPS-1792306167846329 | Rendered drill with real restic missing-input cases | Pass locally |
| REQ-DR-MIRROR-STOP | OPS-1792306168913886 | Toggle, check-mode, idempotency and retained-authority tests | Portable checks pass; required native CI pending |
| REQ-DR-PROCEDURE | OPS-1792306169855109 | Recovery dry-run and current prerequisite contracts | Pass locally |
| REQ-DR-DHCPV6 | OPS-1792306170781535 | Portable admission and isolated native UDP tests | Portable checks pass; required native CI pending |

## Source review

Security review: APPROVE. Exact timer retirement preserves private authority and
administrative masks. Share mode repair does not follow retained symlink targets.
DHCPv6 permits only the admitted uplink, local client ports and scoped server
addresses. State recovery validates a private candidate before atomic publication.

The structured local review and TruffleHog prescan pass with no accepted actionable
findings. Full source CI and Linux native acceptance remain required before merge.
