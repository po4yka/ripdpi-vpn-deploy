# Change: Guarantee secrets cleanup and scoped targeting on deploy paths

Task ID: `VPD-1787497317352770`

## Why

The vpnd deep audit found that deploy and reconverge abort on the first failing step and skip the final cleanup target, leaving the decrypted plaintext secrets file on disk after every failed deploy. Registry ipv4 values flow verbatim into ansible-playbook --limit, so a stale or typo'd entry holding an ansible pattern such as `all` widens a single-host reconverge into a fleet-wide production apply. The doctor and probe --host flags never resolve against the registry their help text documents. And the deploy summary prints the sops and decrypted-secrets file paths to stdout, violating the crate's own never-log rule.

## What Changes

- deploy and reconverge run cleanup after every outcome, including dry-run. Cleanup failure fails a successful pipeline without masking an earlier pipeline error.
- reconverge validates registry IPv4 and resolves exact inventory host keys within the selected environment/provider. A public IPv4 identifies the host; the inventory key, not the IP or an unchecked pattern, is passed to `--limit`.
- doctor and probe resolve --host against the host registry, failing for unknown aliases; probe passes the resolved address where the make target expects one.
- The pre-confirm summary no longer prints secret-file paths; it shows redacted placeholders instead.

## Capabilities

### New Capabilities

- `vpnd/deploy-lifecycle`: Cleanup guarantees, targeting validation, and diagnostics hygiene for deploy-path subcommands.

### Modified Capabilities

- None

## Impact

- `vpnd/src/commands/{deploy,reconverge,doctor,probe,host}.rs`, inventory resolution, `make clean`, and tests.
- Operators relying on pattern-valued limit fields must register real IPv4 addresses.
