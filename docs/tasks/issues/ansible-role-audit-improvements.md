---
id: ANS-1791586652330612
title: Implement remaining Ansible role audit improvements
kind: feature
status: done
area: ansible
priority: medium
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ansible-role-audit-improvements
created: 2026-10-10
updated: 2026-10-12
related_tasks: []
status_detail: Accepted integrated source cf01f94a640913412f3316b5cb288881639712ce; all 86 protected-main jobs passed. Complete local gate components now passed across native Mac/Linux with no selected skips; historical failures and external scope qualifications retained.
closed_at: "2026-10-11T20:50:40Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all86 protected-main jobs in38134843683. Complete local gate components passed across Mac/Linux; all6340 portable tests,22subtests,297CLI tests,206baseline transfers and57shell cases passed. Test clock isolation retained every assertion and deadline; production code unchanged.
---

## Goal

Implement the remaining audit improvement contracts and add observed source
results to existing PR 282, preserving all P1/P2 fixes and unrelated work.

## Acceptance criteria

- I07-I15/F43 have runnable correction or demonstrated current correctness; I01-I06 retain their bounded evidence and explicit artifact qualifications.
- Per-device auth, bounded retention/replay protection, interrupted activation, private metrics and durable notification intent have positive and failure-path proof.
- No unsafe deletion, credential exposure, compatibility shim, guard relaxation or fake live evidence is introduced.
- Reviewed snapshots, complete local gates, independent review and exact-source hosted checks pass before handoff.
- Missing full morphology source does not fabricate capability or close its unfinished feature; source/CI is distinct from provider, live client and human acceptance.
