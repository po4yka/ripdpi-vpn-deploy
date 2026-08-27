---
id: SEC-1787810718115433
title: Refresh Debian Molecule image to clear vulnerability gate
kind: bug
status: review
area: security
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: refresh-molecule-debian13-security
created: 2026-08-27
updated: 2026-08-27
related_tasks: []
status_detail: Published digest passed Trivy and PR CI run 33046238741; awaiting merge.
---

## Goal

Publish a Trivy-clean immutable Debian 13 Molecule image and repin every
scenario to it so dependency PRs can satisfy the repository's security gate.

## Acceptance criteria

- The published Debian 13 image passes the existing HIGH/CRITICAL Trivy gate
  without a new ignore entry or weaker policy.
- Every Debian 13 Molecule reference uses the published digest and none uses
  the vulnerable predecessor.
- Hosted image scan and affected Molecule CI checks are green on the merge SHA.
