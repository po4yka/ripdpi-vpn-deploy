---
id: CIC-1791950809934804
title: Refresh the Ubuntu Molecule image security digest
kind: bug
status: done
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-14
updated: 2026-10-14
spec_reason: dependency-only
related_tasks: []
status_detail: The scanned immutable Ubuntu dependency, all five consumer pins, 29 local regressions and exact-source hosted checks passed at 3da2e91ef73c654b75c9ed7a70b39b54062de273.
closed_at: "2026-10-14T04:46:34Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "The exact immutable Ubuntu image passed the unchanged security policy in publication run 38509685515. All five consumers use e287225b506f48360e5cb185c9ef8d8af690ad07da5b3856a2ea4c7656febe7a. All 29 local consumer regressions, applicable hooks and exact-source hosted checks passed at 3da2e91ef73c654b75c9ed7a70b39b54062de273: 92 successful checks, one optional neutral scan and 138 native tests."
---

## Goal

Clear the fixable Ubuntu Molecule image findings that block runtime and observability source acceptance, using a freshly published immutable test dependency.

## Acceptance criteria

- The exact rebuilt Ubuntu image passes the existing HIGH/CRITICAL Trivy policy without ignore additions or threshold changes.
- Every active Ubuntu image consumer and its pin regression uses the scanned digest.
- Pin and cloud-init acceptance regressions, relevant hooks and complete hosted checks pass.
- Production images, hosts and credentials remain outside this dependency refresh.
