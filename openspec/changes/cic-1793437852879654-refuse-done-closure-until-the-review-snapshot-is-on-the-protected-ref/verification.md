---
task_id: CIC-1793437852879654
change: cic-1793437852879654-refuse-done-closure-until-the-review-snapshot-is-on-the-protected-ref
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: taskctl lifecycle guard only; no deployment input or deploy controller changes.
staging: not_applicable
staging_evidence: No staging host is involved.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: not_applicable
client_evidence: No client artifact or contract changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1793437852879654-001 | CIC-1793437958813160 | taskctl tests for done closure against absent, stale, other-ID and present review snapshots on the protected ref | required |
| REQ-CIC-1793437852879654-002 | CIC-1793437958813160 | taskctl tests for `verify --archive-ready` refusal and unchanged plain `verify` and dropped archive paths | required |
| REQ-CIC-1793437852879654-003 | CIC-1793437958813160 | taskctl tests for a missing protected ref and the `--protected-ref` override; no fetch invoked | required |
| REQ-CIC-1793437852879654-001 | CIC-1793437959694888 | README and skill text name the protected-ref gate; `./taskctl validate` accepts the refreshed asset lock | required |
| REQ-CIC-1793437852879654-001 | CIC-1793437960612788 | focused pytest, `./taskctl validate`, `make task-check`, `make docs-check`, exact-head CI run | required |
