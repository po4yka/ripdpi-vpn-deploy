# Change: Align vpnd operator output contract: man page, json flag, clip flag, doctor resilience

Task ID: `VPD-1787497426503364`

## Why

The deep audit found the operator-facing output contract drifting from reality: the generated man page comes from a hand-maintained replica of the CLI in build.rs and already documents a wrong probe-matrix duration default (1h vs 4h) and a share subcommand missing its required token flags; the global --json flag is accepted everywhere but read nowhere; doctor's --clip silently does nothing without --ai despite its help text; and doctor aborts on the first failing diagnostic step while capturing stdout only, so both the live terminal flow and every exported artifact lose exactly the failure detail they exist to collect.

## What Changes

- The man page is generated from the real clap Command instead of the build.rs replica, with a parity test that fails when cli.rs and the generated surface drift.
- The global --json flag is either implemented for the structured outputs that exist today (host list/show, probe-matrix report path) or removed entirely; help text matches behavior.
- clap declares the requires relationship between --clip and --ai so misuse errors immediately.
- Doctor captures stderr per step, continues after individual step failures, marks failed steps in the report, and exits nonzero only when steps failed.

## Capabilities

### New Capabilities

- `vpnd/operator-output`: Honesty contract between vpnd's documented surface (help, man page, flags) and its actual behavior.

### Modified Capabilities

- None

## Impact

- `vpnd/build.rs`, `vpnd/src/cli.rs`, `vpnd/src/commands/{doctor,host}.rs`, `vpnd/src/runner/process.rs`, completions snapshot.
- Scripts wrapping vpnd --json must be updated if the flag is removed rather than implemented.
