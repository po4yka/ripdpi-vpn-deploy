# Design

## Boundaries

- Rust-only change inside vpnd/src/runner/make.rs and its call sites. Makefile recipes are unchanged; the contract is enforced on the vpnd side of the boundary.

## Decisions

- Single validator function keyed by variable name; unknown keys fail closed with a conservative identifier charset rather than being allowed through.
- Path keys (MATRIX_CONFIG, PLAN) accept absolute canonical paths only: leading /, [A-Za-z0-9._/-], no .. components after canonicalization (callers already canonicalize MATRIX_CONFIG).
- ENV/PROVIDER come from Context discovery (provider already directory-checked); they pass the identifier charset naturally and gain explicit validation for defense in depth.
- No escaping layer: rejection over escaping keeps --explain honest (what you validated is exactly what spawns).

## Rollback

Single-commit revert restores unvalidated passthrough.

## Validation

Table-driven acceptance/rejection tests per key; an integration-style assertion that no spawned argv contains values failing the allowlist; cargo clippy -D warnings.
