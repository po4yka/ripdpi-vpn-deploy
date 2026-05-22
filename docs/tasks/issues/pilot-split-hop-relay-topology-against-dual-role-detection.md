---
title: "Pilot split-hop relay topology against dual-role detection (FOCI 2026)"
type: task
status: backlog
area: ansible
priority: medium
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[dual-role-relay-detection]]"
linked_task: null
---

- [ ] #task Pilot split-hop relay topology against dual-role detection #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Motivation

FOCI 2026 paper (Almutairi, Harfoush, Viniotis — NC State, published 2026-02-19) describes purely behavioral relay detection: per-IP, the proportion of flows where the IP both accepts inbound client connections AND initiates outbound upstream connections within the same window. The Relay Suspicion Score (RSS) achieves 23% detection at 0.18% FPR against legitimate traffic. **Payload obfuscation does not neutralize the signal** — the architectural coupling of inbound + outbound on a single IP is the observable artifact.

Our current deploy topology runs ingress (Xray inbound) and egress (foreign upstream) on the same IP, exhibiting the full dual-role signal. Countermeasure per wiki page: split-hop architecture where client-facing IP ≠ upstream egress IP.

No existing role addresses split-hop topology; the 16 current Ansible roles assume single-IP servers. This is a NEW deployment topology to pilot.

## Proposed change

Pilot a split-hop deployment as a new Ansible role (or topology variant):

1. **Architecture**: Two VPSes per profile — Node A (ingress, client-facing) forwards traffic to Node B (egress, foreign upstream) via an internal tunnel. From a flow-level observer, Node A appears single-role (only accepts inbound) and Node B appears single-role (only initiates outbound).
2. **Implementation candidates**:
   - New role `ansible/roles/split-hop-relay/` OR
   - Variant within existing roles via `group_vars/vpn-split-hop.yml` cohort.
3. **Tunnel layer between Node A and Node B**: TBD architectural decision — could be plain WireGuard, ShadowTLS, or an internal Xray relay. Must NOT create a new dual-role pattern on either node (e.g., if Node A both proxies clients and connects out via Xray to Node B, it still exhibits dual-role).
4. **Documented in `docs/SPLIT-HOP-TOPOLOGY.md`** as an architectural decision record (ADR-style).
5. **Threat-model test**: collect 24–72 h of flow data from Node A and Node B from an upstream vantage; verify each appears single-role in flow stats.

### Canonical recipe

new-role (likely) — follows §"New Ansible role" recipe. Alternatively a hybrid "topology variant" if it fits existing roles. Architecture discussion required before implementation; pilot scope first.

## Acceptance criteria

- [ ] ADR documented in `docs/SPLIT-HOP-TOPOLOGY.md` covering: motivation, two-node architecture, tunnel-layer choice, threat-model coverage, operational cost.
- [ ] Pilot deployment standable: 2 ephemeral VPSes provisioned + tunneled + tested.
- [ ] Flow-level threat-model test: 24+ h flow data from each node demonstrates single-role pattern.
- [ ] Documented cost analysis: 2× VPS cost vs single-VPS baseline — operator decision on whether to recommend split-hop as default for high-risk operators or only opt-in.

## Risks / open questions

- 2× VPS cost — may not be justified for typical operator budgets.
- Tunnel layer between Node A and Node B must itself not introduce a detectable signature OR re-introduce dual-role on Node A.
- Dual-role detection's 23% rate at 0.18% FPR — at backbone scale, manageable false positives; effectiveness depends on adversary's downstream confirmation steps (active probing, etc.).
- Whether RKN/TSPU currently runs flow-level dual-role scoring is unconfirmed; this is a defensive measure against a published technique, not a confirmed deployed threat.

## References

- [[dual-role-relay-detection]] — wiki concept page with full mechanism, RSS scoring, countermeasure table
- FOCI 2026 paper: https://www.petsymposium.org/foci/2026/foci-2026-0008.pdf
- [[censorship-update-academic-2026-05-09]] — source digest
