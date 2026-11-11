---
id: ANS-1794407092808532
title: Allow the AmneziaWG IPv6 uplink in operator extra vars
kind: bug
status: doing
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-11
updated: 2026-11-11
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

`firewall_awg_uplink6_interface` (added by ANS-1794396376228431) is per host, because UpCloud attaches IPv6 to a second NIC, but the deployment controller's extra-vars allowlist refused it, so no supported input could set it for one host. The allowlist now accepts it as one safe Linux interface name.

## Acceptance criteria

- The extra-vars validator accepts `firewall_awg_uplink6_interface` only as a 1-15 character safe interface name.
- The split-hop guide names the UpCloud setting.
