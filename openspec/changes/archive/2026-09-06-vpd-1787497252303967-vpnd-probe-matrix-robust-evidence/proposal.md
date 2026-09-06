# Change: Fix probe-matrix process leaks, timeouts, durability, and evidence semantics

Task ID: `VPD-1787497252303967`

## Why

The original audit identified subprocess cancellation, control timeouts, durability, zero duration and overstated impairment windows. Main now has kill_on_drop on run/capture and a bounded control invocation; those existing fixes must be preserved and tested accurately. Captures still lack process-group cleanup for descendants of make, duration zero remains accepted, and Unknown/Error still open windows or imply recovery across an indeterminate gap. Durability remains separate unfinished work.

## What Changes

- Noninteractive ProbeMatrix and Doctor captures explicitly own a process group; their scoped signal cancellation terminates descendants as well as the direct child protected by existing kill_on_drop(true). Other commands retain foreground capture and default signal behavior, including blocking token input and confirmation prompts.
- The existing control timeout is covered by a real hanging-Make regression, preserving Unknown-on-expiry and continued cell execution.
- Results are checkpointed to disk every tick (atomic rewrite of the JSON report plus incremental JSONL), SIGINT/SIGTERM handlers flush partial results and exit nonzero with an interrupted marker.
- Runtime validation rejects duration 0 and arithmetic/deadline overflow before any probe starts. Interrupt evidence remains part of the deferred durability work.
- windows() only opens impairment windows from protocol verdicts (Blocked/Throttled), never from local Unknown/Error cells, which remain represented by Indeterminate observations.

## Capabilities

### New Capabilities

- `vpnd/probe-matrix-evidence`: Lifecycle and evidence-semantics contract for the topology-aware probe matrix report.

### Modified Capabilities

- None

## Impact

- `vpnd/src/commands/probe_matrix.rs`, `vpnd/src/runner/process.rs`, tests including the insta snapshot (schema_version bump if report shape changes).
- The bounded runtime slice keeps report/configuration schema 2 and adds no fields. Null recovery means recovery was not observed; it does not assert uninterrupted impairment. The interrupted marker and schema-3 fields remain withheld until synchronized with the client contract.
