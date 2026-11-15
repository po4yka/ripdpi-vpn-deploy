# SEC-1794728606515594: Stop nodes and operator tools from disclosing node addresses

## Objective

No default sends a node address or hostname to a third-party service, a cleartext lookup, the worktree or a tracked file.

## Ownership

- `ansible/roles/watchdog/`, `ansible/group_vars/all.yml`, `scripts/burn-check.sh`, `scripts/install-operator-crons.sh`, `scripts/check-ip-reputation.sh`, `scripts/probe-asn.sh`, `scripts/asn-drift.sh`, `scripts/warm-spare-watcher.sh`, `scripts/reality-target-monitor-probe.sh`, `scripts/monitor-protocol-liveness.py`, `scripts/probing-summary.sh`, `tests/unit/test_repository_identifier_policy.py`, their tests, snapshots and docs.

## Execution

- [ ] SEC-1794728786307882 Default node alerts to no public destination and drop the hostname #bug !high @item:SEC-1794728606515594
- [ ] SEC-1794728798422428 Keep burn-check off third-party vantage points by default #bug !high @item:SEC-1794728606515594
- [ ] SEC-1794728810946200 Send reputation and ASN lookups over an encrypted transport #bug !high @item:SEC-1794728606515594
- [ ] SEC-1794728832615527 Write node reports outside the worktree and refuse tracked public addresses #bug !high @item:SEC-1794728606515594

## Verification

- Focused unit tests for each script and the address guard, `make snapshot-check`, `make molecule-test ROLE=watchdog`, `make shellcheck`, one `make check`; remote CI. The watchdog change reaches nodes through the reviewed dry-run and deploy transaction after merge.
