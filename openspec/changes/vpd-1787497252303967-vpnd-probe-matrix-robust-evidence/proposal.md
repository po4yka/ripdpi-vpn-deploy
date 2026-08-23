# Change: Fix probe-matrix process leaks, timeouts, durability, and evidence semantics

Task ID: `VPD-1787497252303967`

## Why

The deep audit found five defects in the probe matrix: timed-out cells leak their child processes because kill_on_drop is unset, so orphaned probes pollute later ticks of the very measurement they belong to; the control probe runs without any timeout and can stall the whole run; the session accumulates entirely in RAM with a single terminal write, so an interrupt loses hours of measurements; --duration 0 silently produces a schema-valid empty report with exit 0; and windows() opens outage windows on local orchestration failures (Unknown/Error), overstating filtering evidence in a report positioned as conservative.

## What Changes

- Cell subprocesses are spawned with kill_on_drop(true) so timeout cancellation terminates the process tree.
- The control invocation gets the same per-call timeout budget as cells.
- Results are checkpointed to disk every tick (atomic rewrite of the JSON report plus incremental JSONL), SIGINT/SIGTERM handlers flush partial results and exit nonzero with an interrupted marker.
- Config validation rejects duration 0; interrupted or empty runs never present as clean green reports.
- windows() only opens impairment windows from protocol verdicts (Blocked/Throttled), never from local Unknown/Error cells, which remain represented by Indeterminate observations.

## Capabilities

### New Capabilities

- `vpnd/probe-matrix-evidence`: Lifecycle and evidence-semantics contract for the topology-aware probe matrix report.

### Modified Capabilities

- None

## Impact

- `vpnd/src/commands/probe_matrix.rs`, `vpnd/src/runner/process.rs`, tests including the insta snapshot (schema_version bump if report shape changes).
- Report consumers must tolerate the new interrupted marker and the narrowed window semantics.
