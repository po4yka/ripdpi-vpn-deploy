# Design

## Boundaries

- The first runtime slice preserved report/configuration schema 2 while adding
  bounded process ownership. The durability phase advances only the report to
  schema 3 after its producer snapshot and client mirror can move together.
  Make probe-matrix-cell/control, input schema 2, and window semantics remain
  unchanged.

## Decisions

- Cmd has an explicit capture policy, default Foreground, with one capture engine. Only ProbeMatrix control/cells and Doctor diagnostics/audit select OwnedProcessGroup. A cancellation guard terminates owned groups through the existing rustix process API; kill_on_drop also protects the immediate child. Test a real child and grandchild because killing make alone does not terminate its probes. Interactive run() is unchanged.
- CLI dispatch retains SIGINT/SIGTERM ownership for Doctor. ProbeMatrix owns its
  listeners inside the command so it can abort and drain nested JoinSet tasks,
  synchronize the partial journal/report, then return 130/143. Other commands
  install no listeners: Share blocks on token stdin and Reconverge retains its
  foreground prompt behavior. Raw Tokio/clipboard helpers gain no group-cleanup
  guarantee.
- A capture cancellation guard drops before its Child, so group termination precedes the child's kill/reap cleanup. After a completed wait it is immediately disarmed rather than signalling a potentially recycled process-group ID. Normal command exit/status semantics remain unchanged.
- Checkpointing uses a private, exclusively created unique temporary file plus rename per tick, and appends tick records to <report>.jsonl. Never unlink an existing temporary file from another invocation. Report schema 3 includes completed/interrupted flags; running checkpoints are false/false, successful completion true/false, and graceful interruption false/true with exit code 130/143. Input configuration remains schema 2.
- Durable flushing replaces, rather than competes with, the earlier
  ProbeMatrix dispatcher listener. Doctor keeps the earlier listener.
- Schema-2 windows retain at most one record per protocol/target: the first observed Blocked/Throttled onset. Unknown/Error before recovery leaves null recovery; null means unobserved recovery, never an assertion of continuing impairment. An Ok after an indeterminate gap cannot establish recovery for the earlier onset. A directly observed Blocked/Throttled to Ok transition still records recovery. These are discrete observations, not exact continuous outage durations; multiple windows and explicit last-impaired timestamps remain deferred.
- parse_duration rejects zero and multiplication overflow; the run validates monotonic deadline representability before probes (including explain validation).
- Polling uses checked duration multiplication and Instant addition. An unrepresentable next tick is beyond the validated session deadline: finish with the observed results, without panic, synthetic Unknown or a new interval/schema restriction.

## Runtime implementation ownership — 2026-08-28

- The first runtime slice delivered explicit runner capture policy,
  ProbeMatrix/Doctor opt-ins and scoped cancellation, probe duration/windows,
  and the schema-2 report. The durability phase builds on that process owner;
  it does not restore the older dispatcher or older multi-window model.
- Tests first: actual `Cmd` invokes real GNU Make, whose recipe starts a child and grandchild and atomically publishes their PIDs before the test cancels capture. Assert all owned processes terminate; fixture cleanup must kill only its own recorded processes. A separate CLI fixture bounds a hanging control and confirms cells still run. Existing control timeout source receives credit rather than being rewritten.

## Rollback

Roll back the durability writer, report schema, producer tests, and client
mirror together. Do not roll back the newer process-group capture or current
single-window semantics, and do not feed schema-3 reports to a schema-2
consumer.

## Validation

Inline unit tests cover no-impairment series, indeterminate gaps and Blocked->Ok
recovery. Real GNU Make fixtures prove timeout/signal cleanup of child and
grandchild processes and a bounded hanging control. Actual CLI validation rejects
zero/overflow before invoking probes. Durability verification additionally
covers mode-0600 checkpoints, JSONL records, output exclusivity, graceful
interrupt flushing, and descendant cleanup. Review the schema-3 snapshot and
byte-identical client mirror, then run Cargo tests and clippy with warnings
denied.
