---
id: SEC-1794729384681094
title: Gate the UpCloud edge firewall, collector ingest and CI runner lane
kind: bug
status: review
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

- The plan policy denies a plan that changes resources while an existing UpCloud server keeps the provider firewall off, and a server on another provider with no attached firewall; it allows first creation, promotion, the completion of an interrupted first apply and a plan with no resource change.
- The collector relay drops metric names and labels outside the sender's allowed set and drops unique series over the hourly limit of the whole relay (one budget for each enrolled node) while it stores series that other nodes already send.
- A unit test fails when a second workflow uses the self-hosted label, the configuration command plans a change for a weaker live fork approval setting and fails the apply readback while it differs, and the image publish workflows run on push only for `main`.
- A unit test fails when the tracked agent settings file has a `hooks` key or a shell allow entry.
