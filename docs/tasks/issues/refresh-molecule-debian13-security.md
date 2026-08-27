---
id: SEC-1787810718115433
title: Refresh Debian Molecule image to clear vulnerability gate
kind: bug
status: done
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
closed_at: "2026-08-27T14:07:48Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Fresh image enumeration and scans passed in 33075359774 on main af555c20705258c989b3255e31d5cce3c7d8b4fc for both pinned digests; main CI 33071688476 passed all 51 jobs. Corrected the new capability delta from MODIFIED to ADDED before validated archival.
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
