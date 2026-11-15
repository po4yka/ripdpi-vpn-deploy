---
id: XRY-1794729068388916
title: Give each node one TLS identity and an operator-owned decoy
kind: bug
status: doing
area: xray-config
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: xry-1794729068388916-single-tls-identity-and-decoy
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
---

## Goal

A production address presents one TLS identity, or the operator recorded why not. No production node serves decoy bytes that this repository publishes. Port 80 behaves like the decoy site. Source: the 2026-11-15 repository audit.

## Acceptance criteria

- The self-steal role publishes the site from `reality_self_steal_public_site_dir` and refuses production when it is empty.
- The REALITY target validator reports `target_network` as `same_asn`, `different_asn`, `unknown` or `not_applicable` from `NODE_ADDRESS` and prints no name, address or ASN number.
- Production preflight refuses a borrowed REALITY target beside Hysteria or nginx-xhttp on the same address, and a target recorded as `reality_target_network: different_asn`, unless `tls_identity_exception` holds a reason. It contacts no lookup service.
- Port 80 sends no redirect to a port other than 443 and answers an unknown Host with the decoy 404 page.
