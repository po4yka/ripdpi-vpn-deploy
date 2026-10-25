---
id: CIC-1792922556845690
title: Keep the Xray semantic validator available after transient downloads
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: Maintainer
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-25
updated: 2026-10-25
spec_reason: tooling-only
related_tasks: []
---

## Goal

Keep checksum-pinned Xray semantic validation available when an upstream download has a transient timeout. The release commit failed before validation because its only download attempt timed out.

## Acceptance criteria

- A transient download timeout recovers within a fixed retry limit.
- Persistent download failure remains fatal and leaves the installed runtime unchanged.
- A corrupt archive remains fatal after a recovered timeout and is never executed or installed.
- The installer tests, template render check, and required local gate pass.
- Hosted CI remains unverified until the fix reaches a reviewed revision.
