## Purpose

Values vpnd forwards into make command-line assignments must survive make's recursive expansion without executing anything or breaking recipe quoting.

## ADDED Requirements

### Requirement: REQ-MAKE-KV-CHARSET — Validated variable values only

Every KEY=VALUE pair appended to a make invocation MUST pass a per-key charset allowlist before the process spawns: identifier-like keys accept [A-Za-z0-9._-], path keys accept a conservative path charset excluding make metacharacters ($, backtick, quotes, whitespace control, shell separators), and address keys accept IP literals. A rejected value MUST abort the subcommand naming both the key and the failed rule.

#### Scenario: Metacharacter in host alias

- **WHEN** a value containing $(shell ...) is passed for HOST
- **THEN** the command aborts before spawning make, naming HOST and the charset rule

#### Scenario: Legitimate path passes

- **WHEN** a canonical absolute path with dots and dashes is passed for MATRIX_CONFIG
- **THEN** the invocation proceeds unchanged
