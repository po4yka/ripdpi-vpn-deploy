---
id: DOC-1787463115965497
title: Correct audit drift in docs and dead config keys
kind: bug
status: done
area: docs
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-08
spec_reason: mechanical-refactor
related_tasks: []
closed_at: "2026-09-08T08:51:37Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All six execution steps re-audited against the tree: dead security_controls keys removed from all.yml and vpn-prod-hardened.yml, node_manifest crowdsec rewired to intrusion_prevention.crowdsec.enabled, os-maintenance test asserts package_updates.automatic_reboot, AGENTS.md lists every role and points the Xray pin at the SOPS secret, PROVIDER-NOTES documents the UpCloud zone allowlist plus ssh_port/public_listeners, Vultr tfvars examples on Debian 13 os_id 2284; no stubs or placeholders found. remote CI observed green on the pushed final SHA fafb9cf3ff1366f6e657e6ed67e753562fef89ad (PR #86, 57 check runs: 56 success + 1 neutral Trivy config discovery, aggregate 'required checks' success), merged to main as bbb2f4189f4caf28714326b3cfbebe2716fcfdf0."
---

## Goal

Describe the observable outcome.

## Acceptance criteria

Define verifiable completion criteria.
