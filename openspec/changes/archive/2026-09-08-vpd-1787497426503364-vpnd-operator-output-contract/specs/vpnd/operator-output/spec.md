## Purpose

Every documented element of vpnd's operator surface — help text, man page, global flags — must match actual behavior, and diagnostic exports must survive partial failures.

## ADDED Requirements

### Requirement: REQ-MANPAGE-SYNC — Man page derived from the real CLI

The installed man page MUST be generated from the same clap Command definition that drives the binary, and a gate MUST fail when the two surfaces diverge.

#### Scenario: Flag added without docs update

- **WHEN** a contributor adds or changes a subcommand flag
- **THEN** the parity gate fails until the generated man page reflects it

### Requirement: REQ-JSON-FLAG-HONESTY — No dead global flags

The global --json flag MUST either produce machine-readable output for the subcommands that have structured results or be removed from the CLI; its help text MUST match the implemented behavior.

#### Scenario: Script consumes --json

- **WHEN** an operator passes --json to any subcommand
- **THEN** either parseable JSON is emitted for that subcommand or the flag is rejected as unknown — never silently ignored human output

### Requirement: REQ-CLIP-REQUIRES-AI — Explicit flag dependency

Passing --clip without --ai MUST fail fast with guidance instead of silently doing nothing.

#### Scenario: Clip without ai

- **WHEN** doctor runs with --clip and no --ai
- **THEN** argument parsing exits nonzero explaining --clip requires --ai

### Requirement: REQ-DOCTOR-RESILIENCE — Diagnostics survive failing steps

Doctor MUST continue running remaining steps after one fails, MUST include captured stderr alongside stdout for each step, MUST mark failed steps in the report, and MUST exit nonzero when any step failed.

#### Scenario: Mid-run diagnostic failure

- **WHEN** one doctor step exits nonzero while later steps would succeed
- **THEN** the report contains all completed outputs plus the failed step's stderr, marked failed, and the final exit code is nonzero
