---
id: ANS-1795163402704344
title: Harden the decoy sites against content clustering and bare-address probes
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795163402704344-decoy-site-probe-hardening
created: 2026-11-20
updated: 2026-11-20
related_tasks: []
---

## Goal

The decoy sites of the nginx-xhttp and reality-self-steal roles cannot be linked through repository-bundled bytes, send no certificate to a handshake that does not name the site, and answer TLS and HTTP probes like an ordinary nginx site. Source: the 2026-11-20 outside probe of the production nodes.

## Acceptance criteria

- Both roles refuse an operator-owned tree with a file byte-identical to a bundled file, under every environment label, and publish no dot path other than `.well-known`.
- Each nginx-xhttp TLS port has a default server that refuses a handshake without SNI or with a foreign name and answers a foreign Host with the site 404.
- Every TLS server of both roles accepts TLS 1.2 and TLS 1.3 with the groups X25519, prime256v1 and secp384r1.
- The self-steal role raises the nginx connection limits, requires 30 days of certificate lifetime and offers an opt-in TCP/80 redirect that follows the listener contract.
- The XHTTP locations keep idle streams for one hour and answer the listed upstream statuses with the site 404.
