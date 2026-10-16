---
task_id: "MON-1791618056169855"
change: "topology-authenticated-probes"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


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
