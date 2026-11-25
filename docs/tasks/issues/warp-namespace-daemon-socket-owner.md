---
id: SCR-1795584057908911
title: Admit the WARP daemon tunnel socket in the namespace relay-owner check
kind: bug
status: doing
area: scripts
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795584057908911-warp-namespace-daemon-socket-owner
created: 2026-11-25
updated: 2026-11-25
related_tasks: []
---

## Goal

The WARP cohort deploys: `namespace.py refresh` is no longer refused with `foreign-relay-owner` because of the vendor daemon's own underlay socket on the namespace relay address. Found on the 2026-11-24/25 staging run at revision 60a371e4b; it blocks step ANS-1795358069969748 of ANS-1795357817411977.

## Acceptance criteria

- In the WARP namespace the socket-owner admission accepts a root-owned UDP socket on the relay address that is connected to a peer other than the host side of the namespace link.
- A non-root owner, an unconnected socket, a socket connected to the host side of the link and a socket with an unreadable peer stay refused with `foreign-relay-owner`; the host check does not change.
- `tests/unit/test_transport_egress_kernel.py` covers the admitted and the refused cases and passes; `make check` passes.
- A separately authorized staging rerun of the WARP cohort shows the refresh admitted and tunnel traffic passing after it.
