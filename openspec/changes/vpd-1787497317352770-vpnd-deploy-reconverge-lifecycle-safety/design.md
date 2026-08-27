# Design

## Boundaries

- The CLI consumes the canonical rendered Ansible inventory. `make clean` also changes to quote the selected path, avoid following symlinks, and propagate removal failures.

## Decisions

- Cleanup runs after success, failure, and dry-run. A cleanup failure fails an otherwise successful command but preserves an earlier pipeline error; explain mode only prints the command.
- Parse registry addresses as strict IPv4 literals, then resolve them to exact host keys in the `vpn` inventory group with matching environment/provider. Match `vpn_service_address` before the management `ansible_host`; reject missing/ambiguous matches and host keys that could denote patterns or groups. Without `--host`, limit execution to the selected environment/provider.
- Host resolution reuses Registry::get with env/provider match identical to reconverge's existing logic, extracted into a shared helper.
- Summary rows render fixed placeholders instead of paths.

## Rollback

Single-commit revert restores prior behavior including the fleet-widening footgun; acceptable because the tightened behavior is strictly safer.

## Validation

Unit tests: failure-injection asserting cleanup runs after a failed middle step; ipv4 rejection table (all, prod:*, 999.1.1.1); unknown-host errors for doctor/probe; summary snapshot showing placeholders. cargo clippy -D warnings.
