---
task_id: SEC-1792306834441683
change: transport-audit-boundaries
commit_sha: 4f19b03939d1df21cf1eb983f623b173f07e16e4
local: passed
local_evidence: Focused AWG/WARP passed 225 cases; integrated Hysteria/export/liveness/ECH passed 191 cases and the final emitter suite passed 38. DNS admission/lifecycle/schema passed 195 cases; ownership and admission passed 51. Network portable checks passed 50 cases. The hopping fixture regression bundle passed 51 cases. Four Ubuntu native packet and retirement cases passed without skips. Source gates and 165 template snapshots passed. The complete Mac make check stopped after 1009 portable passes at an unchanged fake-SOPS fixture hang; it is not a whole-gate pass. The two affected registry cases passed separately on Python 3.12.13 and 3.12.15. Exact-head protected Linux CI remains required.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source repair only; no private deployment inputs.
staging: not_applicable
staging_evidence: No runtime rollout or promotion is part of this change.
live: not_applicable
live_evidence: No provider, real host or credential operations are authorized by this source task.
client: required
client_evidence: Four local native packet and retirement cases passed without skips. The exact hopping fixture methods passed on Linux with checksum-verified Hysteria 2.13.0, Salamander, IPv4/IPv6 multi-port observation, fresh authenticated HTTPS delivery and unrelated UDP controls. Complete hosted upgrade and protocol acceptance remain required. Physical recipient acceptance is outside scope.
artifact: passed
artifact_evidence: All 165 rendered templates match reviewed snapshots. Exact changed policy and service output reviewed. Actual nftables 1.0.9 proved stable rules after three loads and replaced changed SNAT. Structured source and hopping-fixture reviews have no accepted P0-P2 findings; security review APPROVE. The DNS role remains a research integration.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HOPPING | SEC-1792306951999782 | Portable regression and exact real IPv4/IPv6 hopping methods passed; complete hosted acceptance pending | local-pass |
| REQ-AUDIT-SPLIT | SEC-1792306951999782 | Real encrypted traffic, stopped-tunnel denial, recovery, table replacement and guarded retirement passed; protected CI pending | local-pass |
| REQ-AUDIT-STRICT | SEC-1792306951999782 | Real IPv4/IPv6 strict overlay packet cases passed; protected CI pending | local-pass |
| REQ-AUDIT-EXPORT | SEC-1792306952664722 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-AWG | SEC-1792306953297349 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-DNS | SEC-1792306953944270 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-WARP | SEC-1792306953297349 | Focused portable regressions and reviewed source passed; protected CI pending | local-pass |
| REQ-AUDIT-DOCS | SEC-1792306954609366 | Focused regression and required source/native checks pending | required |
