---
id: SCR-1794075997223882
title: Emit INCY import material from an issued device artifact
kind: feature
status: review
area: scripts
priority: medium
risk: high
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1794075997223882-emit-incy
created: 2026-11-07
updated: 2026-11-09
related_tasks: []
---

## Goal

An operator can turn one issued device into INCY import material without hand-editing credentials: one owner-only file with a share link for every enabled P0 REALITY, P1 XHTTP and P2 Hysteria2 endpoint of that device. The AWG `.conf` keeps its existing private delivery. The first consumer is the device `personal-pixel-incy` on the Pixel 8 Pro with INCY 3.9.7.

## Acceptance criteria

- `make emit-incy CLIENT=<device> OUTPUT=<path>` writes one `vless://` or `hysteria2://` line per enabled endpoint of the selected device to a new owner-only file. It never prints credentials to stdout or logs and refuses an existing path.
- Each link carries every field the materialized payload requires (REALITY key, short ID, SNI, fingerprint, flow; XHTTP host, full path, mode; Hysteria2 auth, SNI, Salamander, port hopping), with every URI component encoded once.
- The emitter refuses a profile with a field that INCY links cannot carry (XHTTP mode other than `auto`, XHTTP pool tuning, Hysteria2 ECH or BBR) instead of dropping it.
- Unit tests compare emitted links with literal expected strings and cover each refusal.
- Device acceptance on the Pixel (import, authenticated traffic and tunnel DNS on every path) is recorded separately; it is not part of this source change.
