---
id: SEC-1793774981005821
title: Remediate medium security audit findings
kind: bug
status: backlog
area: security
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793774981005821-medium-security-remediation
created: 2026-11-04
updated: 2026-11-04
related_tasks: []
---

## Goal

Deployed nodes cannot erase their offsite backups or forge telemetry for other nodes. SSH sources stay narrow. The public site hides its nginx version, and P0 REALITY presents an owned same-host certificate.

## Acceptance criteria

- The controller refuses a node B2 credential that has `deleteFiles`, reaches outside the node prefix or bucket, enables `hard_delete`, or lacks 30-day hidden-version retention.
- The collector stores ingested series with `node` equal to the client certificate identity.
- Provider roots reject `allowed_ssh_cidrs` broader than /24 or /48.
- HTTP/80 on the public site returns no nginx version.
- P0 TCP/443 without REALITY authentication presents the certificate for the owned self-steal name, which resolves only to the P0 address.
- Node backups run on the append-only keys; the old keys are deleted.
