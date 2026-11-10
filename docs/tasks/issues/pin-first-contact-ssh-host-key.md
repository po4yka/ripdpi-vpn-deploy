---
id: SEC-1794287701595900
title: Pin the SSH host key before first contact with a new node
kind: feature
status: backlog
area: security
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794287701595900-pin-first-contact-ssh-host-key
created: 2026-11-10
updated: 2026-11-10
related_tasks: []
---

## Goal

The first SSH connection to a new node uses a host key that the operator already holds. An attacker on the network path cannot make the operator trust a different key, so the first deployment cannot send decrypted secrets to a host that is not the node.

## Acceptance criteria

- Bootstrap readiness connects with strict host key checking against a private pin on every provider with a proven seed path, and no production path uses `accept-new`.
- A first contact with a different or missing host key refuses before any command runs on the remote host.
- A provider without a proven seed path refuses first contact unless the operator passes an explicit acknowledgement, and the run records that the first contact was unpinned.
- The host private key and the seed image stay out of Git, Terraform variables, outputs and cloud-init `user_data`.
- A disposable staging run on each supported provider shows the pinned first contact and the exact cleanup of the seed storage.
