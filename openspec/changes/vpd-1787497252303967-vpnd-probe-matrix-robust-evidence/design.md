# Design

## Boundaries

- Rust-only change in vpnd/. Per-cell shell-out surface stays make probe-matrix-cell; scheduling glue remains vpnd-owned. Report JSON stays backward-compatible except additive fields; schema_version bumps per docs/PROBE-MATRIX.md contract.

## Decisions

- kill_on_drop(true) on the capture path: dropping the future at timeout kills the child. SIGPIPE nuance documented: quiet hung children are exactly the ones that survive without this flag.
- Checkpointing: write_report already uses temp+rename; reuse it per tick for controls/cells accumulated so far, and append per-tick records to <report>.jsonl as the crash-log. On graceful signal, write final report with "interrupted": true and exit code 130/143.
- Signal handling via tokio::signal in the run loop; no global handler.
- windows(): onset predicate becomes verdict is Blocked or Throttled; recovery unchanged (first later Ok).
- parse_duration gains a zero check alongside interval validation.

## Rollback

Revert restores single-write semantics; checkpoint files under the same output path are additive and ignored by old readers.

## Validation

Inline unit tests for windows() with Unknown-only series (no window) and Blocked->Ok recovery; timeout test asserting child termination via a sleep stub; duration-0 rejection test; snapshot refresh after schema_version bump; cargo clippy -D warnings.
