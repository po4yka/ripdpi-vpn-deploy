---
task_id: CIC-1788902865968549
change: cic-1788902865968549-preserve-pre-policy-terminal-history
commit_sha: 152670070802629be9b58fea49a8e8fef52ad5b0
local: passed
local_evidence: "Exact source d8fe945e698f9c5887fa32dd2d1e55becf3ce2a9 passed the focused late-activation regressions, the full taskctl suite with 103 tests and 20 subtests, governance count, strict OpenSpec, base-aware task validation with 4 tasks and 16 steps, and build-gate -- make ci-fast: 4362 Python tests passed with 4 deselected and 20 subtests, 55 Bats tests, release Cargo clippy, and all Rust tests; ci-fast: OK."
remote_ci: passed
remote_ci_evidence: Protected PR #210 exact-head checks (run 34306549038 at 15267007) passed: ci, codeql, scorecard, and release-please; Codex code review and security review completed with no blocking findings.
dry_run: not_applicable
dry_run_evidence: Repository task-lifecycle validation has no infrastructure dry-run path.
staging: not_applicable
staging_evidence: No provider or staging resource behavior changes.
live: not_applicable
live_evidence: No fleet or runtime behavior changes.
client: not_applicable
client_evidence: No client behavior changes.
artifact: not_applicable
artifact_evidence: No released runtime artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1788902865968549-001 | CIC-1788924940528030 | Branch-local late activation and federation regressions first reproduced the bypass, then passed with legacy eligibility bound to a pre-established trusted validation base; the full taskctl suite, base-aware validation, and exact-diff ci-fast pass. | passed |
