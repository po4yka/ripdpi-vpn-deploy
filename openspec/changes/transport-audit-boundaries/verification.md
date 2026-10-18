---
task_id: SEC-1792306834441683
change: transport-audit-boundaries
commit_sha: null
local: required
local_evidence: Focused AWG/WARP passed 225 cases; Hysteria/liveness passed 185 cases with official sing-box 1.14.3; DNS admission/lifecycle/schema passed 195 cases. Network and instruction checks passed 17 cases after check-mode repair. Source validation, linters, Terraform tests, schemas, 165 snapshots and parser compatibility passed. The portable run was interrupted at 29 percent for main integration; a baseline Homebrew base64 CR failure reproduced on clean source and passed with the system executable. Full exact-head CI remains required.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source repair only; no private deployment inputs.
staging: not_applicable
staging_evidence: No runtime rollout or promotion is part of this change.
live: not_applicable
live_evidence: No provider, real host or credential operations are authorized by this source task.
client: required
client_evidence: Native synthetic packet and export regressions required; physical recipient acceptance is outside scope.
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
