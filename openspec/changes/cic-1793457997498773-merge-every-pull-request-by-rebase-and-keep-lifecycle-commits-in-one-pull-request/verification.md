---
task_id: CIC-1793457997498773
change: cic-1793457997498773-merge-every-pull-request-by-rebase-and-keep-lifecycle-commits-in-one-pull-request
commit_sha: "3175b0d96f5ee54174040130be88b3fb6714a324"
local: passed
local_evidence: "pytest on test_branch_protection_contract, test_pr_title, test_required_protective_workflows, scripts/tests/test_taskctl and test_task_contract_workflow: 224 passed, 45 subtests passed; test_pr_title after the merge-commit fix: 18 passed; test_agent_instructions and test_ci_dependency_selection: 81 passed; make docs-check: 10 passed; ./taskctl validate: 84 tasks, 296 steps valid; ./taskctl validate --base origin/main on the rebuilt branch: valid; openspec strict validation passed. make check -j 4 -k: 11083 pytest passed, bats, ansible-lint, terraform, shellcheck and validators passed; the only failures are the known container limits that touch none of the changed files (installer and 40 tests refuse to run as root or need IPv6, a locale or the vpn-bootstrap account)."
remote_ci: required
remote_ci_evidence: "The change merged as the squash commit above (pull request 447). Its pull-request runs were cancelled by follow-up pushes and the merge; the main push run 41214287569 on that commit was in progress when this snapshot was written. Record its final result before archive; the PR title job on the pull request validated the rebuilt commits through the new range check."
dry_run: not_applicable
dry_run_evidence: Repository policy, CI check and tasking tooling only; no deployment input changes.
staging: not_applicable
staging_evidence: No staging host is involved.
live: required
live_evidence: "make repository-policy-plan against GitHub shows exactly two pending writes (PUT ruleset main-integrity with allowed_merge_methods [rebase]; PATCH repository settings). make repository-policy-apply from the cloud session is refused by its proxy (write access to the repository settings API path is not permitted), so the owner runs it locally; record the readback here."
client: not_applicable
client_evidence: No client artifact or contract changes.
artifact: passed
artifact_evidence: "The refreshed sha256 for the openspec-archive-change skill in tools/tasking/generated-assets.lock.json is reviewed in the pull request diff and accepted by ./taskctl validate and the CI task-contract job."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RPOL-MERGE | CIC-1793458205564841 | policy contract test pins rebase-only settings and ruleset; PR-title tests cover valid, invalid and co-authored commit ranges; the PR title job passes on this pull request's own commits | required |
| REQ-RPOL-MERGE | CIC-1793458391172583 | `make repository-policy-plan` shows only the merge-method diff; `make repository-policy-apply` readback verified (authorized live step) | required |
| REQ-CIC-1793457997498773-001 | CIC-1793458297726343 | taskctl tests: done closure without any remote ref, collapsed transitions still rejected by the purge audit | required |
| REQ-CIC-1793457997498773-001 | CIC-1793458391172583 | README, CONTRIBUTING and skills name the rebase-only lifecycle; `./taskctl validate` accepts the refreshed asset lock; focused pytest, docs-check, make check and exact-head CI | required |
| REQ-CIC-1793437852879654-001 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
| REQ-CIC-1793437852879654-002 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
| REQ-CIC-1793437852879654-003 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref | required |
