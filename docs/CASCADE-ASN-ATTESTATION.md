# ADR — Per-ASN allowlist attestation gate for the RU cascade entry node

**Date:** 2026-07-10
**Last reviewed:** 2026-07-10
**Status:** accepted (framework); attestation record below is PENDING / UNVERIFIED
**Scope:** RU-jurisdiction cascade entry node (EXCEPTION tier, opt-in only)

## Purpose

### Brand name is not a valid proxy for allowlist membership

The whole point of hosting a cascade entry node inside RU jurisdiction is to ride domestic "white lists" — network paths that RU-side filtering treats preferentially because the destination AS is judged to be a domestic or otherwise trusted network. That judgment is made at the AS (Autonomous System) level, not at the brand or company-name level, and the two do not reliably line up.

The concrete case that motivates this document: a single anecdotal, observation-grade report found that "Yandex.Cloud LLC" and "YANDEX LLC" resolve to **distinct ASNs**, and that the two ASNs do not necessarily share the same allowlist treatment. A deploy that picks a host because its provider is named "Yandex" — without checking which ASN the host actually announces from and whether that specific ASN is presently allowlisted — can silently land on the wrong side of that split. A separate, larger-sample measurement shows continued whitelist presence for at least one of these ASNs, which is in tension with the anecdotal report rather than a resolution of it. Treat that tension itself as the signal: brand name tracks marketing and corporate structure, not network topology, and the two drift apart in ways that are invisible from the provider's storefront.

### Allowlist membership is time-variable

Even a correctly identified ASN is not a permanent guarantee. Allowlist composition is an operational decision made by RU-side network operators and is not published as a stable, versioned contract. An ASN that shows a real reachability advantage today can lose that advantage on a timescale this repo cannot predict or control. Verification therefore cannot be a one-time due-diligence step; it has to be a **dated, per-ASN, expiring** record, re-established on a recurring cadence, not a fact recorded once and assumed to hold indefinitely.

These two properties — brand-name is not ASN, and ASN allowlist status is not permanent — are why this document specifies an attestation **artifact** and a **gate**, not a one-time checklist.

## Attestation artifact schema

The attestation record is a small, non-secret, checked-in metadata file. It is a claim about a *fact that was true on a given date*, not live feed data, and it never embeds a routing table, CIDR list, or ASN inventory. Proposed fields, at the field level only:

- **verified host / ASN identifier** — the specific candidate host and the ASN it was measured under at attestation time. Identifies *what* was checked, not a general provider name.
- **attestation date** — the date the underlying measurement was actually performed.
- **verified-not-brand-inferred** (boolean) — must be explicitly `true` only when the record reflects a real per-ASN measurement as described under Methodology below. A record that exists only because of a provider's marketing name, a support representative's claim, or an assumption carried over from a different ASN under the same corporate umbrella must record this as `false` (or be absent entirely — see Gate behavior).
- **verification method / artifact reference** — a pointer to the measurement class and evidence artifact that backs the attestation (see Methodology; this is a reference, not the raw data itself).
- **expiry / next-recheck date** — the date after which this record is no longer considered current and the gate must treat it as stale.

This schema is intentionally minimal and intentionally does not carry a live ASN or CIDR feed in-repo. It is a dated claim with a pointer to evidence, structured the same way `ASN-EXPOSURE-DENYLIST.md` treats external feed provenance: referenced by pointer, never copied into the repo as inventory.

## Methodology (measurement class, not runnable procedure)

This document describes what an operator must establish, at the class level. It intentionally does not include probe commands, tool invocations, or step-by-step instructions — that operational detail is out of scope for this repo's documentation and is omitted by design.

At a class level, a valid attestation requires establishing that the specific candidate ASN currently shows a **real reachability advantage** over the foreign-VPS baseline this repo already treats as the filtered-network default. "Real" here means the advantage must be produced by a method that is **independent of provider naming** — the measurement has to observe actual network behavior for that ASN from a genuine RU vantage point, not infer treatment from what the provider calls itself, from documentation, or from a different ASN that happens to share a corporate parent.

A valid attestation therefore implies:

- A genuine RU-side vantage point was used, not a foreign or synthetic one.
- The measurement targeted the specific candidate ASN, not a sibling ASN under the same brand.
- The result reflects current behavior, not a historical report or a third party's summary.
- The evidence artifact referenced in the schema is traceable back to that specific measurement.

Absent any one of these, the record does not qualify as `verified-not-brand-inferred: true` and must not be recorded as a pass.

## Gate behavior

The attestation gate is **fail-closed**, with no warn-and-continue path. Any of the following states hard-blocks both initial provisioning and ongoing deploy of the RU cascade entry node:

- No attestation record exists for the candidate ASN.
- An attestation record exists but its expiry / next-recheck date has passed.
- An attestation record exists but `verified-not-brand-inferred` is not explicitly `true` (including records that were only brand-justified).

"Hard-blocks" means provisioning and deploy stop; it does not mean a warning is logged and the run proceeds. This mirrors the fail-closed posture already established for the dataset-unavailable classifier state elsewhere in this repo's RU/foreign classification design — an unknown or stale state is treated as a blocking condition, not a permissive default.

This gate is enforced at two independent points so that a gap in one layer does not silently defeat the intent:

- **A Terraform precondition** at the provisioning layer, evaluated before any RU-jurisdiction entry-node infrastructure is created or modified.
- **An Ansible `pre_task` assert** at the deploy layer, evaluated before the RU cascade entry-node role runs against a host.

Both checks read the same attestation artifact and apply the same pass/fail logic described above. Neither layer is permitted to proceed on an attestation state it cannot positively confirm as current and non-brand-inferred.

## Current status: PENDING / UNVERIFIED

No verified attestation exists for any candidate ASN as of this document's date. The live measurement described under Methodology is an operator step that requires a genuine RU vantage point and a real candidate host, and it **has not been run**.

Because no attestation record satisfies the schema and gate requirements above, **the gate is closed**: provisioning of the RU cascade entry node must not proceed. This is the correct, intentional default — a fail-closed system with no attestation on file is supposed to block, not a bug to be worked around.

This PENDING state must not be flipped to a passing state without a real, dated, per-ASN attestation produced by the methodology described above. Recording a passing attestation on the basis of provider branding, assumption, historical reputation, or convenience is exactly the anti-pattern this document exists to prevent, and doing so would defeat the purpose of the gate entirely.

## Cross-references

- `docs/RU-CASCADE-DECISION.md` — the organizational sign-off accepting RU-jurisdiction hosting for this entry node as a temporary, opt-in exception, and the broader threat-model and structural decisions this attestation gate operates under.
- `docs/ASN-EXPOSURE-DENYLIST.md` — the sibling ASN-based gate design (denylist rather than allowlist); this document reuses its non-bundled-data, schema-first, review-gate-first posture.
- `docs/SPLIT-HOP-TOPOLOGY.md` — documents the directional invariants (initiator-must-be-B, no-listen-on-B) that defend a different threat model (dual-role flow correlation) and do not transfer to a cascade entry node, which is client-facing by definition. This is why the cascade entry/egress roles are a separate role pair rather than an extension of split-hop.

## Known caveats and open risk

- The Yandex.Cloud-LLC-vs-YANDEX-LLC ASN mismatch is a single anecdotal, observation-grade report, in tension with a separate larger-sample measurement showing continued whitelist presence. It motivates recurring per-ASN re-verification, not a one-time or brand-based sign-off, and should not be read as a settled conclusion in either direction.
- Escaping the foreign-datacenter TCP-freeze bucket by routing through an RU-AS node is a trade into a different, already-anticipated enforcement path: RKN TLS-fingerprint and rate-based enforcement on a flagged RU cloud AS. This is a latent risk carried by the design, not an unqualified improvement, and should be weighed as such when evaluating whether a given attestation's "reachability advantage" is worth the exposure.
- Fail-closed behavior on missing, stale, or brand-only-justified attestation is a confidentiality and policy invariant, not an availability tradeoff. A green happy-path test of the gate is not sufficient evidence that it works — the required test is a forced-empty / forced-stale case that confirms the gate actually blocks.
- IPv4-only and CGNAT-incompatible are entry-node preconditions for the candidate host and should be treated as class-level constraints on any host under evaluation, independent of the attestation question itself.
