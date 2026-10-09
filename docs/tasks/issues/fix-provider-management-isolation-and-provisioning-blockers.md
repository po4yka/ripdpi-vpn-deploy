---
id: TFR-1791523370274374
title: Fix provider management isolation and provisioning blockers
kind: bug
status: review
area: terraform
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: provider-management-isolation
created: 2026-10-09
updated: 2026-10-09
related_tasks: []
status_detail: All six P1 source repairs and positive/refusal regressions complete; independent review approves; PR 281 published. Full local make check timeout gap and exact-head hosted CI pending are explicitly recorded; no infrastructure acceptance claimed.
---

## Goal

Restore provider provisioning and management isolation for all six P1 findings
in the provider audit, with an enforced saved-plan policy gate and a reviewable PR.

## Acceptance criteria

- All provider roots reject world-open management networks and public TCP
  selectors covering SSH, while valid explicit and legacy contracts still plan.
- UpCloud rejects management ports inside its stateless TCP return range.
- The operator apply path evaluates a private snapshot of the exact saved plan,
  runs every policy namespace, refuses zero evaluated rules and never applies
  after policy failure. Default dual-stack UpCloud passes secondary-IP policy.
- New Hetzner servers use current approved types and attach their firewall before
  boot; migration forgets the former attachment without detaching it.
- Bootstrap username changes on Hetzner, Vultr and Scaleway, and key changes on
  Vultr and Scaleway, require replacement and encounter prevent_destroy.
- Positive plans, state transitions, unsafe inputs and policy failures have
  observed credential-free regression coverage; make check and independent
  security review are recorded. Hosted PR checks are reported for the exact head.
- Infrastructure, guest and client acceptance remain unclaimed; unrelated work
  is preserved. The task stays in review until integration and acceptance.
