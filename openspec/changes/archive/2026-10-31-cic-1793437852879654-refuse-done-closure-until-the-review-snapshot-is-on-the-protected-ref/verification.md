---
task_id: CIC-1793437852879654
change: cic-1793437852879654-refuse-done-closure-until-the-review-snapshot-is-on-the-protected-ref
commit_sha: "ab47c7fdd34689d8cecf77ac88a81e51b8ce66ed"
local: passed
local_evidence: "python3 -m pytest scripts/tests/test_taskctl.py tests/unit/test_task_contract_workflow.py: 167 passed, 45 subtests passed (seven new protected-ref cases: absent snapshot, other task ID at the path, missing ref, explicit --protected-ref, dropped closure, verify with and without --archive-ready, CLI parsing). tests/unit/test_agent_instructions.py and tests/unit/test_task_contract_workflow.py: 42 passed. make docs-check: 10 passed. ./taskctl validate: 81 tasks, 284 steps valid. make check -j 4 -k in the cloud container: 11078 pytest passed, 168 snapshots match, ansible-lint, terraform, shellcheck and validators passed; the only failures are the known container limits that touch none of the changed files (installer and tests refuse to run as root, kernel without IPv6, no locale and no vpn-bootstrap account for real ansible-playbook, two sops bats tests under an untrusted HOME)."
remote_ci: passed
remote_ci_evidence: "The implementation merged as ab47c7fdd34689d8cecf77ac88a81e51b8ce66ed (pull request 436) with scripts/tasks/taskctl.py, scripts/tests/test_taskctl.py, docs/tasks/README.md, the tasking skills and the asset lock unchanged since; the first complete main push run containing it, run 41201628097 on a2b370b9fae98529e5357028714b7ffcb7c760c2, succeeded with every job and the required-checks aggregate green, including the four pytest groups, task-contract and contract-sync. The pull-request runs on the exact pre-merge heads were cancelled by the merge and the following main pushes; the one earlier failure (contract-sync on cc8edfae) was client-side vendored-contract drift that the later run no longer shows."
dry_run: not_applicable
dry_run_evidence: taskctl lifecycle guard only; no deployment input or deploy controller changes.
staging: not_applicable
staging_evidence: No staging host is involved.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: not_applicable
client_evidence: No client artifact or contract changes.
artifact: passed
artifact_evidence: "The refreshed sha256 for .agents/skills/openspec-archive-change/SKILL.md in tools/tasking/generated-assets.lock.json is reviewed in the pull request diff and accepted by ./taskctl validate and the CI task-contract job."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1793437852879654-001 | CIC-1793437958813160 | taskctl tests for done closure against absent, stale, other-ID and present review snapshots on the protected ref; 167 passed locally | passed |
| REQ-CIC-1793437852879654-002 | CIC-1793437958813160 | taskctl tests for `verify --archive-ready` refusal and unchanged plain `verify` and dropped closure paths; passed locally | passed |
| REQ-CIC-1793437852879654-003 | CIC-1793437958813160 | taskctl tests for a missing protected ref and the `--protected-ref` override; no fetch invoked; passed locally | passed |
| REQ-CIC-1793437852879654-001 | CIC-1793437959694888 | README and skill text name the protected-ref gate; `./taskctl validate` and `make docs-check` passed with the refreshed asset lock | passed |
| REQ-CIC-1793437852879654-001 | CIC-1793437960612788 | focused pytest, `./taskctl validate`, `make docs-check` and `make check -k` observed locally; main run 41201628097 on a2b370b9 (tree contains the merged implementation unchanged) fully green | passed |
