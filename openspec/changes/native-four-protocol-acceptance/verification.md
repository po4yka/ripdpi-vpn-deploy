---
task_id: "TST-1791618356595983"
change: "native-four-protocol-acceptance"
commit_sha: null
local: "required"
local_evidence: "complete affected tests, exact native cases and full source gates after implementation"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: "required"
artifact_evidence: "validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA"
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-NATIVE-COMPLETION | TST-1791618369402905 | NEW native runner cases plus complete existing liveness and emitter suites; packet completion is required rather than socket/activity alone. | required |
| REQ-PROTO-NATIVE-LIFECYCLE | TST-1791618370981853 | Real upstream AWG on Linux TUN, recorded process identity and before/after traffic; inherited ownership fixtures remain supplemental. | required |
| REQ-PROTO-NATIVE-COMPENSATION | TST-1791618370981853 | Exact binaries, activation interruption cases, native logrotate execution and real served request log checks. | required |
| REQ-PROTO-NATIVE-HOPPING | TST-1791618372464891 | Actual nftables namespace rules, rendered systemd restrictions and native Hysteria clients; require controlled traffic witnesses. | required |
| REQ-PROTO-NATIVE-HONESTY | TST-1791618373730661 | NEW runner self-tests for failure paths and complete native CI run; no fake executable can fulfill this requirement. | required |
