---
title: "Investigate RKN protocol-class signatures from deploy side (CI matrix)"
type: task
status: backlog
area: ci
priority: medium
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[rkn-protocol-class-blocking-shift-dec-2025]]"
linked_task: ../../../../RIPDPI/docs/tasks/issues/investigate-rkn-unannounced-protocol-class-signatures.md
---

- [ ] #task Investigate RKN protocol-class signatures from deploy side #repo/RIPDPI-VPN-DEPLOY #area/ci #status/backlog 🔼

## Motivation

Companion to RIPDPI Android `investigate-rkn-unannounced-protocol-class-signatures`. From the deploy side, the question is: which server-side protocol configurations are now caught by RKN's Dec-2025 protocol-class blocks, and how should `ansible/group_vars/` defaults shift to bias toward unblocked transports?

## Proposed change

Add a CI-runnable test matrix that probes the standard transport set (P0–P3 in our profile stack) from a known RU-vantage harness (or via documented operator runs against owned RU VPSes), capturing which P-tier transports currently pass.

1. New CI workflow `.github/workflows/transport-reachability-matrix.yml` (manual `workflow_dispatch`, gated on a `ci-real-deploy` label like the existing `real-vps-deploy.yml`).
2. The workflow stands up a temporary upstream VPS, applies each transport profile in sequence, and runs dpi-checkers / rkn-block-checker against it from operator-driven RU vantage.
3. Output: a generated `docs/TRANSPORT-REACHABILITY-MATRIX-<date>.md` checked into the repo via a PR.

## Canonical recipe

no-canonical-fit — measurement workflow, not a structural change. May be parked if measurement cost exceeds the value of automation.

## Acceptance criteria

- [ ] CI workflow defined and gated like `real-vps-deploy.yml`.
- [ ] First-run output produces `docs/TRANSPORT-REACHABILITY-MATRIX-2026-XX-XX.md`.
- [ ] Documented operator instructions for the RU-vantage half (the RU side cannot be fully automated; document the manual procedure).
- [ ] Findings cross-linked with the sibling RIPDPI task.

## Risks / open questions

- Real-VPS testing has cost (~$3–5/run for ephemeral UpCloud nodes).
- RU-vantage probing is the hard half; cannot be fully CI-automated without a permanent RU residential bridge.
- May overlap with future `add-rkn-block-checker-regression-baseline` task — coordinate to avoid duplicate infrastructure.

## References

- [[rkn-protocol-class-blocking-shift-dec-2025]]
- Linked client task: `investigate-rkn-unannounced-protocol-class-signatures` in RIPDPI repo
- Sibling deploy task `add-rkn-block-checker-regression-baseline` — should not be merged before that one lands
