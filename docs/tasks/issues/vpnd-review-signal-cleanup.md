---
id: SEC-1792842686096891
title: Stop terminal reviews on worker-delivered signals
kind: bug
status: done
area: security
priority: high
risk: high
owner: CLI runtime implementation
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpnd-review-signal-cleanup
created: 2026-10-24
updated: 2026-10-24
related_tasks: []
status_detail: Deterministic actual-launcher regressions, all 12 installed CLI cases, full local gates, independent review and exact combined-main CI passed. Native cleanup is confirmed by the job log.
closed_at: "2026-10-24T18:22:09Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: The installed native CLI passed all 12 worker-signal, approval and refusal cases with actual launchers and synthetic infrastructure inputs. Full local checks, independent reviews, PR 385 and all five exact combined-main workflows passed at f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc. Native staging cleanup was confirmed in the terminal job log.
---

## Goal

Stop deploy and reconverge reviews after a handled terminal signal, including
delivery to a worker thread, and complete secrets cleanup without terminal input.
This fixes the local acceptance blocker for the quality and hopping delivery.

## Acceptance criteria

- Real launcher PTY tests deliver all four handled signals to a retained worker
  during both reviews. Each exits with 128 plus the signal, runs cleanup once,
  removes synthetic plaintext and performs no gated mutation without an answer.
- Default choices, terminal authority, queued answers, partial input, EOF,
  ignored signals and explain behavior remain correct. A signal wins over an
  answer that is ready at the same boundary.
- Cancellation removes terminal readers, preserves inherited descriptor flags and waits
  for cleanup. Repeated cancellation cannot leave cleanup detached or replace
  the primary failure. A cancelled worker must finish before cleanup starts.
  Running Make steps retain their current ownership.
- Targeted regressions, the complete vpnd tests/lint/parity, package checks,
  full local check, independent review and exact PR/main CI pass.
- Real providers, private credentials, SSH, deployment and physical devices
  are outside this change. Refusal-only or fixture-only proof cannot close it.

## Ownership

- CLI implementer owns the async terminal reader, its export, shared review and
  signal contracts, deploy/reconverge callers, narrow signal/Darwin loop dispatch,
  the retained runner cancellation join, wizard/lifecycle/runner regressions and
  vpnd folder guidance. Runner process ownership is preserved.
- Root owns task/spec planning, shared board, package and combined acceptance,
  reviewed test-environment prerequisites, Git integration and task closure.
- Independent reviewer reads the design, source and acceptance without edits.
