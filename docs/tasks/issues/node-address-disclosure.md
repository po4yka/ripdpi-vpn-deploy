---
id: SEC-1794728606515594
title: Stop nodes and operator tools from disclosing node addresses
kind: bug
status: backlog
area: security
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794728606515594-node-address-disclosure
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
---

## Goal

No default sends a node address or hostname to a third-party service, a cleartext lookup, the Git worktree or a tracked file. Source: the 2026-11-15 repository audit.

## Acceptance criteria

- A host deployed with default variables sends no notification to a public service, and production refuses that service as a destination.
- Alerts name the node by alias, and no notification token or topic is in a process argument list.
- The scheduled burn check contacts no third-party probe service and sends no UDP probe; both need an explicit option on a manual run.
- Scheduled reputation and ASN lookups send the node address only over an encrypted transport and fail closed without one.
- The probing summary writes its report outside the repository with mode `0600` and no address in the file name.
- A unit test fails when a tracked text file contains a globally routable address that is not in the committed allowed list.
