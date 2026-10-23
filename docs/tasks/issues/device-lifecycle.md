---
id: OPS-1792679812321846
title: Unify device issuance refresh and complete revocation
kind: feature
status: review
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: device-lifecycle
created: 2026-10-22
updated: 2026-10-23
related_tasks: []
---

## Goal

Provide one resumable operator workflow that issues usable per-device access,
refreshes all active grants, and revokes every matching protocol identity and
published grant across the complete declared fleet.

## Acceptance criteria

- Issue enabled protocol credentials and a usable private recipient artifact,
  preserving unrelated users and native server identities.
- Refresh all active grants without changing their URLs, formats or expiries.
- Revoke retained credentials on former nodes and disabled variants, then prove
  old native access denial and running HTTP revocation policy.
- Resume exact encrypted intent after uncertain local, remote and publication
  acknowledgements without regenerating identity or overwriting independent work.
- Observe portable and real isolated native checks, independent review, protected
  PR integration and exact-main CI. Source tests do not establish live fleet or
  physical-device acceptance; incomplete or refusal-only results remain open.
