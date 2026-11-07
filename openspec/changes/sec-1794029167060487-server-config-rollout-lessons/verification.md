---
task_id: SEC-1794029167060487
change: sec-1794029167060487-server-config-rollout-lessons
commit_sha: pending
local: passed
local_evidence: "Integrated branch: 706 tests passed across every touched unit test file plus agent-instruction and docs-index tests; make snapshot-check 184 templates matched. After review fixes: 419 passed in the agent render, bootstrap-tailnet, tailnet-management and operator files; ansible-lint clean on the agent tasks. Molecule and nft parsing did not run locally."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request.
dry_run: required
dry_run_evidence: Pending agent lifecycle check on the nodes after merge.
staging: not_applicable
staging_evidence: Production nodes are updated through the ordinary reviewed lifecycle.
live: required
live_evidence: Pending the monitoring rollout that drops the hand-set self-steal flag, and the observer foundation input.
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-RH-SELF-STEAL-SERIES | SEC-1794030485989065 | Render tests driven by the stat result, follow on a symlinked leaf; adapter reports collection failure for an unreadable chain | required |
| REQ-SEC-RH-OBSERVER-EGRESS | SEC-1794031569118515 | Foundation render and validation tests; rendered rules equal the live observer rules | required |
| REQ-SEC-RH-OPERATOR-REFUSALS | SEC-1794032178100678 | Operator failed-task, ignored-failure, node-lock-busy and missing-inventory tests | passed |
