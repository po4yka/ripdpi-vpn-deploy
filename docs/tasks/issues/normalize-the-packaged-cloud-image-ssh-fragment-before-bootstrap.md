---
id: SEC-1791451917662060
title: Normalize the packaged cloud image SSH fragment before bootstrap
kind: bug
status: doing
area: security
priority: critical
risk: high
owner: primary
parent: EPC-1788891270457728
blocked_by: []
spec_mode: required
openspec_change: sec-1791451917662060-normalize-the-packaged-cloud-image-ssh-fragment-before-bootstrap
created: 2026-10-08
updated: 2026-10-08
related_tasks: []
---

## Goal

Complete first-boot hardening on the supported image with its exact packaged
password-disabled SSH fragment, preserving strict refusal and rollback.

## Acceptance criteria

- The exact packaged fragment normalizes to canonical ownership and repeats
  unchanged; noncanonical content and unsafe files refuse before writes.
- Ordinary failures restore the original fragment; interruption can safely
  restart. Focused tests and the required local and hosted gates pass.
- The fresh node completes cloud-init through its real failed-stage rerun,
  publishes the marker and proves strict pinned SSH policy and readiness.
- Refusal-only, synthetic markers and missing positive live evidence do not
  complete this work or the fleet acceptance.
