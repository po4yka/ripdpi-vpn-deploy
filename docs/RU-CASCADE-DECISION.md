# ADR — RU-entry AmneziaWG GeoIP-split cascade

**Date:** 2026-07-10
**Status:** Implementation authorized; live activation remains no-go. The 2026-07-11 measurement did not produce a qualifying candidate-ASN attestation, so no RU-hosted server/account, provisioning apply, EXCEPTION registration, or cascade converge is authorized. A 2026-07-11 follow-up authorizes inert, default-off implementation and tests for Phases 1–6 so the complete fail-closed system can be reviewed before any hosting decision.
**Scope:** implemented-but-inert cascade ingress/egress scaffolds, a dedicated RU-hosting jurisdiction EXCEPTION tier, a fail-closed classifier invariant, and an empirical per-ASN attestation gate.
**Source anchor:** Habr 1056220 (community report), read against this repo's existing `PROVIDER-NOTES.md` ASN risk tiers and `ROLE-TIERING.md` tier guard.

## Context

At class level, the cascade under discussion is a single RU-hosted entry node that terminates client connections and, per destination, either serves RU-destination traffic directly from the RU host or forwards non-RU-destination traffic through a tunnel to a foreign exit node. The split is destination-driven and happens entirely on the server side; the client is unaware of it and requires no schema or code change to work with a cascade entry versus any other entry (see the android-side client-transparency ADR cross-referenced below).

The motivation for considering this shape at all is "whitelist riding": some RU-hosted ASNs currently sit outside the filtering treatment this repo's `PROVIDER-NOTES.md` documents for the foreign-datacenter ASN bucket (the TCP-freeze pattern seen on OVH/Hetzner/DigitalOcean-class ranges). If an entry point terminates on an RU-hosted IP that already rides a domestic allowlist, it may be reachable through a path a foreign-hosted-only entry cannot use. That is the entire case for touching RU hosting at all; it is not a claim that RU hosting is generally safer, and it does not change this repo's default provider guidance.

This is the repo's first hosting-jurisdiction exception. The org sign-off recorded here is deliberately narrow: RU-jurisdiction hosting is accepted specifically for a temporary, opt-in entry node whose sole purpose is riding a domestic allowlist. It is never a default, never a `Preferred` or `Acceptable` provider tier, and the legal, data-retention, compulsion, and seizure exposure that comes with RU-jurisdiction hosting is accepted as a known, bounded tradeoff scoped to that temporary node — not as a general repo posture toward RU hosting.

`SPLIT-HOP-TOPOLOGY.md` already establishes a two-node pattern in this repo, so the natural first question is whether the cascade is a variant of split-hop. It is not, and Decision 1 below records why.

## Decision

### 0. Confirm-or-kill outcome: no-go

On 2026-07-11 the first-attestation gate was executed out of band. A genuine RU-side baseline measurement completed across multiple independent vantage networks, but no candidate RU-hosted endpoint and candidate ASN existed to measure against that baseline without first opening an account or creating a server. The baseline therefore established measurement-path availability but could not establish the required candidate-specific reachability advantage. No brand, corporate relationship, historical report, or baseline-only observation was substituted for the missing candidate comparison. Consequently no record can truthfully set `verified-not-brand-inferred: true`, no passing attestation artifact exists, and the gate remains closed. The operator-held evidence is referenced as dated report `cascade-baseline-2026-07-11-a` with SHA-256 `82cc54ccdb1432147c1ac81cf5f9df8b99247919cc44088942efa18f2377c606`; the raw probe feed and its storage location remain outside the repo.

The latent tradeoff makes the absence of a measured benefit dispositive. An RU-AS entry could escape the foreign-datacenter TCP-freeze bucket, but it would also enter the anticipated RKN TLS-fingerprint and rate-enforcement path on a flagged RU AS while adding the legal, retention, compulsion, and seizure exposure already accepted only conditionally in this ADR. With no demonstrated reachability advantage to offset those costs, provisioning the entry node is not justified.

This remains the kill outcome for live infrastructure and serving state. The implementation-first follow-up permits code, inert Terraform state scaffolding, default-off roles, validators, tests, and documentation, but every path must remain unreachable from normal deploys and must hard-block without a fresh attestation plus a later governance activation decision. No implementation artifact may reinterpret the no-go as a stale or implicit pass, and no variable alone may turn the inert scaffold into a live provider resource.

### 1. Separate role pair, not a split-hop extension

The cascade is implemented as a new, separate ingress/egress role pair, not as an extension or flag on `split-hop-egress`.

`SPLIT-HOP-TOPOLOGY.md`'s directional invariants (initiator-must-be-B, no-listen-on-B) defend a specific threat model: a flow-level observer scoring whether a single IP simultaneously accepts inbound and initiates outbound within the same window. That defense depends on Node A never being the tunnel initiator. A cascade entry node is, by definition, client-facing — it accepts inbound client connections as its primary job. Folding cascade behavior into the split-hop role would either invert split-hop's single-role guarantee on the node that gains cascade behavior, or require the cascade node to impersonate split-hop's Node A/Node B roles for a purpose they were not designed for. Neither is acceptable, so the two mechanisms stay structurally separate: split-hop defends against dual-role flow correlation, and the cascade role pair defends nothing about flow correlation — it exists purely to give an RU-terminated entry point a domestic-allowlist path, with the geo-split classification happening downstream of that entry.

The implemented working names are `cascade-ingress` for the client-facing entry integration boundary and `cascade-egress` for the foreign exit that receives forwarded non-RU-destination traffic. Both roles remain non-serving by default, and the repository-owned governance guard blocks normal converge while this ADR remains implementation-only.

### 2. RU-hosting jurisdiction EXCEPTION tier

RU-jurisdiction hosting for the cascade-ingress role is gated behind a new EXCEPTION tier, orthogonal to the CORE / TACTICAL / RESEARCH deploy-readiness tiers `ROLE-TIERING.md` already defines. EXCEPTION is not a readiness tier; it is a jurisdiction-risk gate that sits in front of the existing tiering, and it applies to exactly one role pair for now.

Three structural properties are enforced by the implementation:

- **Isolated Terraform state.** The cascade-ingress host's Terraform state lives in its own root, separate from the state that provisions every other role in this repo. A jurisdiction exception must not share a state file, a plan, or an apply cycle with the non-exception fleet.
- **Literal, non-boolean opt-in.** Enabling the EXCEPTION tier is not a single `enable_*: true` flag. It requires an explicit, named opt-in that names the specific host and the specific temporary purpose, mirroring the `allow_research_roles` list-of-names convention `ROLE-TIERING.md` uses for research-tier overrides rather than a blanket switch.
- **A new `PROVIDER-NOTES.md` risk row.** RU-jurisdiction ASNs get their own row in that document's risk table, distinct from the existing `Avoid` / `Acceptable` / `Preferred` rows, carrying the legal-exposure caveat above. `ROLE-TIERING.md` and `PROVIDER-NOTES.md` are being amended separately to carry these entries; this ADR records the decision to make those amendments, not the amendments themselves.

### 3. Fail-closed classifier invariant

The server-side destination classifier that decides RU-destination-direct versus foreign-exit-tunneled is tri-state: RU, foreign, or dataset-unavailable. `dataset-unavailable` hard-blocks serving on that classification path — it is a confidentiality and policy invariant, not an availability tradeoff, and it has no operator override.

This mirrors the reasoning `ROLE-TIERING.md` applies to fail-closed geodata dependencies elsewhere in the repo, but is stricter: for the cascade, silently defaulting an unclassifiable destination to either RU-direct or foreign-tunneled would leak the RU-direct path's traffic-shape signal onto destinations it was never verified for, or would silently drop the allowlist-riding property the entire cascade exists to provide. Neither degraded mode is acceptable, so the third state hard-blocks instead of guessing.

Phase 4's required paired Molecule scenarios include a populated dataset and a forced-empty dataset. The forced-empty scenario asserts that ingress configuration is not rendered and serving state is not entered. A green happy-path suite never substitutes for this test; both scenarios are required by CI.

### 4. Empirical per-ASN attestation gate

Provisioning the cascade-ingress role requires a recurring, expiring, fail-closed attestation: a dated, per-ASN measurement confirming the candidate RU-hosted ASN is actually riding the domestic allowlist it is being provisioned for. The attestation schema and the checker that enforces it are specified separately in `docs/CASCADE-ASN-ATTESTATION.md` (companion document, tracked under Phase 3 below).

The baseline portion of the measurement ran out of band on 2026-07-11, but the candidate-specific comparison cannot run until a real candidate endpoint exists. Accordingly, the attestation record for any named candidate remains absent and therefore `PENDING` / `UNVERIFIED`; that state hard-blocks provisioning until an operator supplies a real, dated, per-ASN attestation. A brand-based or assumed pass is explicitly the anti-pattern this gate exists to prevent, and no code path may synthesize a passing attestation.

The evidence motivating a *recurring* rather than one-time gate: a single anecdotal report of an ASN split within one provider (two legally distinct entities operating under related branding, observed to sit on different ASNs with different allowlist treatment) stands in tension with a separate, larger-sample measurement showing continued allowlist presence for the same provider family. The two data points do not resolve to a stable answer, which is itself the argument for re-verification on a cadence rather than a single sign-off.

### 5. Cascade and split-hop role families are mutually exclusive per host

No host may enable either cascade role alongside either split-hop role. This is host-level mutual exclusion across all four pairings: proposed `cascade-ingress` or `cascade-egress` with existing `split-hop-ingress` or `split-hop-egress`. It does not prohibit separate hosts in one inventory from carrying the two different topologies, but no VM, physical node, inventory host, or public IP identity may serve both role families.

The reason is architectural rather than an anticipated nftables collision. Split-hop's `initiator-must-be-B` and `no-listen-on-B` invariants preserve a single-role flow appearance: Node A accepts inbound without initiating the protected outbound leg, and Node B initiates without exposing a listener. Cascade ingress is intentionally client-facing and must originate direct RU-destination traffic or the foreign-egress tunnel, which would recreate the dual-role signal on a split-hop Node A. Cascade egress must receive the cascade tunnel and initiate destination traffic, which would add a listener/accepted flow to a split-hop Node B. A flow observer sees the combined behavior of the host and IP, not the Ansible role, interface, routing table, or nftables-table boundary, so independently scoped firewall state cannot restore either split-hop invariant.

Passing the jurisdiction-exception and research-tier gates would authorize two risky features independently but would not make their directional contracts compatible. Co-location therefore has no override and is not conditionally enabled by satisfying both gates.

The structural guard is an `always`-tagged play pre-task named **Guard — cascade and split-hop role families are mutually exclusive**, evaluated before either family runs. It derives the two family-enabled states from their role toggles, treats undefined toggles as `false`, and asserts that both families are not active together. Failure names the host and conflicting enabled roles, then stops before package, service, interface, route, or firewall changes. Each cascade role also begins with its own `always`-tagged direct-execution assertion that treats inclusion of that role as proof the cascade family is active and rejects either split-hop toggle; duplicating this small safety assertion keeps each role independently fail-closed without introducing a shared base before Decision 7's reopen trigger. No `allow_colocation` variable or warn-only mode is permitted. Tests cover all four cross-family pairings plus each family alone.

### 6. A per-leg watchdog is a hard EXCEPTION-registration blocker

The cascade role pair may not be registered for the EXCEPTION tier until every configured ingress-to-egress leg has an operational per-leg watchdog and a fresh healthy result. This is stricter than a promotion-only criterion: registration is the moment the repository accepts the jurisdiction exposure and permits a client-facing ingress, so allowing a known silent far-leg failure during the EXCEPTION phase would spend the risk budget before proving the two-node service works. The same requirement remains an explicit blocker for any later promotion; promotion revalidates it rather than introducing it for the first time.

This deliberately diverges from split-hop's current unenforced treatment. `SPLIT-HOP-TOPOLOGY.md` records the same “ingress answers while egress is down” gap as a follow-up, but the RESEARCH pilot can still be stood up with operator-driven verification. That precedent is not carried into the cascade: the cascade adds RU-jurisdiction exposure, an allowlist-dependent purpose, and destination-dependent direct-versus-forward policy, so a known silent loss of the forwarded leg is incompatible with registration. This decision does not retroactively promote or repair split-hop; it names its unenforced posture as the weaker precedent.

The required health signal is end-to-end and per leg. From the ingress side it must exercise the configured cascade forwarding path through the selected egress, complete an authenticated protocol-level exchange with a controlled target on the forwarded path, validate the semantic response, and observe the response return through that leg. Process state, an open local socket, a tunnel interface marked up, a successful TCP connect without protocol completion, or a self-dial that never traverses the egress cannot satisfy the signal.

The signal must distinguish a transient miss from a far-leg-down state. Checks run on five-minute intervals: one failed completion marks the leg degraded, and three consecutive failed completions in distinct intervals, while the ingress-local control remains healthy, classify the far leg as down. A successful end-to-end completion resets the failure streak. Registration accepts only a healthy record no more than ten minutes old; missing, stale, degraded, or far-leg-down observations block even when they are insufficient to diagnose the far leg specifically. The checked-in `cascade-leg-probe.py` implements the operator-side signal producer with an authenticated HTTPS completion over the selected leg and a separate direct-interface control, expected response-status and body-digest validation, a persistent failure streak, and redacted evidence. Target ownership, URL, bearer token, interface identities, and expected digest remain operator-supplied and are not committed. The role installs the script and its config schema but renders its service and five-minute timer disabled behind a literal false execution condition, never enables either unit, and cannot satisfy registration without a real target plus a fresh healthy record.

### 7. Defer a literal shared ingress base

The repository will keep the shared split-hop/cascade ingress conventions documented rather than extracting a literal shared Ansible base now. `split-hop-ingress` is still RESEARCH, cascade ingress has only a non-serving scaffold while its concrete per-connection adapter remains intentionally unimplemented, and the apparent overlap—secret-block shape, `no_log`/diff suppression, a role-scoped nftables table, and tier/guard registration—is presently a set of conventions rather than a cohesive module with a small interface. Extracting it now would create a shallow module whose callers still need to supply nearly every contract-specific secret, template, table, routing, guard, handler, and lifecycle choice, increasing coupling before two stable adapters exist.

This decision must be reopened only when all of the following are true: split-hop has graduated out of RESEARCH; a new governance decision has reversed the cascade no-go and both ingress roles have concrete implementations; and behavior-neutral tests pin each role's observable pre-refactor behavior through its own interface. Those tests must cover secret validation failure, secret-bearing render redaction and file permissions, scoped table ownership/lifecycle, handler/service behavior, and tier/guard rejection. Meeting only one trigger is insufficient. At that point the implementations must be compared again, and extraction proceeds only if real duplication remains and the proposed shared interface is smaller than the behavior it hides.

The reopen evaluation may consider sharing generic secret-render hardening, scoped resource naming/lifecycle checks, and tier-manifest/guard registration mechanics. It must permanently exclude split-hop's directional invariants—`initiator-must-be-B`, `no-listen-on-B`, responder-only peer shape, keepalive direction, conntrack direction/UID marking, and the routes that preserve the single-role flow appearance. Cascade destination classification, RU-direct versus foreign-forward behavior, EXCEPTION attestation, and per-leg registration watchdog policy are likewise contract-specific. No shared base may turn either role family's threat-model contract into configurable flags on a common shallow interface.

## Phased plan

- **Phase 0 — governance / ADR:** complete. Live activation remains no-go.
- **Phase 1 — isolated Terraform root:** complete as an inert root with separate local state, no provider resource, no normal Terraform router integration, and an apply path that always blocks.
- **Phase 2 — role pair and classifier, default-off:** complete as non-serving scaffolds with a concrete disabled per-connection adapter. `cascade-ingress` and `cascade-egress` are absent from every family profile; the password-authenticated loopback SOCKS5 CONNECT adapter classifies each resolved destination as `ru`, `foreign`, or `dataset-unavailable`, binds RU and foreign connections to distinct configured interfaces, refuses to listen when the dataset is unavailable, and revalidates any dataset generation change before accepting another connection. Xray resolves domain traffic through built-in TCP DNS queries that themselves traverse the classifier, passes only resolved IP destinations to the adapter, sends only TCP to it, and blackholes UDP rather than bypassing classification. Cascade ingress and WARP routing are structurally incompatible because no earlier optional route may bypass uniform classification. The rendered adapter unit contains a literal false execution condition, and no service task or handler enables or starts it.
- **Phase 3 — attestation-gate wiring:** complete. One checker enforces the weekly schema inside the isolated Terraform root, at its single-purpose plan/apply boundaries, and at the Ansible pre-task boundary. Missing, stale, malformed, brand-only, or unavailable verification blocks.
- **Phase 4 — fail-closed and role-compatibility tests:** complete. Unit fixtures cover all classifier states, paired Molecule scenarios cover populated and forced-empty datasets, and structural tests cover family exclusion and cascade/split-hop mutual exclusion. Both Molecule scenarios are required by CI.
- **Phase 5 — deploy-side reconciliation:** complete in this repo. `ROLE-TIERING.md`, `PROVIDER-NOTES.md`, and `server-integration.md` describe the shipped inert contract. No Android-repo change or client-visible diagnostic label is included.
- **Phase 6 — promotion criteria:** documented and blocked. Promotion requires a passing current attestation, required fail-closed coverage, an operator-configured probe producing a fresh per-leg authenticated protocol-completion signal, and a future governance commit changing the repository-owned lifecycle state. A missing, stale, disabled, or unhealthy per-leg signal is an explicit blocker even if local ingress processes and sockets remain healthy.

## Preconditions for any future live activation

Implementation completion does not clear the no-go. A future operator may reconsider live activation only after all of the following happen in order: organizational RU-hosting sign-off is reconfirmed; a candidate endpoint is obtained without inferring its ASN from a brand; a genuine RU-side comparison produces a fresh passing attestation; every configured leg produces a fresh healthy authenticated protocol-completion result from the checked-in probe against an operator-controlled target; live-node tests confirm the per-connection adapter's interface binding and fail-closed behavior; and a reviewed governance commit changes `cascade_governance_status` from `implementation-only` to `live-authorized`, replaces the Terraform root's inert adapter with a separately reviewed provider implementation, and deliberately removes the repository-owned false execution conditions. Until then, the normal Terraform router cannot reach the root, the dedicated apply boundary always fails, the rendered units cannot execute, no role task enables or starts them, family profiles cannot enable either role, and Ansible blocks even a host that supplies both an allowlist and a fresh attestation.

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

## Caveats

- The single report motivating this ADR — that two legally distinct entities within one provider family sit on different ASNs with apparently different allowlist treatment — is anecdotal and observation-grade. It is in tension with a separate, larger-sample measurement showing continued allowlist presence for the same provider family. This is why Decision 4 requires recurring re-verification rather than a one-time or brand-based sign-off.
- Moving an entry node's egress off the foreign-datacenter ASN bucket that `PROVIDER-NOTES.md` already documents as triggering TCP-freeze is a trade, not an unqualified improvement: it exchanges one enforcement path for a different, already-anticipated enforcement path on flagged RU cloud ASNs (TLS-fingerprint and rate-based treatment). Both the current context section's org sign-off and this caveat should be read together — the tradeoff is accepted as bounded and temporary, not resolved.
- Split-hop's directional invariants defend a different threat model (dual-role flow correlation) and do not transfer to the cascade. A cascade entry node is inherently client-facing, which would invert split-hop's guarantee if the two were merged — this is the full rationale behind Decision 1's separate role pair, restated here as a standing caveat against any future attempt to unify them.
- The fail-closed classifier behavior on empty or stale data (Decision 3) is a confidentiality and policy invariant, not an availability tradeoff. A passing happy-path test suite must never be treated as sufficient evidence that the invariant holds; the forced-empty test is required, not optional.
- IPv4-only and CGNAT-incompatible are class-level preconditions for the cascade-ingress role — a client-facing entry point on this class of RU hosting cannot rely on IPv6 parity or on being reachable from behind carrier-grade NAT on the entry side. These constraints are noted here as scope-defining preconditions; the operational detail of how they are satisfied is intentionally out of scope for a governance document.

## Cross-references

- `docs/ROLE-TIERING.md` — being amended separately to record the EXCEPTION tier alongside the existing CORE/TACTICAL/RESEARCH guard.
- `docs/PROVIDER-NOTES.md` — being amended separately to add the RU-jurisdiction risk row referenced in Decision 2.
- `docs/CASCADE-ASN-ATTESTATION.md` — companion document specifying the attestation schema, weekly cadence, authorized signer role, dated-report evidence form, and checker referenced in Decision 4 and Phase 3.
- `docs/SPLIT-HOP-TOPOLOGY.md` — prior two-node ADR in this repo; Decisions 1 and 5 explain why the cascade does not extend it and why the two role families may not share a host, while Decision 6 elevates its documented but unenforced per-leg watchdog gap into a cascade registration and promotion blocker.
- `docs/CDN-DECISION.md` — sibling flat-file ADR this document's structure follows.
- `docs/server-integration.md` — deploy-side reconciliation of the opaque-single-endpoint subscription precedent and the client-transparency constraint. Client-visible tier or diagnostic labels remain out of scope.
