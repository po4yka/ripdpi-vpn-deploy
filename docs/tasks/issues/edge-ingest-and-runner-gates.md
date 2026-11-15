---
id: SEC-1794729384681094
title: Gate the UpCloud edge firewall, collector ingest and CI runner lane
kind: bug
status: backlog
area: security
priority: medium
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794729384681094-edge-ingest-and-runner-gates
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
---

## Goal

A server without a provider edge firewall, an unbounded push to the collector, a second self-hosted workflow and a hook in the agent settings are each refused by a check in the tree. Source: the 2026-11-15 repository audit.

## Acceptance criteria

- The plan policy denies an existing UpCloud VPN server that keeps the provider firewall off, and a server on any provider with no attached firewall; it allows first creation and promotion.
- The collector relay drops metric names and labels outside the allowed set and rejects series over the limit for one node while it stores series from other nodes.
- A unit test fails when a second workflow uses the self-hosted label, the configuration check fails on a weaker fork approval setting, and the image publish workflows run on push only for `main`.
- A unit test fails when the tracked agent settings file has a `hooks` key or a shell allow entry.
