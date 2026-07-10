# tools — compiled research helpers

## Design decisions

Compiled helpers live here only when the operator-facing `scripts/` layer cannot implement a protocol safely with its shell/Python runtime. Each helper has a single stdin/stdout JSON interface, locked dependencies, and a reproducible Make build target.

## What's done well

- Secrets are accepted on stdin, never command arguments or environment variables.
- Helpers return categorical, redacted errors and leave aggregation to the caller.

## Pitfalls

- Do not commit built binaries; build into the ignored helper output path.
- A helper is not a second operator interface. The Make target and scripts remain canonical.
