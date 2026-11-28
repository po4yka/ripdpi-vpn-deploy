---
id: SEC-1795866391476569
title: Enforce security boundaries found in deployment audit
kind: bug
status: review
area: security
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: harden-audit-security-boundaries
created: 2026-11-28
updated: 2026-11-28
related_tasks: []
---

## Goal

Ensure that deployment accepts only explicit management, credential and firewall authority.

## Acceptance criteria

- Protect Tailnet SSH and select the Xray source IP for policy enforcement.
- Keep transport candidate data out of Ansible output and suppress backend error pages.
- Reject public placeholders, invalid secret types and missing Salamander passwords.
- Refuse provider plans with missing ingress safeguards or unreliable selectors.
