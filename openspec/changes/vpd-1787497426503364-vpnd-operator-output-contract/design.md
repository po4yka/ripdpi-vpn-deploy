# Design

## Boundaries

- Rust-only change in vpnd/. Output formats stay stable except where a finding requires change (doctor report gains stderr sections and failed-step marks).

## Decisions

- Man-page parity: build.rs cannot import the crate, so generation moves behind a feature-gated helper invoked from an xtask-style test or build step that constructs Cli::command() from src/cli.rs directly; the build.rs replica is deleted.
- --json decision default: implement emission for host list/show and probe-matrix (report already JSON — flag prints the path plus machine-readable summary); removal alternative documented if scope grows.
- Doctor resilience: capture() gains capture_stderr mode returning Output{stdout,stderr}; loop collects failures instead of propagating, renders them with a Failed marker, exits 1 when any step failed.
- clap requires = "ai" on --clip gives parse-time errors.

## Rollback

Single-commit revert; man-page generation returns to replica (known-drifty) state.

## Validation

Snapshot tests for doctor report shape; parity gate seeded-drift negative test; clap parse tests for clip/json behavior; cargo clippy -D warnings.
