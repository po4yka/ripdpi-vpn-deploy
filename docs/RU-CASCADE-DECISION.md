# ADR — RU-entry AmneziaWG GeoIP-split cascade

**Date:** 2026-07-10
**Status:** No-go — the 2026-07-11 confirm-or-kill gate did not produce a qualifying RU-side per-ASN attestation. The governance structure below remains the record of what was approved conditionally, but Phases 1–6 must not start.
**Scope:** new cascade ingress/egress role pair (not yet implemented), a dedicated RU-hosting jurisdiction EXCEPTION tier, a fail-closed classifier invariant, and an empirical per-ASN attestation gate.
**Source anchor:** Habr 1056220 (community report), read against this repo's existing `PROVIDER-NOTES.md` ASN risk tiers and `ROLE-TIERING.md` tier guard.

## Context

At class level, the cascade under discussion is a single RU-hosted entry node that terminates client connections and, per destination, either serves RU-destination traffic directly from the RU host or forwards non-RU-destination traffic through a tunnel to a foreign exit node. The split is destination-driven and happens entirely on the server side; the client is unaware of it and requires no schema or code change to work with a cascade entry versus any other entry (see the android-side client-transparency ADR cross-referenced below).

The motivation for considering this shape at all is "whitelist riding": some RU-hosted ASNs currently sit outside the filtering treatment this repo's `PROVIDER-NOTES.md` documents for the foreign-datacenter ASN bucket (the TCP-freeze pattern seen on OVH/Hetzner/DigitalOcean-class ranges). If an entry point terminates on an RU-hosted IP that already rides a domestic allowlist, it may be reachable through a path a foreign-hosted-only entry cannot use. That is the entire case for touching RU hosting at all; it is not a claim that RU hosting is generally safer, and it does not change this repo's default provider guidance.

This is the repo's first hosting-jurisdiction exception. The org sign-off recorded here is deliberately narrow: RU-jurisdiction hosting is accepted specifically for a temporary, opt-in entry node whose sole purpose is riding a domestic allowlist. It is never a default, never a `Preferred` or `Acceptable` provider tier, and the legal, data-retention, compulsion, and seizure exposure that comes with RU-jurisdiction hosting is accepted as a known, bounded tradeoff scoped to that temporary node — not as a general repo posture toward RU hosting.

`SPLIT-HOP-TOPOLOGY.md` already establishes a two-node pattern in this repo, so the natural first question is whether the cascade is a variant of split-hop. It is not, and Decision 1 below records why.

## Decision

### 0. Confirm-or-kill outcome: no-go

On 2026-07-11 the first-attestation gate was executed against the operator-accessible measurement paths. No candidate ASN produced evidence from a genuine RU-side vantage demonstrating a current reachability advantage over the foreign-VPS baseline. The accessible vantage was not RU-side and therefore could not qualify; no brand, corporate relationship, historical report, or non-RU observation was substituted for the missing per-ASN measurement. Consequently no record can truthfully set `verified-not-brand-inferred: true`, no passing attestation artifact exists, and the gate remains closed.

The latent tradeoff makes the absence of a measured benefit dispositive. An RU-AS entry could escape the foreign-datacenter TCP-freeze bucket, but it would also enter the anticipated RKN TLS-fingerprint and rate-enforcement path on a flagged RU AS while adding the legal, retention, compulsion, and seizure exposure already accepted only conditionally in this ADR. With no demonstrated reachability advantage to offset those costs, provisioning the entry node is not justified.

This is the kill outcome required by the gate, not a request to proceed with implementation while evidence is collected later. The cascade effort stops at Phase 0: no isolated Terraform root, role pair, classifier, attestation wiring, tests, reconciliation, or promotion work may begin under this decision. Reconsideration requires a new governance decision backed first by a fresh, traceable, dated RU-side measurement for a specific candidate ASN; the present no-go must not be reinterpreted as a stale or implicit pass.

### 1. Separate role pair, not a split-hop extension

The cascade is implemented as a new, separate ingress/egress role pair, not as an extension or flag on `split-hop-egress`.

`SPLIT-HOP-TOPOLOGY.md`'s directional invariants (initiator-must-be-B, no-listen-on-B) defend a specific threat model: a flow-level observer scoring whether a single IP simultaneously accepts inbound and initiates outbound within the same window. That defense depends on Node A never being the tunnel initiator. A cascade entry node is, by definition, client-facing — it accepts inbound client connections as its primary job. Folding cascade behavior into the split-hop role would either invert split-hop's single-role guarantee on the node that gains cascade behavior, or require the cascade node to impersonate split-hop's Node A/Node B roles for a purpose they were not designed for. Neither is acceptable, so the two mechanisms stay structurally separate: split-hop defends against dual-role flow correlation, and the cascade role pair defends nothing about flow correlation — it exists purely to give an RU-terminated entry point a domestic-allowlist path, with the geo-split classification happening downstream of that entry.

The role pair (working names only, not yet implemented, subject to change during Phase 2 design): a cascade-ingress role for the RU-hosted, client-facing entry, and a cascade-egress role for the foreign exit that receives forwarded non-RU-destination traffic. Concrete transport, listener, and tunnel-layer choices are Phase 2/3 implementation questions, out of scope for this ADR.

### 2. RU-hosting jurisdiction EXCEPTION tier

RU-jurisdiction hosting for the cascade-ingress role is gated behind a new EXCEPTION tier, orthogonal to the CORE / TACTICAL / RESEARCH deploy-readiness tiers `ROLE-TIERING.md` already defines. EXCEPTION is not a readiness tier; it is a jurisdiction-risk gate that sits in front of the existing tiering, and it applies to exactly one role pair for now.

Three structural properties are decided here, implementation deferred to Phase 1:

- **Isolated Terraform state.** The cascade-ingress host's Terraform state lives in its own root, separate from the state that provisions every other role in this repo. A jurisdiction exception must not share a state file, a plan, or an apply cycle with the non-exception fleet.
- **Literal, non-boolean opt-in.** Enabling the EXCEPTION tier is not a single `enable_*: true` flag. It requires an explicit, named opt-in that names the specific host and the specific temporary purpose, mirroring the `allow_research_roles` list-of-names convention `ROLE-TIERING.md` uses for research-tier overrides rather than a blanket switch.
- **A new `PROVIDER-NOTES.md` risk row.** RU-jurisdiction ASNs get their own row in that document's risk table, distinct from the existing `Avoid` / `Acceptable` / `Preferred` rows, carrying the legal-exposure caveat above. `ROLE-TIERING.md` and `PROVIDER-NOTES.md` are being amended separately to carry these entries; this ADR records the decision to make those amendments, not the amendments themselves.

### 3. Fail-closed classifier invariant

The server-side destination classifier that decides RU-destination-direct versus foreign-exit-tunneled is tri-state: RU, foreign, or dataset-unavailable. `dataset-unavailable` hard-blocks serving on that classification path — it is a confidentiality and policy invariant, not an availability tradeoff, and it has no operator override.

This mirrors the reasoning `ROLE-TIERING.md` applies to fail-closed geodata dependencies elsewhere in the repo, but is stricter: for the cascade, silently defaulting an unclassifiable destination to either RU-direct or foreign-tunneled would leak the RU-direct path's traffic-shape signal onto destinations it was never verified for, or would silently drop the allowlist-riding property the entire cascade exists to provide. Neither degraded mode is acceptable, so the third state hard-blocks instead of guessing.

Phase 4's test strategy must include a required forced-empty scenario — a test that starts from an empty or stale classifier dataset and asserts the hard-block behavior — as a first-class dimension alongside the normal-path tests. A green happy-path suite never substitutes for this test; this repeats the general principle `SPLIT-HOP-TOPOLOGY.md` and `ROLE-TIERING.md` already apply to silent-failure surfaces elsewhere in the fleet.

### 4. Empirical per-ASN attestation gate

Provisioning the cascade-ingress role requires a recurring, expiring, fail-closed attestation: a dated, per-ASN measurement confirming the candidate RU-hosted ASN is actually riding the domestic allowlist it is being provisioned for. The attestation schema and the checker that enforces it are specified separately in `docs/CASCADE-ASN-ATTESTATION.md` (companion document, tracked under Phase 3 below).

The live measurement itself has not been run as part of this ADR and cannot be produced from a governance-only pass — it requires an RU network vantage point and a real candidate host, both of which are operational activities outside this document's scope. Accordingly, the attestation record for any named candidate ships in a `PENDING` / `UNVERIFIED` state by default, and that state hard-blocks provisioning until an operator supplies a real, dated, per-ASN attestation. A brand-based or assumed pass — treating "this is a well-known RU cloud provider" as sufficient — is explicitly the anti-pattern this gate exists to prevent, and no code path may synthesize a passing attestation.

The evidence motivating a *recurring* rather than one-time gate: a single anecdotal report of an ASN split within one provider (two legally distinct entities operating under related branding, observed to sit on different ASNs with different allowlist treatment) stands in tension with a separate, larger-sample measurement showing continued allowlist presence for the same provider family. The two data points do not resolve to a stable answer, which is itself the argument for re-verification on a cadence rather than a single sign-off.

## Phased plan

- **Phase 0 — governance / ADR (this document).** Decision recorded; no code, no Terraform, no role scaffolding.
- **Phase 1 — isolated Terraform root.** State isolation from Decision 2 stood up; not wired to any provisioning path yet.
- **Phase 2 — role pair and classifier, default-off.** cascade-ingress / cascade-egress roles and the tri-state classifier land, absent from every family profile (`all.yml`, `vpn-p0-minimal.yml`, `vpn-family-standard.yml`, `vpn-device-full.yml`), consistent with how `ROLE-TIERING.md`'s guard keeps unproven mechanisms out of the default fleet.
- **Phase 3 — attestation-gate wiring.** The checker described in `docs/CASCADE-ASN-ATTESTATION.md` is wired to block provisioning on anything other than a current, passing, per-ASN attestation.
- **Phase 4 — fail-closed and role-compatibility tests.** Full test-dimension coverage for the tri-state classifier, including the required forced-empty scenario from Decision 3, plus tests asserting the cascade role pair does not silently interact with split-hop's directional invariants when both are present in an inventory.
- **Phase 5 — cross-repo documentation reconciliation.** `ROLE-TIERING.md`, `PROVIDER-NOTES.md`, and the android-side client-transparency ADR are reconciled against whatever Phase 2–4 actually ships, closing any drift between this governance document and the amended docs it currently only proposes edits to.
- **Phase 6 — promotion criteria.** Promotion out of EXCEPTION-only, lab-only status requires, at minimum: a passing current attestation (Decision 4), full Phase 4 test coverage including the forced-empty scenario, and resolution of the inherited split-hop per-leg watchdog gap — `SPLIT-HOP-TOPOLOGY.md`'s open item that a downed egress leg is currently silent to the ingress side's health checks — as a hard blocker if the cascade role pair is ever deployed alongside a split-hop egress on the same fleet. This gap is not created by the cascade; it is inherited exposure that promotion must not paper over.

## Reuse-vs-new map

| Reused (shape, not contract) | New for this ADR |
|---|---|
| Tier / guard mechanism pattern from `ROLE-TIERING.md` (a tag plus a two-layer static+deploy-time guard) | The EXCEPTION tier itself, and its guard, which gates on hosting jurisdiction rather than deploy readiness |
| `allow_research_roles`-style literal, per-name opt-in (no blanket boolean) | The specific opt-in list for EXCEPTION-tier hosts |
| Secrets-handling and no-log conventions already established for every role in this repo | — |
| Scoped `nftables` perimeter convention already established for every role in this repo | — |
| SHA256-pinned dataset pipeline pattern used for the existing geodata role | The classifier's specific dataset content and refresh cadence |
| — | Two new roles (cascade-ingress, cascade-egress) |
| — | The tri-state fail-closed classifier boundary |
| — | The per-ASN attestation schema and checker (`docs/CASCADE-ASN-ATTESTATION.md`) |
| — | An isolated Terraform root for the EXCEPTION-tier host |

This map exists to keep Phase 2 implementation honest: it reuses the *shape* of existing mechanisms (tiering, opt-in lists, secrets discipline, pinned datasets) without reusing their *contracts* — the EXCEPTION tier is not a fifth entry in the existing CORE/TACTICAL/RESEARCH enum, and the cascade roles are not a mode of `split-hop-egress`.

## Open decisions

- **EXCEPTION tier versus a RESEARCH sub-flag.** Whether jurisdiction risk deserves its own orthogonal tier (as decided above) or could instead have been modeled as a specially-flagged research role is not fully closed; the orthogonal-tier choice is recorded as the working decision but may be revisited once Phase 1 Terraform isolation is built and its operational cost is known.
- **Re-verification cadence for the attestation gate.** Decision 4 establishes that attestation must be recurring and can expire; the specific interval is not set here and is deferred to `docs/CASCADE-ASN-ATTESTATION.md`.
- **Co-location with split-hop.** Whether a cascade-ingress host may ever share a fleet, or a host, with a split-hop deployment is unresolved. The two mechanisms currently look mutually exclusive by default topology (split-hop's Node A is not client-facing in the same way), but this has not been proven incompatible or compatible; Phase 4's role-compatibility tests are meant to settle it empirically rather than by inspection.
- **Who signs the attestation.** Decision 4 requires a dated, real per-ASN attestation before provisioning; who is authorized to produce or approve that attestation (operator only, or a defined second reviewer) is not yet decided.

## Caveats

- The single report motivating this ADR — that two legally distinct entities within one provider family sit on different ASNs with apparently different allowlist treatment — is anecdotal and observation-grade. It is in tension with a separate, larger-sample measurement showing continued allowlist presence for the same provider family. This is why Decision 4 requires recurring re-verification rather than a one-time or brand-based sign-off.
- Moving an entry node's egress off the foreign-datacenter ASN bucket that `PROVIDER-NOTES.md` already documents as triggering TCP-freeze is a trade, not an unqualified improvement: it exchanges one enforcement path for a different, already-anticipated enforcement path on flagged RU cloud ASNs (TLS-fingerprint and rate-based treatment). Both the current context section's org sign-off and this caveat should be read together — the tradeoff is accepted as bounded and temporary, not resolved.
- Split-hop's directional invariants defend a different threat model (dual-role flow correlation) and do not transfer to the cascade. A cascade entry node is inherently client-facing, which would invert split-hop's guarantee if the two were merged — this is the full rationale behind Decision 1's separate role pair, restated here as a standing caveat against any future attempt to unify them.
- The fail-closed classifier behavior on empty or stale data (Decision 3) is a confidentiality and policy invariant, not an availability tradeoff. A passing happy-path test suite must never be treated as sufficient evidence that the invariant holds; the forced-empty test is required, not optional.
- IPv4-only and CGNAT-incompatible are class-level preconditions for the cascade-ingress role — a client-facing entry point on this class of RU hosting cannot rely on IPv6 parity or on being reachable from behind carrier-grade NAT on the entry side. These constraints are noted here as scope-defining preconditions; the operational detail of how they are satisfied is intentionally out of scope for a governance document.

## Cross-references

- `docs/ROLE-TIERING.md` — being amended separately to record the EXCEPTION tier alongside the existing CORE/TACTICAL/RESEARCH guard.
- `docs/PROVIDER-NOTES.md` — being amended separately to add the RU-jurisdiction risk row referenced in Decision 2.
- `docs/CASCADE-ASN-ATTESTATION.md` — companion document specifying the attestation schema and checker referenced in Decision 4 and Phase 3 (tracked separately; not yet landed).
- `docs/SPLIT-HOP-TOPOLOGY.md` — prior two-node ADR in this repo; Decision 1 above explains why the cascade does not extend it, and Phase 6 inherits its open per-leg watchdog gap as a promotion blocker for any co-located deployment.
- `docs/CDN-DECISION.md` — sibling flat-file ADR this document's structure follows.
- android repo `docs/adr/0009-cascade-client-transparency.md` — the client-side counterpart recording that the cascade requires no client schema or code change; this ADR's context section assumes that transparency guarantee holds.
