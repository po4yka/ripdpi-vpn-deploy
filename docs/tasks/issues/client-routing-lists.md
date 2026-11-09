---
id: ANS-1794214330785468
title: Host and refresh client routing lists on the subscription plane
kind: feature
status: doing
area: ansible
priority: medium
risk: high
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794214330785468-client-routing-lists
created: 2026-11-09
updated: 2026-11-09
related_tasks: []
---

## Goal

A delivery host refreshes client routing lists daily from operator-configured feeds and serves them, with the operator profile, through one stable INCY Autorouting link. A feed update that fails admission never reaches clients.

## Acceptance criteria

- `subscription.routing_lists` enables a daily admitted refresh; it stays off by default.
- A refused candidate leaves the served generation unchanged.
- Only the five client files are served under `/routing/<token>/`.
- Disabling retires only owned runtime and preserves unit masks.
- A client imports the Autorouting link on a deployed host and receives a later list update.
