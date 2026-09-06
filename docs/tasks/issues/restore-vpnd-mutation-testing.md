---
id: CIC-1788625996198006
title: Restore trustworthy vpnd mutation testing
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: Codex
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-05
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Mutation baseline and failure propagation delivered to protected main 08b4a97d.
---

## Goal

Restore the scheduled vpnd mutation lane so its real baseline can compile
embedded documentation and shared fixtures, and technical failures cannot
produce a successful workflow. This tooling repair gates confidence in vpnd
runner, doctor, QR and secrets behavior; it changes no deployment runtime.

## Acceptance criteria

- Run the complete configured mutation set with the unmutated baseline enabled.
- Preserve sibling repository build/test inputs without mutating the checkout.
- Report surviving mutants while failing baseline, timeout, usage and log errors.
- Retain diagnostics on both successful and failed runs.
- Observe regression checks and real cargo-mutants execution, then deliver the
  change to protected main with required CI passing.
