---
id: CIC-1791962806189740
title: Control payload probe fixture timing deterministically
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
spec_reason: test-only
related_tasks: []
status_detail: Independent completion and elapsed-time inputs now exercise the real classifier deterministically; all 10 cases pass and genuine RTT spikes remain detected.
closed_at: "2026-10-14T07:38:58Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: All 10 payload-classification cases passed in 12.23 seconds at repaired source 447b8453a46cf47805153f862d46fda279eb255a. Uniform elapsed times produce ok; a completed ladder with an actual modeled RTT spike remains throttled at 16384 bytes. Other Python invocations use the pinned interpreter. Production measurement and thresholds are unchanged; applicable hooks passed.
---

## Goal

Make payload-classification unit scenarios deterministic so host scheduling cannot fabricate an RTT spike in the runtime acceptance delivery gate.

## Acceptance criteria

- Unit scenarios control curl completion and elapsed time independently.
- A uniform complete ladder reports ok with the requested timings.
- A complete ladder with a genuine RTT spike remains throttled at the expected threshold.
- Every other Python invocation delegates to the actual pinned interpreter.
- The complete payload-probe module passes; production measurement and thresholds are unchanged.
