---
id: SCR-1795491503477936
title: Retire an expired never-assigned disposable liveness executor
kind: feature
status: done
area: scripts
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795491503477936-retire-expired-liveness-executor
created: 2026-11-24
updated: 2026-11-24
related_tasks: []
status_detail: All three execution steps are done; protected-main CI passed at f9d6a5139 and both leftover executors are retired
closed_at: "2026-11-24T15:19:48Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: All three execution steps are done. Protected-main ci run 45410025050 passed at f9d6a5139. make retire-expired-disposable-liveness retired both leftover staging executors (status retired-expired, receipts in the private kit config); colima list shows no liveness profile.
---

## Goal

A prepared disposable liveness executor can be left with no supported removal path: no promotion intent names it, or its run's dedicated client was already retired, so `retire-unbound-staging-executor` cannot get the client receipt it requires. Such Colima VMs then keep running on the operator machine. `make retire-expired-disposable-liveness` removes a prepared executor through the same profile journal and removal steps once its manifest has expired, because an expired manifest can never be bound.

## Acceptance criteria

- `make retire-expired-disposable-liveness EXECUTOR_MANIFEST=… EXECUTOR_RECEIPT=…` accepts only these two command-line fields, holds the machine build gate, and passes them to `scripts/disposable_liveness_executor.py retire-expired`.
- Before the manifest's `expires_at`, the command refuses with `executor-not-expired` and makes no Colima change.
- An executor that was ever assigned refuses with `executor-claimed` and makes no Colima change.
- An expired, never-assigned executor is stopped and deleted after its marker, configuration and Docker context are verified; the private receipt has the status `retired-expired` and no client field; a repeat reports `changed: false`.
- Two leftover executors from the 2026-11-22/24 staging runs are retired with the command.
