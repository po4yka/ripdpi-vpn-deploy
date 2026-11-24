---
task_id: SCR-1795491503477936
change: scr-1795491503477936-retire-expired-liveness-executor
commit_sha: null
local: passed
local_evidence: "2026-11-24 working tree on f5646b742: `python3 -m pytest tests/unit/test_disposable_liveness_executor.py tests/unit/test_disposable_liveness_make.py tests/unit/test_retire_unbound_staging_client.py` 217 passed, exit 0 (new: expiry refusal and retirement with receipt and idempotent repeat, resume after an interrupted delete, assigned-executor refusal, Make wiring; the parametrized Make boundary tests now cover the new goal); `make docs-check` passed, exit 0, after `make docs-reference`. An independent review found no blocker; its audit-record finding is fixed (the command appends a best-effort audit record like `deonboard`)."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change touches only operator-side executor cleanup; no deployed runtime changes.
staging: required
staging_evidence: "Partial, 2026-11-24 at db0de21b3: `make retire-expired-disposable-liveness` retired the expired leftover executor of the acc3 staging run (status retired-expired, changed true); `colima list` no longer shows it. The leftover executor of the acc4 run refused with executor-not-expired, as designed, because its manifest expires at 08:43Z; it is retired after that time."
live: not_applicable
live_evidence: Operator machine only; no production node changes.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EXPIRED-EXECUTOR-RETIRE | SCR-1795491794457312 | `test_expired_unassigned_executor_retires_only_after_expiry` | passed |
| REQ-EXPIRED-EXECUTOR-GUARDS | SCR-1795491794457312 | `test_expired_unassigned_executor_retires_only_after_expiry` (before expiry), `test_expired_retirement_refuses_an_assigned_executor_before_vm_mutation` | passed |
| REQ-EXPIRED-EXECUTOR-MAKE | SCR-1795491794457312 | `test_retire_expired_is_gated_and_passes_only_manifest_and_receipt`, the parametrized `test_make_rejects_unowned_command_variable_before_expansion`, `test_make_rejects_nonliteral_owned_fields_before_any_child`, `test_makefile_declares_every_disposable_goal_phony` | passed |
