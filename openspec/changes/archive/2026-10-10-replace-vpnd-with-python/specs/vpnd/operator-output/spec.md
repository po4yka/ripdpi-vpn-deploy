## Purpose

Keep generated operator documentation aligned with the Python parser after
retiring clap and the Rust implementation.

## MODIFIED Requirements

### Requirement: REQ-MANPAGE-SYNC — Man page derived from the real CLI

The installed man page MUST be generated from the same command definition
that drives the Python parser, help and completions. A gate MUST fail when
commands, options, defaults or argument relationships diverge. Generation
MUST cover the root and all existing subcommand pages without requiring Rust.

#### Scenario: Flag added without docs update

- **WHEN** a contributor adds or changes a subcommand flag
- **THEN** the parity gate fails until generated man pages and supported-shell completions reflect the actual parser
