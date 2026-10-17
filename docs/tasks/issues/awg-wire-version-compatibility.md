---
id: TST-1792263206120096
title: Assess AmneziaWG wire-version and arm64 compatibility
kind: research
status: backlog
area: testing
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-17
updated: 2026-10-17
spec_reason: research-only
related_tasks: []
---

## Goal

Record which exact AmneziaWG server/client versions can use the current
parameter and delivery contracts. Separate supported behavior from newer
upstream fields and unresolved Android arm64 S3/S4 behavior.

## Scope and evidence

Research only: inspect tagged source and use isolated native tests. Start
with `contract/amneziawg-arm64-version-floor.json`,
`ansible/roles/amneziawg/templates/awg0.conf.j2`,
`contract/ripdpi-bundle.schema.json` and
`scripts/ripdpi_cohort_fingerprint.py`. Compare scalar/range H values,
I1-I5 encoding and S1-S4 requirements for each exact wire version,
including the upstream 3.1 requirements. An application version does not
identify its embedded core. Existing source acceptance does not establish
a physical Android arm64 safe floor.

## Acceptance criteria

- The execution record contains an exact source/build/ABI matrix and a
  field-by-field comparison of server, emitter and consumer support.
- Native parser and bidirectional TCP/UDP/DNS observations identify each
  tested tuple; missing cases remain explicitly unverified.
- Any proposed nonzero S3/S4 safe floor has all physical arm64 evidence
  required by the existing contract, including three reconnects, sustained
  transfer and captured H4 bytes. Issue closure alone is insufficient.
- The record classifies each tuple as supported, rejected or unverified
  and identifies any required follow-up OpenSpec change before adoption.

## Safety boundaries

Keep `guard_required: true` and the existing S3/S4 refusal. Do not change
pins, schema, fingerprints, profiles or client support under this task.
Physical devices, credentials and external hosts require separate scope
and authorization. Missing evidence cannot justify a guard change.
