---
task_id: "TST-1791618356595983"
change: "native-four-protocol-acceptance"
commit_sha: null
local: "required"
local_evidence: "complete affected tests, exact native cases and full source gates after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal required checks on the exact integrated implementation SHA"
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "required"
client_evidence: "real isolated consuming-client behavior named in the requirements; not host activity alone"
artifact: "required"
artifact_evidence: "validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-NATIVE-COMPLETION | TST-1791618369402905 | NEW native runner cases plus complete existing liveness and emitter suites; packet completion is required rather than socket/activity alone. | required |
| REQ-PROTO-NATIVE-LIFECYCLE | TST-1791618370981853 | Real upstream AWG on Linux TUN, recorded process identity and before/after traffic; inherited ownership fixtures remain supplemental. | required |
| REQ-PROTO-NATIVE-COMPENSATION | TST-1791618370981853 | Exact binaries, activation interruption cases, native logrotate execution and real served request log checks. | required |
| REQ-PROTO-NATIVE-HOPPING | TST-1791618372464891 | Actual nftables namespace rules, rendered systemd restrictions and native Hysteria clients; require controlled traffic witnesses. | required |
| REQ-PROTO-NATIVE-HONESTY | TST-1791618373730661 | NEW runner self-tests for failure paths and complete native CI run; no fake executable can fulfill this requirement. | required |
