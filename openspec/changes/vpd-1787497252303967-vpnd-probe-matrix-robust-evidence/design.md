# Design

## Boundaries

- Runtime slice: Rust-only changes in vpnd/, preserving make probe-matrix-cell/control and report/configuration schema 2. No writer, journal or contract mirror changes. Signal-aware dispatch is limited to noninteractive ProbeMatrix and Doctor commands so separating their captured process groups does not orphan them on terminal interruption. Schema-3 durability remains withheld until consumers and snapshots can advance together.

## Decisions

- Cmd has an explicit capture policy, default Foreground, with one capture engine. Only ProbeMatrix control/cells and Doctor diagnostics/audit select OwnedProcessGroup. A cancellation guard terminates owned groups through the existing rustix process API; kill_on_drop also protects the immediate child. Test a real child and grandchild because killing make alone does not terminate its probes. Interactive run() is unchanged.
- CLI dispatch registers SIGINT/SIGTERM listeners only for ProbeMatrix and Doctor, before polling either command. Interruption drops that dispatch future and aborts nested JoinSet tasks before runtime shutdown, returning 130/143. Other commands install no new signal listeners: Share blocks on token stdin before capture and Reconverge prompts after its inventory capture. Their foreground behavior must remain unchanged, proven by real stdin/PTY signal regressions. Raw Tokio/clipboard subprocess helpers gain no group-cleanup guarantee; no checkpointing is added.
- A capture cancellation guard drops before its Child, so group termination precedes the child's kill/reap cleanup. After a completed wait it is immediately disarmed rather than signalling a potentially recycled process-group ID. Normal command exit/status semantics remain unchanged.
- Checkpointing uses a private, exclusively created unique temporary file plus rename per tick, and appends tick records to <report>.jsonl. Never unlink an existing temporary file from another invocation. Report schema 3 includes completed/interrupted flags; running checkpoints are false/false, successful completion true/false, and graceful interruption false/true with exit code 130/143. Input configuration remains schema 2.
- Deferred durable flushing must compose with the scoped ProbeMatrix cancellation owner rather than install a competing signal handler.
- Schema-2 windows retain at most one record per protocol/target: the first observed Blocked/Throttled onset. Unknown/Error before recovery leaves null recovery; null means unobserved recovery, never an assertion of continuing impairment. An Ok after an indeterminate gap cannot establish recovery for the earlier onset. A directly observed Blocked/Throttled to Ok transition still records recovery. These are discrete observations, not exact continuous outage durations; multiple windows and explicit last-impaired timestamps remain deferred.
- parse_duration rejects zero and multiplication overflow; the run validates monotonic deadline representability before probes (including explain validation).
- Polling uses checked duration multiplication and Instant addition. An unrepresentable next tick is beyond the validated session deadline: finish with the observed results, without panic, synthetic Unknown or a new interval/schema restriction.

## Runtime implementation ownership — 2026-08-28

- Branch `codex/high-probe-runtime-20260828` from `069f664949cd04ca3d64954b6135cf48258e443c`: explicit runner capture policy, ProbeMatrix/Doctor opt-ins and scoped dispatch cancellation, probe duration/windows, existing Rust tests/snapshot, the existing rustix process feature, and relevant docs/evidence. No shared-controller, host/provider, schema-3 or durability implementation is included.
- Tests first: actual `Cmd` invokes real GNU Make, whose recipe starts a child and grandchild and atomically publishes their PIDs before the test cancels capture. Assert all owned processes terminate; fixture cleanup must kill only its own recorded processes. A separate CLI fixture bounds a hanging control and confirms cells still run. Existing control timeout source receives credit rather than being rewritten.

## Rollback

The runtime slice does not change the writer or schemas. A later durability
rollout must revert its writer and schema together; do not interpret schema-3
observations using the old window semantics.

## Validation

Inline unit tests cover no-impairment series, indeterminate gaps and Blocked->Ok
recovery. Real GNU Make fixtures prove timeout/signal cleanup of child and
grandchild processes and a bounded hanging control. Actual CLI validation rejects
zero/overflow before invoking probes. Review the schema-2 snapshot diff and run
Cargo tests and clippy with warnings denied. Checkpoint/schema-3 verification is
separate and remains pending.
