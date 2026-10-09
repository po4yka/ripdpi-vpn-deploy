---
task_id: TFR-1791523370274374
change: provider-management-isolation
commit_sha: 4434a6086a876cb10dfbe92505110e7819f777b1
local: blocked
local_evidence: Targeted and remaining gates passed; complete make check hit one timeout flake, reproduced as passing unchanged on this branch and clean main. A single uninterrupted green make check remains unobserved.
remote_ci: required
remote_ci_evidence: PR 281 head e32f95ab9a5b30e44155b91c24135917841407b3 passed provider and policy jobs but pytest shard 3 failed on the unchanged bundle-emitter fixture closing stdin early (SIGPIPE). The fixture now consumes piped input; final-head CI remains required, no terminal success claimed.
dry_run: not_applicable
dry_run_evidence: No provider access authorized for this source PR.
staging: not_applicable
staging_evidence: No infrastructure deployment authorized for this source PR.
live: not_applicable
live_evidence: Source PR only; fleet behavior remains unverified.
client: not_applicable
client_evidence: Source PR only; client-path acceptance remains unverified.
artifact: passed
artifact_evidence: PR 281 on codex/terraform-provider-p1-fixes; integrated source head 4434a6086a876cb10dfbe92505110e7819f777b1.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PMI-SSH | TFR-1791523579427434 | Complete native management tests and range-aware policy tests | passed; aggregate local-gate gap below |
| REQ-PMI-IDENTITY | TFR-1791523580174419 | Mock state transitions, unchanged plans and exact prevent_destroy diagnostics | passed; aggregate local-gate gap below |
| REQ-PMI-HETZNER | TFR-1791523580174419 | Current-type plans and non-destructive attachment ownership migration | passed; aggregate local-gate gap below |
| REQ-PMI-POLICY | TFR-1791523580836950 | Real Conftest positive/negative/empty evaluation and saved-plan subprocess tests | passed; aggregate local-gate gap below |

## Delivery gates

TFR-1791523581450706 requires the complete local gate, independent security
review, an exact committed head, a scoped PR and reported hosted status.

## Observed targeted evidence

- Terraform 1.15.2 complete native suites: UpCloud 65, Hetzner 46, Vultr 46,
  Scaleway 39; all passed. Actual synthetic legacy/current state transitions:
  18 passed, including first adoption, protected key/name edits and safe forgetting.
- Policy/operator pytest suites: 65 passed. Real Conftest policy unit tests:
  59 passed. Post-integration runtime/operator portable subset: 109 passed,
  one native Linux-only test deselected by the documented platform partition.
- Independent security review: APPROVE after canonical gate/helper integration,
  all-port selectors, malformed-input guards and full UpCloud source intervals.
- Full make check used real SOPS/age binaries and a working local Docker engine:
  5296 portable tests passed, one subprocess-timeout test failed, 36 native tests
  deselected by the portable partition. Both timeout parametrizations then passed
  unchanged here (2 passed) and on a clean integrated main snapshot (2 passed).
  This does not turn the failed aggregate invocation into a green run.
- Remaining local gates passed separately: all 56 Bats tests, release Clippy with
  warnings denied and the complete release Cargo test suite (no ignored tests).
- All commit hooks passed with pinned native ShellCheck execution. The task stays
  in review; aggregate local-gate and infrastructure acceptance remain explicit.
- The hosted bundle-emitter failure was traced to a wg stub that exited without
  consuming its piped input. The production script and fixture were byte-identical
  to integrated main before correction. The fixture correction preserves all
  assertions and consumes stdin before emitting output, as the real command does.
  Both existing parametrizations passed (2 tests). A forced delayed-producer probe
  returned pipeline statuses [141, 0] before and [0, 0] after using the exact stub;
  the ordinary full test did not reproduce the scheduling race locally.
