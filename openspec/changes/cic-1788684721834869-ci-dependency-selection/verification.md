---
task_id: CIC-1788684721834869
change: cic-1788684721834869-ci-dependency-selection
commit_sha: a5fc27c44fd217743469283cb181cbc413874a96
local: passed
local_evidence: 79 related regressions passed after merging current main; make validate, actionlint, strict offline zizmor and taskctl validation passed.
remote_ci: passed
remote_ci_evidence: Exact-main CI selected all 28 groups and passed all 75 jobs, including the strict final gate; CodeQL, Scorecard and release-please also succeeded.
dry_run: not_applicable
dry_run_evidence: CI scheduling does not change deployment inputs or runtime configuration.
staging: not_applicable
staging_evidence: No deployed behavior changes.
live: passed
live_evidence: All nine canonical contexts have app_id 15368 and strict mode enabled; full before/after protection comparison found no unrelated changes.
client: not_applicable
client_evidence: No public CLI or client contract changes.
artifact: passed
artifact_evidence: requirements, design and regression tests are repository-contained; hosted outcomes are recorded below with exact revision identifiers.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CI-SELECT | CIC-1788684721858733 | 47 selector/gate regression cases; selective hosted CI on 76f7b8db381513ca0f862ebc3bd78b41758856b7 selected Rust/native plus baseline, 19 successful executed jobs and 14 planned group skips | passed |
| REQ-CI-FALLBACK | CIC-1788684721858733 | Full hosted CI on f198a98703a947ce3b44894919478b2180c3d8d7 selected all 28 groups; 75 jobs succeeded | passed |
| REQ-CI-GATE | CIC-1788684721858733 | Failure, cancellation, malformed/partial maps and unauthorized skip regressions passed; strict aggregate gate succeeded in both observed hosted modes | passed |
| REQ-CI-PROTECTION | CIC-1788686155608641 | Protected main a5fc27c44fd217743469283cb181cbc413874a96 passed all 75 CI jobs, CodeQL, Scorecard and release-please; full protection readback preserved strict mode, nine app-bound contexts and unrelated settings | passed |
