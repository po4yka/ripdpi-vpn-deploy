---
task_id: "SCR-1791617975137354"
change: "reality-target-validation"
commit_sha: "593a518be0f34604b24a5212a412f4c96b9d112a"
local: "required"
local_evidence: "complete affected suites plus the named native positive/failure cases after implementation"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "not_applicable"
staging_evidence: "source-only scope; isolated native behavior is required, and any external rollout is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "not_applicable"
client_evidence: "External clients removed by owner; real local TLS peers remain required under local evidence."
artifact: "required"
artifact_evidence: "rendered contracts and redacted requirement-specific exact-source artifacts after implementation"
---

# Verification

## Requirement evidence

The local identity and bounded-process rows below have observed source evidence. Native owned-public-path and full source gates remain required; checked source steps do not certify these missing results.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RTV-IDENTITY | SCR-1791617985610703 | `tests/unit/test_validate_reality_target.py`: 20 passed in 8.01s at source `593a518b`; actual local TLS exact/wildcard identity, trust/SAN failures and redacted reports. | passed |
| REQ-PROTO-RTV-IDENTITY | SCR-1791617989032738 | NEW test_validate_reality_target.py with controlled exact wildcard deep-label mixed comma/space duplicate and empty-name cases. | required |
| REQ-PROTO-RTV-DEADLINES | SCR-1791617986915903 | Actual stalled TLS, aggregate bounds and forked-descendant cleanup in the same 20-case run; monitor/supervision regression run passed 57 overlapping cases, retaining accepted budgets and replacing timed-out observations. | passed |
| REQ-PROTO-RTV-DEADLINES | SCR-1791617989032738 | NEW real subprocess deadline and child-cleanup tests for DNS TLS HTTP and multi-name aggregate work; retain current monitor state tests. | required |
| REQ-PROTO-RTV-CLAIMS | SCR-1791617987865403 | NEW truthful report/available-client tests; inspect real handshake execution boundary rather than using a User-Agent assertion as proof. | required |
| REQ-PROTO-RTV-CLAIMS | SCR-1791617989032738 | NEW truthful report/available-client tests; inspect real handshake execution boundary rather than using a User-Agent assertion as proof. | required |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617986915903 | NEW owned public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | required |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617987865403 | NEW owned public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | required |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617989032738 | NEW owned public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | required |
