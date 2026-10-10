---
id: ANS-1791647100922906
title: Prove historical sender samples survive failed activation
kind: bug
status: review
area: ansible
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-10
updated: 2026-10-10
spec_reason: test-only
related_tasks: []
status_detail: Historical-sample proof, all 53 consumer cases, full local gate and exact ee5be722 native/required CI passed; source-only acceptance.
---

## Goal

Prove that the pinned sender delivers a specific historical synthetic sample
after a failed activation restores its prior runtime. Replace the invalid
post-rollback pending-depth proxy with real authenticated remote-write delivery
to an isolated native Prometheus fixture. This is the approved test-only gate
repair for post-merge CI run 38062631074, not a production runtime change.

## Acceptance criteria

1. The bounded mTLS fixture acknowledges writes only after its loopback native
   receiver accepts the actual payload; forwarding failures cannot fake success.
2. A unique synthetic sample is persisted during the receiver outage, removed
   from the producer before cutover, and observed after rollback with its exact
   node, value and historical timestamp. Fresh samples and queue depth do not
   substitute for delivery.
3. Existing readiness, unit, generation, executable and queue-inode rollback
   checks remain intact. Fixture cleanup touches only owned resources.
4. Helper regression cases reject wrong nodes/values, fresh or invalid timestamps,
   missing samples and failed forwarding. Complete affected unit/render checks
   and native enabled Molecule convergence, idempotence and verification pass.
5. Exact-source protected CI passes before main integration and terminal closure.
   Runtime templates, production listeners, dependencies, pins and real fleet
   state remain unchanged.
