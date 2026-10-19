---
id: SEC-1792307003680932
title: Repair network protocol correctness audit defects
kind: bug
status: done
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: network-protocol-correctness
created: 2026-10-18
updated: 2026-10-19
related_tasks: []
closed_at: "2026-10-19T08:57:35Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Accepted source bc849f60a7422682c8f21826807ceee792ab9953 passed CI 39216524425 with all 92 jobs, all nine required checks and all five workflows successful. All 45 canonical native cases verify exact source, corrected engine identity and clean cleanup. Exact-tree local make check passed 8660 portable tests, 45 subtests, 65 BATS and 322 CLI tests. PRs 333 and 338 are merged; committed review 8aa6cbda and canonical archive retain historical failures and runtime limits. No deployment or private fleet access.
---

## Goal

Close the confirmed network protocol audit defects and integrate the reviewed
source through a protected PR without deployment or private fleet access.

## Acceptance criteria

- Every confirmed finding has a focused regression and source evidence.
- Existing SAN and validity fixes and the separately owned Hysteria transit fix
  are integrated without duplicate implementations.
- Complete local gates, security review, structured review and required CI pass.
- The source PR is merged to main; live and conditional risks remain explicit.
