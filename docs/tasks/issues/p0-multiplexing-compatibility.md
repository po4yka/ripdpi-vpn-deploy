---
id: TST-1792263213777327
title: Verify P0 multiplexing wire compatibility
kind: research
status: backlog
area: testing
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-17
updated: 2026-10-17
spec_reason: research-only
related_tasks: []
---

## Goal

Determine whether emitted P0 sing-box smux profiles interoperate with the
pinned Xray VLESS/REALITY server. Separate smux, Mux.Cool, XUDP and XHTTP
XMUX instead of treating their names as equivalent.

## Scope and evidence

Research only. Start with `ansible/group_vars/all.yml` P0 shapes,
`scripts/client_payload.py` and
`ansible/roles/xray/templates/config.json.j2`. Resolve exact client engine
and mux dependency commits before comparing command bytes, destination
encoding and stream/session framing. A rolling source branch or valid
JSON is insufficient evidence of interoperability.

## Acceptance criteria

- The execution record maps exact server/client builds and dependencies
  to the emitted mux shape, with a source-level wire comparison.
- An isolated native matrix uses the unchanged emitted mux profile and
  a Vision control; it records authenticated concurrent TCP streams,
  UDP/DNS traffic, reconnects and primary/fallback listeners when emitted.
- Wrong credentials, unsupported framing and interrupted sessions have
  explicit outcomes; no case silently uses a direct or different transport
  path to turn a failure into success.
- Each tuple is supported, rejected or unverified with native evidence.
  Any confirmed incompatibility gets a separate OpenSpec change before
  server/client contracts or delivery claims change.

## Safety boundaries

Keep Vision as the default, mux disabled in that shape, and PQE on HOLD.
Do not change flow, mux settings, templates, schemas, engine pins or
fallback rules under this task. External path/device acceptance requires
separate authorization and cannot be inferred from local runtime tests.
