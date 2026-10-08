---
id: TFR-1791469128152528
title: Select the actual Vultr Debian 13 image for disposable nodes
kind: bug
status: dropped
area: terraform
priority: high
risk: standard
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: tfr-1791469128152528-select-the-actual-vultr-debian-13-image-for-disposable-nodes
created: 2026-10-08
updated: 2026-10-08
related_tasks: []
closed_at: "2026-10-08T15:25:23Z"
closed_reason: Owner cancelled acceptance and requested removal of all acceptance resources
evidence_summary: Live acceptance is cancelled, not completed. Already merged implementation is preserved; temporary provider and local acceptance resources are being retired.
---

## Goal

Create an authorized disposable Vultr node with the actual Debian 13 image,
and refuse unsupported images before provisioning.

## Acceptance criteria

- Examples and validation select Debian 13 x64 as OS 2625; all approved IDs are accurately labeled.
- Rocky Linux 9 OS 1869 and unapproved IDs fail validation.
- Focused Terraform tests, policies, applicable hooks and exact-source hosted CI pass.
- The authorized replacement independently proves its actual OS, host key and strict SSH/2222 foundation.
- Existing production nodes remain intact until accepted cutover; source and mock results are not live or client proof.
