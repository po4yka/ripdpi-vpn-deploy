---
title: "Spike: measure TSPU access-attempt-unblock pattern on bare-HTTPS endpoint"
type: task
status: backlog
area: vpnd
priority: medium
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[access-attempt-unblock-pattern]]"
linked_task: null
---

- [ ] #task Spike: measure TSPU access-attempt-unblock pattern on bare-HTTPS endpoint #repo/RIPDPI-VPN-DEPLOY #area/vpnd #status/backlog 🔼

## Motivation

Single-observer report (ntc.party #24845 Comment 10) on a Western bare-HTTPS server with `SNI=*.stackoverflow.com` describes: first access attempt after a long idle wait succeeds after ~1 minute; subsequent attempts are immediate; next idle gap re-applies the block. Three hypotheses listed in the wiki page (idle-LRU at TSPU / NAT-conntrack timeout / throttled active-probe-and-cache), none confirmed. Reproducing the pattern with proper measurement would confirm whether this is a third TSPU policy class distinct from `tls-policing-home-isps` and `tcp-connection-freezing`.

## Proposed change

Stand up a synthetic measurement rig (foreign VPS bare-HTTPS server with TLS access logs + TCP SYN logging) and measure:

1. Idle-cycle reproduction: leave the server idle for varying durations (5 min, 30 min, 60 min, 4 h, 24 h) from RU-residential vantage; attempt access; measure TLS handshake latency.
2. Server-side correlation: log every inbound SYN with timestamp + source IP; cross-reference with client-side handshake timing.
3. Active-probe detection: during the ~1-minute wait window after the first access, check server logs for connections from non-client source IPs (potential TSPU probes).
4. Threshold mapping: identify the idle duration at which the block re-applies.

Output: structured measurement report at `docs/measurements/access-attempt-unblock-<date>.md` with raw timing data + interpretation against the three hypotheses.

## Canonical recipe

no-canonical-fit — this is a measurement spike, not a structural recipe. The result feeds into either a new `vpnd probe-idle-cycle` subcommand (if findings reproduce) OR informs strategy-pack design upstream in RIPDPI client. Architecture discussion required before promoting to production.

## Acceptance criteria

- [ ] Synthetic bare-HTTPS server provisioned on foreign VPS with TLS + TCP SYN logging enabled.
- [ ] At least 5 idle-duration cycles measured from a stable RU-residential vantage.
- [ ] Measurement report distinguishes the three hypotheses with data.
- [ ] If pattern confirmed: cross-link findings into `[[access-attempt-unblock-pattern]]` wiki page as `## Field measurement 2026-XX-XX` section.

## Risks / open questions

- Single-observer report may not reproduce on different ISP / vantage combinations.
- ~1-minute waits across many idle cycles is slow — manual orchestration is feasible but tedious; consider scripting.
- "Stable RU-residential vantage" requires either a personal connection or a residential proxy — both have logistical cost.

## References

- [[access-attempt-unblock-pattern]] — source concept with three hypotheses + testable predictions
- [[2026-05-22-ntc-party-24845-tspu-multiprotocol-block]] §Comment 10 — original observation
- [[tcp-connection-freezing]] — distinct mechanism (byte-cap)
- [[tls-policing-home-isps]] — distinct mechanism (connection-count)
