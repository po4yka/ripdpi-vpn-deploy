---
task_id: CIC-1793457997498773
change: cic-1793457997498773-merge-every-pull-request-by-rebase-and-keep-lifecycle-commits-in-one-pull-request
commit_sha: "3175b0d96f5ee54174040130be88b3fb6714a324"
local: passed
local_evidence: "pytest on test_branch_protection_contract, test_pr_title, test_required_protective_workflows, scripts/tests/test_taskctl and test_task_contract_workflow: 224 passed, 45 subtests passed; test_pr_title after the merge-commit fix: 18 passed; test_agent_instructions and test_ci_dependency_selection: 81 passed; make docs-check: 10 passed; ./taskctl validate: 84 tasks, 296 steps valid; ./taskctl validate --base origin/main on the rebuilt branch: valid; openspec strict validation passed. make check -j 4 -k: 11083 pytest passed, bats, ansible-lint, terraform, shellcheck and validators passed; the only failures are the known container limits that touch none of the changed files (installer and 40 tests refuse to run as root or need IPv6, a locale or the vpn-bootstrap account)."
remote_ci: passed
remote_ci_evidence: "The change merged as the squash commit above (pull request 447); its pull-request runs and the main push run 41214287569 were cancelled by follow-up pushes and the merge. The review-snapshot pull request 448 run 41216160249 on 31032f0b, whose tree differs from the merged commit only in task and board files, succeeded with every job and the required-checks aggregate green, including PR title (the new range check), task-contract and the four pytest groups."
dry_run: not_applicable
dry_run_evidence: Repository policy, CI check and tasking tooling only; no deployment input changes.
staging: not_applicable
staging_evidence: No staging host is involved.
live: passed
live_evidence: "The owner ran make repository-policy-plan and make repository-policy-apply locally on 2026-10-31 from the merged main: the plan listed exactly the two writes (PUT ruleset main-integrity with allowed_merge_methods [rebase]; PATCH repository settings), apply reported Repository policy verified; no remaining changes. Cloud readback afterwards: repository settings allow_rebase_merge true, allow_squash_merge false, allow_merge_commit false, delete_branch_on_merge true, allow_auto_merge true; ruleset 25813558 allowed_merge_methods [rebase]; a fresh plan returns []."
client: not_applicable
client_evidence: No client artifact or contract changes.
artifact: passed
artifact_evidence: "The refreshed sha256 for the openspec-archive-change skill in tools/tasking/generated-assets.lock.json is reviewed in the pull request diff and accepted by ./taskctl validate and the CI task-contract job."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RPOL-MERGE | CIC-1793458205564841 | policy contract test pins rebase-only settings and ruleset; PR-title tests cover valid, invalid, co-authored and merge-commit ranges (18 passed); the PR title job passed on the pull-request commits in runs 41213570025 and 41216160249 | passed |
| REQ-RPOL-MERGE | CIC-1793458391172583 | `make repository-policy-plan` showed only the two merge-method writes; `make repository-policy-apply` by the owner reported policy verified; cloud readback confirms rebase-only settings and ruleset | passed |
| REQ-CIC-1793457997498773-001 | CIC-1793458297726343 | taskctl tests: done closure requires only the HEAD review snapshot and works without any remote ref; purge audit tests unchanged (224 passed locally; task-contract and pytest green in CI run 41216160249) | passed |
| REQ-CIC-1793457997498773-001 | CIC-1793458391172583 | README, CONTRIBUTING and skills name the rebase-only lifecycle; `./taskctl validate` accepts the refreshed asset lock; focused pytest, docs-check, make check -k and the green review-snapshot run 41216160249 | passed |
| REQ-CIC-1793437852879654-001 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref (224 passed locally; CI run 41216160249 green) | passed |
| REQ-CIC-1793437852879654-002 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref (224 passed locally; CI run 41216160249 green) | passed |
| REQ-CIC-1793437852879654-003 | CIC-1793458297726343 | requirement removed: `--protected-ref`, the protected-ref lookup and their tests are deleted; taskctl tests cover done closure with no remote ref (224 passed locally; CI run 41216160249 green) | passed |
