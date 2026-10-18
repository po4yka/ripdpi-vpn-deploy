---
task_id: SEC-1792306834441683
change: transport-audit-boundaries
commit_sha: 365b08b680963d1bdd8c879b005467e24913b482
local: passed
local_evidence: Focused AWG/WARP passed 225 cases; integrated Hysteria/export/liveness/ECH passed 191 cases and the final emitter suite passed 38. DNS admission/lifecycle/schema passed 195 cases; ownership and admission passed 51. Network portable checks passed 50 cases. The hopping fixture regression bundle passed 51 cases. Four Ubuntu native packet and retirement cases passed without skips. Source gates and 165 template snapshots passed. The complete Mac make check stopped after 1009 portable passes at an unchanged fake-SOPS fixture hang; it is not a whole-gate pass. The two affected registry cases passed separately on Python 3.12.13 and 3.12.15. Protected Linux CI run 39122200716 passed on merged source 365b08b680963d1bdd8c879b005467e24913b482.
remote_ci: passed
remote_ci_evidence: Protected PR 334 merged as 365b08b680963d1bdd8c879b005467e24913b482 with the same tree as tested head 7ff0e83c5dfdf3999b410a6783f1579fdc269ec6. PR CI run 39117790356 passed. Post-merge CI run 39122200716 completed successfully on that exact main SHA, including native runtime integration, both native transport acceptance partitions and all three four-transport partitions. All nine required protected-main checks passed; CodeQL, REALITY target validation, release-please and scorecard workflows also passed.
dry_run: not_applicable
dry_run_evidence: Source repair only; no private deployment inputs.
staging: not_applicable
staging_evidence: No runtime rollout or promotion is part of this change.
live: not_applicable
live_evidence: No provider, real host or credential operations are authorized by this source task.
client: passed
client_evidence: Four local native packet and retirement cases passed without skips. The exact hopping fixture methods passed on Linux with checksum-verified Hysteria 2.13.0, Salamander, IPv4/IPv6 multi-port observation, fresh authenticated HTTPS delivery and unrelated UDP controls. The exact hopping methods also passed with pinned Hysteria 2.8.2. Hosted CI run 39117790356 passed native runtime integration, both native transport acceptance partitions and all three four-transport partitions at head 7ff0e83c5dfdf3999b410a6783f1579fdc269ec6. The same native suites passed again on main in CI run 39122200716. Physical recipient acceptance is outside scope.
artifact: passed
artifact_evidence: All 165 rendered templates match reviewed snapshots. Exact changed policy and service output reviewed. Actual nftables 1.0.9 proved stable rules after three loads and replaced changed SNAT. Structured source and hopping-fixture reviews have no accepted P0-P2 findings; security review APPROVE. The DNS role remains a research integration.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HOPPING | SEC-1792306951999782 | Portable regressions, real IPv4/IPv6 hopping methods and protected-main core/recovery acceptance passed | passed |
| REQ-AUDIT-SPLIT | SEC-1792306951999782 | Real encrypted traffic, stopped-tunnel denial, recovery, table replacement and guarded retirement passed; protected-main native CI passed | passed |
| REQ-AUDIT-STRICT | SEC-1792306951999782 | Real IPv4/IPv6 strict overlay packet cases and protected-main native CI passed | passed |
| REQ-AUDIT-EXPORT | SEC-1792306952664722 | Focused endpoint metadata and bandwidth regressions, source review and protected-main CI passed | passed |
| REQ-AUDIT-AWG | SEC-1792306953297349 | Handshake-size and effective-header admission regressions, source review and protected-main CI passed | passed |
| REQ-AUDIT-DNS | SEC-1792306953944270 | Key, endpoint, explicit echo mode and ownership-first admission regressions plus protected-main CI passed; research data-plane acceptance stays outside scope | passed |
| REQ-AUDIT-WARP | SEC-1792306953297349 | Armored-key format and signed-by regressions, source review and protected-main CI passed | passed |
| REQ-AUDIT-DOCS | SEC-1792306954609366 | Reviewed operator contracts, source/native gates, protected PR merge and all exact-main required checks passed | passed |
