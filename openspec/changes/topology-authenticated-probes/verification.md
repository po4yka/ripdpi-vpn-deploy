---
task_id: "MON-1791618056169855"
change: "topology-authenticated-probes"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-PROBE-TOPOLOGY | MON-1791618060162436 | Executable manifest/verify/watchdog regression matrix for cohort-only, custom single-interface and multiple-instance layouts, plus XHTTP backend-only outage and shared-owner cases. | required |
| REQ-PROTO-PROBE-TOPOLOGY | MON-1791618061966295 | Executable manifest/verify/watchdog regression matrix for cohort-only, custom single-interface and multiple-instance layouts, plus XHTTP backend-only outage and shared-owner cases. | required |
| REQ-PROTO-PROBE-AUTH | MON-1791618060162436 | Exact Hysteria and supported client runtime tests with real certificates and obfuscation on/off; exact AWG and Xray authenticated positive and credential-negative cases. | required |
| REQ-PROTO-PROBE-AUTH | MON-1791618061120158 | Exact Hysteria and supported client runtime tests with real certificates and obfuscation on/off; exact AWG and Xray authenticated positive and credential-negative cases. | required |
| REQ-PROTO-PROBE-AUTH | MON-1791618061966295 | Exact Hysteria and supported client runtime tests with real certificates and obfuscation on/off; exact AWG and Xray authenticated positive and credential-negative cases. | required |
| REQ-PROTO-PROBE-OWNERSHIP | MON-1791618061120158 | Preserve smoke cleanup and watchdog notification/state suites; add actual stalled-client and exact recovery-target cases with verbose synthetic-secret leak assertions. | required |
| REQ-PROTO-PROBE-OWNERSHIP | MON-1791618062766877 | Preserve smoke cleanup and watchdog notification/state suites; add actual stalled-client and exact recovery-target cases with verbose synthetic-secret leak assertions. | required |
| REQ-PROTO-PROBE-EVIDENCE | MON-1791618061966295 | Add exact binary Linux systemd/TUN/QUIC cases to the native lane; retain existing controller notification and retirement tests as distinct proof. Schema-test redacted evidence and stale-health replacement. | required |
| REQ-PROTO-PROBE-EVIDENCE | MON-1791618062766877 | Add exact binary Linux systemd/TUN/QUIC cases to the native lane; retain existing controller notification and retirement tests as distinct proof. Schema-test redacted evidence and stale-health replacement. | required |
