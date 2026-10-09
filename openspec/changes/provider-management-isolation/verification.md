---
task_id: TFR-1791523370274374
change: provider-management-isolation
commit_sha: null
local: passed
local_evidence: Complete build-gated make check passed with pinned cached providers and enforced lock checksums; 5535 portable tests, 56 Bats tests, release Clippy and complete release Cargo tests passed. Native and targeted P2 suites also passed.
remote_ci: required
remote_ci_evidence: P1 head 0068c68f55908533209995030217743c1b561ff2 completed all 81 hosted checks (80 success, one neutral). The P2 follow-up requires fresh exact-head hosted evidence.
dry_run: not_applicable
dry_run_evidence: No provider access authorized for this source PR.
staging: not_applicable
staging_evidence: No infrastructure deployment authorized for this source PR.
live: not_applicable
live_evidence: Source PR only; fleet behavior remains unverified.
client: not_applicable
client_evidence: Source PR only; client-path acceptance remains unverified.
artifact: passed
artifact_evidence: PR 281 on codex/terraform-provider-p1-fixes is the existing delivery artifact; P2 commits and updated evidence are pending.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PMI-SSH | TFR-1791523579427434 | Complete native management tests and range-aware policy tests | passed; aggregate local-gate gap below |
| REQ-PMI-IDENTITY | TFR-1791523580174419 | Mock state transitions, unchanged plans and exact prevent_destroy diagnostics | passed; aggregate local-gate gap below |
| REQ-PMI-HETZNER | TFR-1791523580174419 | Current-type plans and non-destructive attachment ownership migration | passed; aggregate local-gate gap below |
| REQ-PMI-POLICY | TFR-1791523580836950 | Real Conftest positive/negative/empty evaluation and saved-plan subprocess tests | passed; aggregate local-gate gap below |
| REQ-PMI-ADAPTER | TFR-1791537004741307 | Native Vultr range/singleton and enabled/disabled backup plans | required P2 follow-up |
| REQ-PMI-LISTENERS | TFR-1791537005304551 | Four-root fractional refusal, integer boundaries and effective legacy collision tests | required P2 follow-up |
| REQ-PMI-SCALARS | TFR-1791537005854827 | Actual Terraform rendering, YAML parsing and CI-renderer parity | required P2 follow-up |
| REQ-PMI-P2-DELIVERY | TFR-1791537006373613 | Integrated local checks, independent review and exact-head PR 281 checks | required P2 follow-up |

## Delivery gates

TFR-1791523581450706 requires the complete local gate, independent security
review, an exact committed head, a scoped PR and reported hosted status.

## Observed targeted evidence

The following P1 evidence is historical and does not substitute for the P2 gate.

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

## P2 evidence and original finding disposition

- Four complete native suites: UpCloud 69, Hetzner 50, Vultr 53, Scaleway 43;
  215 passed, no failures or skips. Old validation rules fail the new integer-port
  regression suites in all four roots, confirming the tests detect the original bug.
- Existing synthetic legacy/current state lifecycle harness: 18 passed, no skips.
  Encoded trailing-newline public keys preserve the existing identity guard.
- Shared serialization tests: 15 passed, including actual Terraform rendering and
  parsed CI parity for ordinary, punctuation, multiline and Unicode values, plus
  null-input refusal in both renderers. Serialization plus executable coverage:
  21 passed, with both native functions registered in the unchanged exact-set check.
- Bootstrap/CI portable subset: 122 passed, eight native cases deselected by the
  documented platform partition. Policy/operator tests: 65 passed; Rego: 59 passed.
- Independent security review: APPROVE on the complete P2 diff, including new
  untracked tests, with 21 serialization/coverage checks independently passing
  after the native registration and null-input correction.
- P2 dual-stack secondary-IP policy was already repaired with P1 enforcement.
- P2 Hetzner honeypot address convergence already exists in current main's
  dedicated guest address unit and presence assertion; no runtime reimplementation.
- P2 Vultr range syntax and backup scheduling are repaired with three new adapter
  plans covering TCP/UDP, both families, canonical outputs and opt-in/off schedules.
- P2 fractional SSH ports were repaired with P1; this follow-up also rejects
  fractional singleton and legacy XHTTP ports in all roots (16 new native runs).
- P2 legacy XHTTP regressions now select the effective legacy mode (eight repaired
  runs), assert old TCP/8443 absence and retain UDP/443 on TCP collision.
  UpCloud's final predicate checks actual destination ports after filtering
  configured TCP rules; its complete 69-case suite passed after that correction.
  A temporary actual-port mutation with an unchanged comment fails the assertion,
  proving it observes port data rather than descriptive notes alone.
- P2 shared YAML serialization now preserves supplied scalar values and metadata
  bytes while refusing document-structure injection.
- The original P2 Debian 11 claim is withdrawn: official public catalog ID 1743
  is Ubuntu 22.04 LTS x64. The existing OS mapping remains unchanged.
- First full P2 local gate: 5531 portable passed, one native-registry assertion
  failed, 43 native cases deselected. Its exact native-function set was missing the
  new function; registration is repaired without weakening the assertion. The
  corrected full gate passed. A registry timeout in a separate early attempt was
  resolved with a task-local mirror of already pinned packages; checksum checks
  remained enforced and no operator configuration was changed.
- Complete corrected make check: 5535 portable passed, 46 native cases deselected
  by the documented partition, 56 Bats passed, release Clippy passed and complete
  release Cargo tests passed (no ignored tests); aggregate command exited zero.
- Fresh exact-head hosted results remain required. No authenticated
  provider, guest reboot/convergence, deployment or client acceptance is claimed.
