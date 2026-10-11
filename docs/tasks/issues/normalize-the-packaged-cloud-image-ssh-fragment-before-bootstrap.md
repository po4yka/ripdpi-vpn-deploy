---
id: SEC-1791451917662060
title: Normalize the packaged cloud image SSH fragment before bootstrap
kind: bug
status: done
area: security
priority: critical
risk: high
owner: primary
parent: EPC-1788891270457728
blocked_by: []
spec_mode: required
openspec_change: sec-1791451917662060-normalize-the-packaged-cloud-image-ssh-fragment-before-bootstrap
created: 2026-10-08
updated: 2026-10-11
related_tasks: []
status_detail: Integrated source cf01f94a640913412f3316b5cb288881639712ce passed all protected-main hosted checks in run 38134843683; recorded source scope and external qualifications are preserved. Archive-readiness verification passed; authorized lifecycle completion is in progress.
closed_at: "2026-10-11T15:43:23Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected integrated source cf01f94a640913412f3316b5cb288881639712ce passed all 86 CI jobs in run 38134843683. Recorded complete local source gates and independent reviews preserved; canonical requirement results resolved and OpenSpec synchronized. Source scope and all external qualifications retained. The clean first-boot helper is byte-identical to its previously accepted source; failed-stage retry remains excluded.
---

## Goal

Complete first-boot hardening on the supported image with its exact packaged
password-disabled SSH fragment, preserving strict refusal and rollback.

## Acceptance criteria

- The exact packaged fragment normalizes to canonical ownership and repeats
  unchanged; noncanonical content and unsafe files refuse before writes.
- Ordinary failures restore the original fragment; interruption can safely
  restart. Focused tests and the required local and hosted gates pass.
- The fresh replacement completes its actual clean cloud-init first boot,
  publishes the marker and proves strict pinned SSH policy and readiness.
- Refusal-only, synthetic markers and missing positive live evidence do not
  complete this work or the fleet acceptance.
