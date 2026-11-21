---
id: ANS-1795259263103243
title: Serve the Hysteria masquerade site from a node-local origin
kind: feature
status: doing
area: ansible
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: [ANS-1795162466557355]
spec_mode: required
openspec_change: ans-1795259263103243-hysteria-node-local-masquerade-origin
created: 2026-11-21
updated: 2026-11-21
related_tasks: [ANS-1795163654691828]
---

## Goal

A `vpn-p2-udp` node without a web frontend serves its Hysteria masquerade site from the operator site bundle published on the node, so a probe of the node address gets a site that the node hosts instead of a proxy to another host. Follow-up of the fleet audit change `ANS-1795163654691828`, which declined this part because the site bundle of `ANS-1795162466557355` owns site publication.

## Acceptance criteria

- A node with a published site bundle renders the `file` masquerade type with the published directory.
- A node without a bundle keeps the proxy origin and its self-origin refusal.
- The role refuses a missing, empty or foreign-writable published tree before Hysteria restarts.
- A disposable staging node answers HTTP/3 on its UDP port and HTTPS and HTTP on TCP from the node-local site.
