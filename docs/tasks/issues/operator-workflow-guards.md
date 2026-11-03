---
id: SCR-1793686598981597
title: Verify operator release inputs and encrypted recovery evidence
kind: feature
status: doing
area: scripts
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1793686598981597-operator-workflow-guards
created: 2026-11-03
updated: 2026-11-03
related_tasks: []
---

## Goal

Give operators tested release-input checks, encrypted bounded diagnostics and
catalog-bound recovery verification, with clear continuation instructions.

## Acceptance criteria

- Release checks inspect actual archive hashes and members and detect inconsistent APT policy before installation.
- Diagnostics retain encrypted output and the real exit code without plaintext logs or surviving owned processes.
- Kit checks bind selected current catalog references to private files; backup verification downloads, decrypts and verifies the full selected manifest.
- Skills match panel-only operation; continuation reuses scoped authority and reconciles interrupted work.
- Missing task tools fail before history loading; existing task validation remains intact.
- Relevant tests, the required repository gate and independent review have recorded results before the PR handoff. No live service claim follows from local tests.
