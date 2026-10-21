# Architecture decision records

> **Status:** Current · **Type:** decision · **Tier:** —

Accepted decisions, numbered in the order they were recorded. A decision is
never edited after acceptance; a later record supersedes it. The template
and the status-line rules are in [the style guide](../STYLE.md).

| # | Decision | Status | Tier |
|---|---|---|---|
| [0001](0001-cdn-not-filtered-path-baseline.md) | A CDN front is not the filtered-path baseline; nginx XHTTP is direct-only by default | Accepted 2026-05-11 | CORE |
| [0002](0002-role-and-doc-tiering.md) | Roles and docs are tiered CORE / TACTICAL / RESEARCH, with a guard that keeps research roles out of family profiles | Accepted 2026-06-11 | — |
| [0003](0003-split-hop-relay-topology.md) | Two-VPS split-hop relay topology against per-IP dual-role flow classification | Pilot 2026-07-26 | RESEARCH |
| [0004](0004-geoip-split-cascade.md) | Domestic-entry AmneziaWG cascade with a GeoIP split between direct and egress legs; implementation-only, hosting unauthorized | Accepted 2026-07-11 | EXCEPTION |
| [0005](0005-per-asn-allowlist-attestation.md) | Per-ASN allowlist attestation gate for the cascade ingress; empirical, expiring, fail-closed | Accepted 2026-07-11 | EXCEPTION |
| [0006](0006-pq-reality-adoption.md) | VLESS Encryption (post-quantum) over REALITY follows an enforced HOLD / STAGING / PRODUCTION policy | Accepted 2026-10-17 | CORE |

Record history: 0004 and 0005 were renamed in the 2026-10 documentation
rewrite to remove a geographic label from their file names. Git history
keeps the old names; the decision content did not change.
