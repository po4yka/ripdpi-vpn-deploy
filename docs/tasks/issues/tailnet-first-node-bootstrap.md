---
id: SEC-1788894219568782
title: Bootstrap restricted Tailnet access before dual-path deployment
kind: feature
status: doing
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1788894219568782-tailnet-first-node-bootstrap
created: 2026-09-08
updated: 2026-09-09
related_tasks: []
---

## Goal

Enroll a fresh node through pinned public SSH before ordinary deployment, with
durable rollback and independently verified public and restricted Tailnet SSH.
This unblocks the authorized disposable staging deployment without weakening the
existing dual-path SSH transaction or exact-node protocol promotion proof.

## Acceptance criteria

1. A canonical Make command selects exactly one node and validates clean source,
   host pins, private inputs, approved Tailnet sources, and recovery readiness
   before mutation; invalid input performs no host or provider writes.
2. Fresh enrollment and the minimum guest firewall foundation form one durable
   transaction. Timeout, controller loss, reboot, or failed path proof restores
   the original firewall and removes only the newly enrolled Tailnet identity.
3. Success requires fresh public and Tailnet SSH with the original host key,
   unchanged sshd policy, resolver ownership/content, and default routes. No
   Tailscale SSH, DNS, route, exit-node, or ACL changes are introduced.
4. Ordinary deploy still refuses a missing management path and still requires
   exact-node protocol proof. Bootstrap success never counts as VPN acceptance.
5. Disposable staging has a valid UUID-bound cleanup manifest before any guest
   mutation and a supported state-bound reissue after firewall promotion.
6. Regression, recovery, native runtime, local gates, exact-SHA hosted CI, and
   authorized disposable staging plus guarded deletion pass before closure.
   Serial production rollout remains conditional on successful staging and
   the applicable operator window; no task closes on refusal-only behavior.
