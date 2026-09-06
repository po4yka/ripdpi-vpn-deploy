---
task_id: VPD-1787497252303967
change: vpd-1787497252303967-vpnd-probe-matrix-robust-evidence
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
staging: not_applicable
staging_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
live: not_applicable
live_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
client: not_applicable
client_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
artifact: not_applicable
artifact_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-MATRIX-CELL-TIMEOUT-KILL | VPD-1787497252661429 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-MATRIX-CONTROL-TIMEOUT | VPD-1787497252679177 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-MATRIX-DURABILITY | VPD-1787497252698055 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-MATRIX-EVIDENCE-SEMANTICS | VPD-1787497252715025 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |

## Bounded runtime evidence — 2026-08-28

- Base `069f664949cd04ca3d64954b6135cf48258e443c`, branch
  `codex/high-probe-runtime-20260828`. Before source edits, library tests had
  86 pass / 2 fail, lifecycle 2 pass / 2 fail, runner 1 pass / 1 fail.
  Failures reproduced zero acceptance/overflow panic, unsupported window claims,
  and live Make descendants after timeout or CLI signal. Fixture cleanup then
  confirmed its recorded processes were gone; no live hosts were involved.
- After scoped capture/signal ownership and the reviewed snapshot update,
  `cargo test --locked --jobs 2 --lib --test runner_execution --test probe_matrix_lifecycle --test probe_matrix_snapshot --test share_command --test deploy_lifecycle --no-fail-fast`
  passed all 112 tests (88 library, 8 deploy lifecycle, 6 probe lifecycle,
  3 snapshot, 2 runner, 5 share) through the machine build gate. Signals target either the
  real CLI PID or its fixture-owned foreground process group; both probe jobs
  and doctor return 130/143 and leave no running recorded Make/shell/sleep process
  within three seconds. This observes cancellation of nested JoinSet captures,
  not merely a dropped handle. The hanging-control test is credit for the
  already-existing timeout, not a new timeout implementation.
- Existing rustix 1 gains only its `process` feature; no package/version or lock
  change. No unsafe code, contracts, schema-3 fields, journal or report writer
  changes are included. These local process fixtures do not establish hosted,
  staging, filtered-path, client or durable interruption acceptance.
- An intermediate global-listener design passed 97 focused tests, but actual
  blocking stdin/PTY tests exposed changed signal behavior before publication.
  The corrected candidate explicitly opts only ProbeMatrix and Doctor captures
  into group ownership, with signal listeners scoped to those dispatches.
  Share and Reconverge retain foreground captures and default signal behavior;
  their source does not gain descendant-cleanup guarantees.
- Four actual interactive cases now pass: Share first consumes synthetic pipe
  bytes with EOF withheld; Reconverge first displays its real dialoguer prompt
  in a controlling PTY after an inventory fixture. SIGINT and SIGTERM must each
  terminate by that exact signal within three seconds. On Darwin only, a
  pre-close E/P_WEXIT observation permits releasing the PTY master before reaping;
  the exact requested signal is still mandatory, so closing a live terminal and
  inducing SIGHUP cannot pass. The same final harness remains RED against the
  preserved intermediate binary and GREEN against the scoped candidate.
- `cargo clippy --locked --jobs 2 --all-targets -- -D warnings` passed for the
  scoped candidate through the machine build gate. Formatting, strict OpenSpec
  validation, task validation and diff whitespace checks also passed.
- Follow-up arithmetic review found that a valid one-second session with a
  maximum-u64 CLI or configuration poll interval still panicked after its first
  real Make sweep. The new CLI regression reproduced exit 101 in both cases.
  Checked interval multiplication and Instant addition now return no next tick
  when it lies beyond the representable clock, ending the bounded session with
  its one observed Ok control and two Ok cells. Existing fixed-rate cadence
  coverage remains, extended with multiplication/addition overflow and tick-zero
  cases. No new schema fields or interval restrictions were added. The 112-test
  rerun and final all-target clippy passed.

## Full Rust validation — 2026-08-28

- From `vpnd/`, ran the complete unfiltered suite and all-target Clippy in one
  machine-wide build-gate slot, with the existing worktree-local target cache
  and two Cargo jobs:

  ```sh
  CARGO_BUILD_JOBS=2 CARGO_TARGET_DIR="$PWD/target" mise exec -- build-gate -- sh -c 'cargo test --locked --jobs 2 --no-fail-fast && cargo clippy --locked --jobs 2 --all-targets -- -D warnings'
  ```

- The combined command exited **0**. All **177 Rust tests passed**, with zero
  failed, ignored, measured or filtered cases; the documentation-test target
  contained zero tests. This includes 88 library tests and 89 integration/property
  tests, including real process cancellation and interactive pipe/PTY fixtures.
  Clippy completed with warnings denied. This is a debug-profile local Rust gate,
  not the repository-wide `make check` or hosted release-profile gate.
- Independent read-only review covered capture ownership/drop ordering, scoped
  signals and Doctor opt-ins, the final checked schedule arithmetic, and the
  corresponding real process/CLI tests; no blocking findings remained. Runtime,
  test, snapshot and schema files were unchanged during this full validation.
- Full repository checks, hosted checks and authorized live/client acceptance
  remain separate. This 2026-08-28 evidence covers only the schema-2 runtime
  slice; the following section records the later durability phase.

## Durability implementation — 2026-08-29

- Input configuration remains schema 2. Report schema 3 adds only the required
  `completed` and `interrupted` booleans; the existing single-window onset and
  recovery semantics are unchanged. JSONL records and atomic reports are mode
  `0600`, synchronized in journal-before-report order, and serialized by a
  persistent current-owner regular-file lock.
- The lifecycle suite now has 13 passing real CLI tests. It covers normal
  checkpoints, distinct companion paths, active-session exclusion and lock
  reuse, unsafe/symlink/nonempty locks, reserved output suffixes, SIGINT and
  SIGTERM during cells, SIGINT during the scheduled wait, completed-cell
  preservation, descendant cleanup, and report-write failure after a durable
  journal record. A failed interrupt checkpoint exits 1 instead of falsely
  claiming 130/143 and leaves the last valid report byte-identical.
- The complete unfiltered Rust suite passed all 184 tests, and
  `cargo clippy --locked --all-targets --all-features -- -D warnings` passed in
  the machine-wide build gate with two jobs. The Python schema contract passed
  all 5 tests, including valid complete/interrupted states and rejection of the
  impossible true/true state.
- Independent review found one race where a biased signal could discard an
  already-ready control result. The control future now has priority when both
  branches are ready; the reviewer confirmed the blocker closed and found no
  further blocker.
- The combined candidate `f29ca8e72e2c5d9803ce21da0f9b3cab144a3b4d`
  then passed the complete repository `make -j1 check`: 2050 Python tests with
  one existing skip, all 55 BATS tests, all 184 release-profile Rust tests,
  Clippy with warnings denied, and the Terraform, policy, cloud-init, render,
  schema, Ansible and `ci-fast` gates. The isolated Colima profile stopped with
  exit 0. The outer wrapper alone returned nonzero because its context-string
  comparison reported false after `make` had completed; the Docker config file
  was not modified, and a bounded follow-up start/stop observed both identical
  context and identical config hash. This is local repository evidence, not
  hosted, client, staging or live traffic acceptance.
- PR #116 exact head `ef688f2a785173913e6e22c42a4843f1c97451bb`
  passed CI run `33244798098` (51/51), CodeQL run `33244798079`,
  and all other required checks. The PR rollup reached 64 successful checks and
  one neutral report after contract-sync run `33244798075` compared against the
  integrated client mirror.
- RIPDPI PR #460 exact head
  `10f209b1a8f6c51f7c85ae9bde54467c2798f986` passed 47 hosted checks with
  18 expected skips and CodeQL, then entered protected main as
  `ec7f670cdd97277d468496338dafbe3eb69ddefb`. Exact client-main CI run
  `33247910603` passed all 44 executed jobs with 17 expected skips; CodeQL,
  Secret Scan and fleet-fixtures also passed. The vendored schema SHA-256 is
  `1504d756decd4de5f13dc468d9a56ffa6bfbef9fd89051a2a0f76a15acee029a`,
  byte-identical to this producer candidate. No client runtime, exposure or
  schema-2 window behavior changed. Staging and live traffic acceptance remain
  separate and pending.
