# Change: Validate make variable values against make expansion metacharacters

Task ID: `SEC-1787497526094023`

## Why

The deep audit found that every KEY=VALUE pair vpnd appends to make invocations is passed without charset validation. GNU make recursively expands command-line variable values when recipes reference them, so a value containing `$(shell ...)` or a double quote executes inside recipe shells or breaks out of recipe quoting (Makefile references $(HOST), $(MATRIX_CONFIG), $(CLIENT) inside double-quoted shell strings). Every current source is operator-typed or operator-trusted, making this self-inflicted RCE today — but any second-order channel (a shared registry file, an imported secrets entry, a scripted wrapper) converts directly to arbitrary command execution on the operator workstation, contradicting the crate's own no-shell-via-string rule.

## What Changes

- A per-key allowlist validator gates every value passed through make::target_with: identifiers get token charsets, paths get strict path charset, addresses get IP literals.
- Values failing validation abort the subcommand before spawning, naming the offending key and rule.
- The validator is the single choke point; call sites cannot bypass it silently.

## Capabilities

### New Capabilities

- `vpnd/make-interface`: Charset contract for values vpnd forwards into make command-line variable assignments.

### Modified Capabilities

- None

## Impact

- `vpnd/src/runner/make.rs` and all target_with call sites; tests.
- Operators with exotic characters in client names, host aliases, or config paths must adjust those inputs.
