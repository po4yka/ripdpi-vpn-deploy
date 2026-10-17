---
id: TST-1792263213110841
title: Assess exact Realm peer interoperability
kind: research
status: backlog
area: testing
priority: medium
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

Determine which exact peers can use the pinned Realm service, separating
authenticated rendezvous from the direct QUIC data path.

## Scope and evidence

Research only. Start with `ansible/roles/hysteria-realm/CLAUDE.md`, its
defaults/template and `scripts/client_payload.py`. Trace the service and
peer wire contracts at `v1.14.0-alpha.22`; compare them with exact newer
sing-box and native Hysteria candidates. Current native Realms support
does not establish compatibility with this older service tag.

## Acceptance criteria

- The execution record identifies exact tags, commits and binaries for
  each service/peer tuple; it makes no open-ended minimum-version claim.
- An isolated matrix includes the pinned sing-box control and candidate
  native/mixed peers, with TLS identity, valid/invalid auth and mismatched
  protocol outcomes recorded separately.
- Each positive tuple has authenticated rendezvous and direct
  bidirectional TCP/UDP observations. A UDP-blocked or failed hole-punch
  case cannot pass from a successful rendezvous response alone.
- The record lists tested NAT conditions and unverified cases, and gives
  a supported/rejected/unverified decision for each tuple. Any proposed
  pin or peer-contract change is assigned to a separate OpenSpec change.

## Safety boundaries

Keep the exact alpha pin, research classification, staging-only admission,
TLS verification and current peer restrictions. Do not change credentials,
listeners, profiles or deployment code. Real-host/NAT testing requires
separate authorization; local namespaces do not prove external reachability.
