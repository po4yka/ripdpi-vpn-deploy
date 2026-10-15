# Change: Deliver bounded monitoring with isolated runtime acceptance

Task ID: `MON-1792080593038468`

## Why

The owner limited completion on 2026-10-15 to deployable source and isolated real runtimes, excluding external infrastructure. The prior monitoring task's live acceptance is cancelled separately, without relabeling its missing evidence. The implemented collector, sender and observer still need current reproducible positive runtime acceptance and representative historical replay under their resource ceilings.

## What Changes

- Deliver the existing private collector, bounded vmagent sender and independently deployable Uptime Kuma observer contracts with isolated runtime acceptance.
- Add exact historical replay for a bounded ten-node cardinality workload across receiver outage and managed sender restart, preserving public nginx and resource boundaries.
- Keep host admission, real Telegram delivery, human receipt, live VPN performance and cutover outside this source-only task; retain their checks as future deployment prerequisites.
- BREAKING: the supported monitoring topology uses VPN/collector capabilities and a typed independent observer; obsolete dedicated topology remains rejected.

## Capabilities

### New Capabilities

- `operations/resource-bounded-observability`: private bounded monitoring, independent push producers, safe activation/rollback and isolated positive acceptance.

### Modified Capabilities

- None.

## Impact

- Existing observability Ansible roles, their canonical enabled scenarios, focused tests and operator documentation. No runtime dependency, provider resource, paid service, real credential or external message is added.
- Historical evidence retains its original scope. Completion requires source, hosted CI and isolated real-runtime results rather than a live deployment claim.
