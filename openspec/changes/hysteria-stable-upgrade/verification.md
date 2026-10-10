---
task_id: "SCR-1791618064422507"
change: "hysteria-stable-upgrade"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "required"
staging_evidence: "separately authorized bounded 48-hour candidate soak and exact rollback before promotion"
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
| REQ-PROTO-HY-VERSION | SCR-1791618069580618 | Version-consumer consistency, digest rejection and exact native parser cases; recorded execution-time refresh and staging eligibility are separate from unit fixture assertions. | required |
| REQ-PROTO-HY-VERSION | SCR-1791618072302643 | Version-consumer consistency, digest rejection and exact native parser cases; recorded execution-time refresh and staging eligibility are separate from unit fixture assertions. | required |
| REQ-PROTO-HY-TUNING | SCR-1791618070531675 | Schema boundary tests, exact binary startup under rendered sandbox, effective sysctl inspection and coordinated client configuration tests. | required |
| REQ-PROTO-HY-TUNING | SCR-1791618072302643 | Schema boundary tests, exact binary startup under rendered sandbox, effective sysctl inspection and coordinated client configuration tests. | required |
| REQ-PROTO-HY-MEASURE | SCR-1791618071381219 | NEW measured runtime target with controlled Linux network impairment and two real clients; do not silently skip required modes or substitute a fixture server. | required |
| REQ-PROTO-HY-MEASURE | SCR-1791618072302643 | NEW measured runtime target with controlled Linux network impairment and two real clients; do not silently skip required modes or substitute a fixture server. | required |
| REQ-PROTO-HY-UPGRADE | SCR-1791618071381219 | Extend real runtime-release adoption/compensation cases with exact Hysteria sockets, secure trust, Salamander and multi-port traffic; capture process identity instead of invoking only the new installed command. | required |
| REQ-PROTO-HY-UPGRADE | SCR-1791618072302643 | Extend real runtime-release adoption/compensation cases with exact Hysteria sockets, secure trust, Salamander and multi-port traffic; capture process identity instead of invoking only the new installed command. | required |
