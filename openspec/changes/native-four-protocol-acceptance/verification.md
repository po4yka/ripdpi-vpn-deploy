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

Rows distinguish observed local acceptance from evidence still required. The complete runner and exact integrated CI result remain required before closure.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-NATIVE-COMPLETION | TST-1791618369402905 | Isolated Linux ARM64 at c7346609e101116f09735b756bec73cab70aa47c: all nine completion cases passed with real admitted engine digests, including HTTPS byte completion, TCP/UDP/DNS, wrong credentials/TLS, both XHTTP listener selections, two-instance binding and dual-stack AWG. The runner confirmed cleanup after the later lifecycle failure; 146 affected portable liveness/logrotate tests also passed. | local observed; complete exact-SHA CI pending |
| REQ-PROTO-NATIVE-LIFECYCLE | TST-1791618370981853 | Real upstream AWG on Linux TUN, recorded process identity and before/after traffic; inherited ownership fixtures remain supplemental. | required |
| REQ-PROTO-NATIVE-COMPENSATION | TST-1791618370981853 | Exact binaries, activation interruption cases, native logrotate execution and real served request log checks. | required |
| REQ-PROTO-NATIVE-HOPPING | TST-1791618372464891 | Local isolated Linux ARM64: both selected hopping cases passed (2 passed, zero skips), applying complete firewall renders, observing distinct ingress ports, checking the actual daemon lacks NET_ADMIN, preserving foreign UDP destinations/table and converging ordinary listener twice. | local observed; exact-SHA CI pending |
| REQ-PROTO-NATIVE-HONESTY | TST-1791618373730661 | NEW runner self-tests for failure paths and complete native CI run; no fake executable can fulfill this requirement. | required |
