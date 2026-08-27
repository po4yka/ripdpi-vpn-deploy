# Design

## Boundaries

- Rust-only change in vpnd/. Per-cell shell-out surface stays make probe-matrix-cell; scheduling glue remains vpnd-owned. Report JSON advances to schema version 3; update consumers and snapshots together without preserving the old evidence interpretation.

## Decisions

- Each captured invocation owns a process group. A cancellation guard terminates that group through the existing rustix process API; kill_on_drop also protects the immediate child. Test a real child and grandchild because killing make alone does not terminate its probes.
- Checkpointing uses a private, exclusively created unique temporary file plus rename per tick, and appends tick records to <report>.jsonl. Never unlink an existing temporary file from another invocation. Report schema 3 includes completed/interrupted flags; running checkpoints are false/false, successful completion true/false, and graceful interruption false/true with exit code 130/143. Input configuration remains schema 2.
- Signal handling via tokio::signal in the run loop; no global handler.
- windows(): only Blocked or Throttled opens or extends impairment. Record the last impaired observation explicitly. Unknown/Error terminates the observed window without claiming recovery; an Ok after that gap cannot establish when recovery happened. A directly observed Blocked/Throttled to Ok transition still records recovery.
- parse_duration gains a zero check alongside interval validation.

## Rollback

Revert restores the prior writer and schema together; do not interpret schema-3 observations using the old window semantics.

## Validation

Inline unit tests for windows() with Unknown-only series (no window) and Blocked->Ok recovery; timeout test asserting child termination via a sleep stub; duration-0 rejection test; snapshot refresh after schema_version bump; cargo clippy -D warnings.
