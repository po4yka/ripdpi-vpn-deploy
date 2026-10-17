---
id: EPC-1792155716043904
title: Deliver the local four-protocol reliability roadmap
kind: epic
status: done
area: epic
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: four-protocol-reliability-local
created: 2026-10-16
updated: 2026-10-17
related_tasks: []
status_detail: Complete exact-source local acceptance passed; all 45 positive requirements verified and owned runtimes retired.
closed_at: "2026-10-16T22:37:02Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Implementation 60689d884b1b4b1a108b2138bd7af13ca913da20 passed complete local make check, all 189 unique native cases without skips, exact AWG source-pair adoption and confirmed owned runtime cleanup. All 45 requirements are retained in canonical specs; 48 OpenSpec items validate. Supplementary exact-source CI 38955842595 passed all 89 jobs. External soak, recipient devices and production promotion are excluded by the owner.
---

## Goal

Deliver complete local REALITY, direct XHTTP, Hysteria2 and AmneziaWG reliability
with canonical per-device identity, guarded runtime authority, secure observation
and real pinned-engine acceptance. This is the local successor to
`EPC-1791618453830051` following the owner's removal of external soak and
recipient-device acceptance.

## Acceptance criteria

- Actual local engines complete authenticated traffic and reject wrong authority while private destinations, unrelated UDP and independent tunnels retain their declared isolation.
- Canonical materialization and drift/issuance agree on selected device binding, both address families, MTU, explicit XHTTP modes, bounded XMUX and independently selectable alternate identities.
- Stable local runtime/parser adoption, ECH/SNI/trust, Salamander, resource limits, warm/unchanged convergence, hopping, retirement and rollback are observed with real processes and retained authority.
- Watchdog, secure smoke and liveness use effective topology, finite ownership and exact recovery targets; a working alternate cannot conceal a failed endpoint.
- REALITY target hygiene validates normalized SAN identities, TLS 1.3/H2, complete bounded DNS candidates and finite owned process sessions without claiming browser or external-path equivalence.
- Complete portable/native source gates and every selected requirement pass without skips or uncertain owned cleanup. Redacted measurements retain exact source and runtime identities.
- Prior external scopes are explicitly superseded, their genuine observations retain their original provenance, and no staging, physical/emulated recipient, provider or production outcome is claimed.
