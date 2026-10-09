---
id: TFR-1791523370274374
title: Fix provider P1 and P2 audit defects
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
status_detail: All actionable P1/P2 source findings addressed; complete make check passed and independent review approves. P2 source 4c600d43536c2c1b1ab09b09fc9af4d5fafa1743 is published on PR 281; final-head hosted results are pending. No live acceptance or closure claimed.
---

## Goal

Restore provider provisioning, bootstrap serialization and management isolation
for the actionable P1 and P2 provider audit findings in the same reviewable PR.

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
- Vultr adapters encode canonical hyphen ranges as provider colon ranges and
  enabled backups include a valid daily schedule; disabled backups have no schedule.
- Every root rejects fractional singleton and legacy XHTTP ports. Legacy tests
  exercise the effective legacy contract and prove old XHTTP ports disappear.
- Shared cloud-init preserves scalar strings and metadata content, including
  punctuation and multiline boundaries, without altering the YAML structure.
- Previously repaired P2 groups are revalidated and the incorrect OS-ID finding
  is withdrawn; no unrelated DNS/image/default-backup changes are included.
