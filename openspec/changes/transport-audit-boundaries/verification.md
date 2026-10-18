---
task_id: SEC-1792306834441683
change: transport-audit-boundaries
commit_sha: 40471477976336f87364a14910d9ad1e5d416874
local: required
local_evidence: Focused AWG/WARP passed 225 cases; integrated Hysteria/export/liveness/ECH passed 191 cases and the final emitter suite passed 38. DNS admission/lifecycle/schema passed 195 cases. Actual Ubuntu nftables 1.0.9 and pinned Python 3.12 passed both strict-overlay family cases and split-hop/retirement cases with no skips. The native split-hop failure exposed the stale OUTPUT interface; both guards now use final IPv4 POSTROUTING, with successful encrypted traffic, stopped-tunnel denial, recovery, repeated table replacement and canonical guard coverage. Complete current-source gates remain required.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source repair only; no private deployment inputs.
staging: not_applicable
staging_evidence: No runtime rollout or promotion is part of this change.
live: not_applicable
live_evidence: No provider, real host or credential operations are authorized by this source task.
client: required
client_evidence: Four local native packet and retirement cases passed without skips; hosted hopping and complete protocol acceptance remain required. Physical recipient acceptance is outside scope.
artifact: required
artifact_evidence: All 165 rendered templates match reviewed snapshots. Exact changed policy and service output reviewed. Actual nftables 1.0.9 proved stable rules after three loads and replaced changed SNAT. Structured review has no accepted P0-P2 findings; security review APPROVE. The DNS role remains a research integration.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HOPPING | SEC-1792306951999782 | Focused regression and required source/native checks pending | required |
| REQ-AUDIT-SPLIT | SEC-1792306951999782 | Focused regression and required source/native checks pending | required |
| REQ-AUDIT-STRICT | SEC-1792306951999782 | Focused regression and required source/native checks pending | required |
| REQ-AUDIT-EXPORT | SEC-1792306952664722 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-AWG | SEC-1792306953297349 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-DNS | SEC-1792306953944270 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-WARP | SEC-1792306953297349 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-DOCS | SEC-1792306954609366 | Focused regression and required source/native checks pending | required |
