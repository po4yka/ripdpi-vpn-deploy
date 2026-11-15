# Change: Stop nodes and operator tools from disclosing node addresses

Task ID: `SEC-1794728606515594`

## Why

The 2026-11-15 audit found defaults that give node addresses to parties outside the fleet:
- The watchdog is on by default and posts alerts, with the node hostname, from the node to a public notification service. A node posts when its transports fail, which is when it is under observation.
- The scheduled burn check submits the node address to a third-party probe service every 30 minutes, at fixed minutes. The service keeps the address, and its vantage points open a connection to the node on each run.
- The burn check also sends a QUIC packet with one fixed version and zero padding from the operator workstation.
- The scheduled reputation and ASN lookups put the node address in cleartext DNS and whois queries.
- The probing summary writes a report whose file name contains the node address into the Git worktree, and the path is not ignored.
- No check refuses a public address in a tracked file. A node address reached the public history this way.

## What Changes

- BREAKING: the watchdog sends no notification unless the operator configures a destination. Production refuses the public notification service. Alert titles and tags carry a node alias, not the hostname.
- Notification tokens and topics no longer appear in process arguments.
- BREAKING: operator scripts and the protocol liveness monitor send alerts only when `NTFY_URL` names a service; they have no public default.
- BREAKING: the burn check uses no third-party vantage point and sends no UDP probe unless the operator asks for it on the command line. The scheduled entry never does.
- Scheduled reputation and ASN lookups use an encrypted transport, or do not run.
- Node reports are written to the private operator state directory, with mode `0600`.
- A repository test refuses a globally routable address literal in a tracked text file, except for an explicit list of well-known public service addresses.

## Capabilities

### New Capabilities

- `security/node-address-disclosure`: node addresses and hostnames stay out of third-party services, cleartext lookups, the worktree and tracked files by default.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/watchdog/`, `ansible/group_vars/all.yml`.
- Scripts: new `scripts/ntfy-curl-config.sh` and `scripts/doh-lookup.py`; `scripts/tspu-canary.sh`, `scripts/burn-check.sh`, `scripts/install-operator-crons.sh`, `scripts/check-ip-reputation.sh`, `scripts/probe-asn.sh`, `scripts/asn-drift.sh`, `scripts/warm-spare-watcher.sh`, `scripts/reality-target-monitor-probe.sh`, `scripts/monitor-protocol-liveness.py`, `scripts/probing-summary.sh`.
- Tests: `tests/unit/test_repository_identifier_policy.py` and the tests of the changed scripts and role.
- Secrets: `watchdog_secrets` keeps its keys. A deployment that relied on the default destination must set one.
- Operations: installed operator cron entries change after `make install-operator-crons` runs again.
