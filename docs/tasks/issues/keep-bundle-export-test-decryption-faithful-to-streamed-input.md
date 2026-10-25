---
id: TST-1792926788036937
title: Keep bundle export test decryption faithful to streamed input
kind: bug
status: review
area: testing
priority: high
risk: standard
owner: Maintainer
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-25
updated: 2026-10-25
spec_reason: test-only
related_tasks: []
---

## Goal

Keep bundle-export regression tests faithful to the streamed SOPS interface so scheduler timing cannot turn valid host selection into a decryption refusal.

## Acceptance criteria

- A valid bundle exports with a private input larger than a pipe buffer.
- The test adapter reads the input source selected by each SOPS invocation.
- The existing invalid-AWG consumer cases still refuse without changing authority or generating credentials.
- Relevant tests pass; remaining main CI outcomes are recorded without claiming unobserved results.
