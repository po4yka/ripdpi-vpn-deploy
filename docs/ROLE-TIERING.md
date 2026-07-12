# ADR: Role and doc tiering — CORE / TACTICAL / RESEARCH

Status: Accepted — 2026-06-11
Decision drivers: three independent priority angles, reconciled below.
Implements (this change): the tier tags (`ansible/role-tiers.yml`) and the
two-layer guard. Deprecation/removal of any role is a **recommendation only**.

## Context and problem

The stated purpose is keeping a few non-technical family devices in RU online
with minimal remote intervention. The repo has grown to **29 Ansible roles**
plus research-grade machinery (split-hop dual-role defense, probe-matrix,
idle-cycle measurement, multi-operator). On a single operator the
maintenance and silent-failure surface now scales super-linearly — against a
threat model the docs themselves admit is unconfirmed in production
(`docs/SPLIT-HOP-TOPOLOGY.md` status: "Pilot (2026-05)", and explicitly: "We
do not have direct confirmation that any specific filtering pipeline currently
runs flow-level dual-role scoring at scale").

This ADR classifies every role (and the major docs) into three tiers and adds
a guard so a RESEARCH role can never silently end up in the default
P0+P1+P2 family deploy.

Tier definitions:

- **CORE** — required for the family-VPN baseline (P0+P1+P2). Always-on or
  default-on. If it breaks, the family loses connectivity or recoverability.
- **TACTICAL** — opt-in, situational. Production-safe to enable for a specific
  condition; not default-on for a family node.
- **RESEARCH** — experimental / unconfirmed-in-prod / measurement-only. Must
  never appear enabled in a default family deploy.
- **EXCEPTION** — hosting-jurisdiction exception. Reserved for roles whose risk
  is a *hosting-location / legal-compulsion* category distinct from RESEARCH's
  technique-maturity rationale. Opt-in only via a literal (non-boolean)
  acknowledgment, provisioned from isolated Terraform state, never in any
  default family profile, and gated by an empirical, expiring, fail-closed
  per-ASN attestation. Introduced for the RU-entry cascade ingress/egress role
  pair (implemented as inert, default-off scaffolds). See `RU-CASCADE-DECISION.md` and
  `CASCADE-ASN-ATTESTATION.md`. This is the repo's first hosting-jurisdiction
  exception; do not fold jurisdiction risk into RESEARCH.

## EXCEPTION registration and promotion criteria

### Cascade per-leg watchdog

- **Registration blocker:** `cascade-ingress` / `cascade-egress` may not be registered for the EXCEPTION tier until every configured ingress-to-egress leg has a watchdog producing a fresh healthy end-to-end result. This is a prerequisite to registration, not a capability deferred until promotion.
- **Promotion blocker:** any later promotion remains blocked while the per-leg watchdog is absent, stale, or unhealthy. A previously healthy result does not waive the current signal requirement.
- **Signal class:** the watchdog must complete an authenticated protocol exchange from ingress through the selected egress to a controlled target on the forwarded path, validate the semantic response, and observe its return through that leg. Process/socket/interface presence and local self-dial are non-authoritative. Checks occur every five minutes; one miss is degraded/transient, three consecutive misses across distinct intervals with a healthy ingress-local control classify the far leg as down, and any success resets the streak. Registration accepts only a healthy record no more than ten minutes old; `scripts/cascade-leg-probe.py` produces the redacted record from an authenticated leg completion plus an independent direct control, and `scripts/check-cascade-leg-health.py` enforces its state and freshness. The checked-in units remain literally disabled until a future live-authorization decision.
- **Treatment relative to split-hop:** this intentionally diverges from split-hop's current RESEARCH treatment, where the identical far-leg gap is documented but unenforced. Cascade registration pays an additional jurisdiction and policy cost, so the weaker pilot precedent is not sufficient for EXCEPTION admission.

### Cascade attestation operations

- **Cadence:** candidate-ASN evidence is valid for seven UTC calendar days. The next-recheck date must equal the attestation date plus seven days, and the checker blocks on or after that date without a grace period.
- **Owner and evidence:** only the Cascade Attestation Operator role may sign or re-sign. Each record points to a dated measurement report by opaque identifier and SHA-256; raw probe output, endpoints, provider identity, and ASN/CIDR inventories stay outside the repo.
- **Method unavailable:** loss of the RU-side comparison method, candidate access, report path, or authorized signer is a permanent fail-closed block while unavailable. This residual availability risk is accepted and does not create an override.
- **Family exclusion:** EXCEPTION roles are absent from every `family_profiles` effective-enable set indefinitely. A future promotion or default-profile inclusion requires a separate governance decision; neither a passing attestation nor an exact host allowlist changes family profiles automatically.

## The three angles (argued independently, then reconciled)

| Angle | Optimizes | Core count | Headline |
|---|---|---|---|
| **(a) operator burden** | fewest moving parts that keep the family online; self-healing; recoverability | **7** | Keep an irreducible CORE; push every research prototype and expensive transport variant to TACTICAL/RESEARCH so on-call surface matches what a family VPN needs. |
| **(b) censorship-resistance** | transport diversity + proven defenses vs the TSPU threat model | **11** | Keep every *confirmed* transport path and *proven* defense hot; hold *unconfirmed* machinery at arm's length — an unproven defense that adds a detectable signature is net-negative against an adaptive adversary. |
| **(c) attack surface / silent-failure** | smallest surface that still delivers the baseline | **11** | Demote every extra listener, unverified external dependency, second trusted host, or control whose own failure is invisible. |

The angles converged more than expected: (b) and (c) arrived at the same core
count from opposite motivations — (b) wants the confirmed transports *present*,
(c) wants everything *unconfirmed or extra* gone, and the two sets coincide on
the shipped default. (a) argued the most aggressive shrink. Where they
genuinely disagree is recorded in **Disagreements**, not averaged away.

## Per-role classification

Final tier with each angle's vote. "Contested" = the three did not agree.

| Role | (a) | (b) | (c) | **Final** | Deciding rationale |
|---|---|---|---|---|---|
| baseline | CORE | CORE | CORE | **CORE** | Always-on by contract; sysctl/SSH/time-sync (REALITY breaks on >90 s drift)/forwarding. Without it nothing converges and SSH recovery breaks. |
| firewall | CORE | CORE | CORE | **CORE** | Always-on; nftables default-drop is the sole perimeter. No toggle. |
| xray | CORE | CORE | CORE | **CORE** | P0 VLESS+REALITY+Vision (TCP/443), primary tunnel in every profile. Churn managed by `XRAY-RELEASE-LINE.md` pin+rollback. |
| nginx-xhttp | CORE | CORE | CORE | **CORE** | P1 XHTTP direct (TCP/8443); first fallback when 443 is fingerprinted. No external dependency (CDN-DECISION ADR). |
| hysteria | CORE | CORE | CORE | **CORE** | P2 UDP/QUIC; orthogonal transport when TCP is throttled. Reuses nginx cert. |
| amneziawg | TACTICAL | CORE | CORE | **CORE** *(contested)* | (b)/(c) win: default-on in `all.yml`, declared P2 device-VPN baseline, a 4th transport shape. (a)'s build-tax point is *valid and real* (see burden table — it builds amneziawg-go from source at deploy) but doesn't outweigh baseline status. |
| geodata | TACTICAL | CORE | CORE | **CORE** *(contested)* | (b)/(c) win: default-on; the firewall geo-block set depends on its feed — disabling it silently half-breaks the allowlist. License-tier death risk is real but has named fallbacks. |
| monitoring | TACTICAL | CORE | CORE | **CORE** *(contested)* | (b)/(c) win: default-on; the *collection* layer (node_exporter on loopback, log rotation) is sound. AUDIT-SILENT-FAILURE targets the *alert* layer above it, not collection. A single operator must not fly blind. |
| watchdog | CORE | CORE | CORE | **CORE** | Two-level local supervision prevents permanent process death. Authenticated public-path liveness and rotation are intentionally separate and use the quorum/OTP flow in `PROTOCOL-LIVENESS.md`. |
| backup | CORE | CORE | CORE | **CORE** | restic+age is the only recovery path on burn. Integrity check is missing (AUDIT remediation) but that's a fix, not a demotion. |
| subscription-host | TACTICAL | CORE | CORE | **TACTICAL** *(contested)* | (a) wins: `enable_subscription_host: false` (default-off); ARCHITECTURE lists it "optional"; v1 delivery is `emit-singbox.sh` + scp. (b)/(c)'s "zero-intervention reconfig" is a later hardening aspiration, not the current baseline. |
| policy-ratelimit | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; recently re-scoped to a routing-blackhole abuse limiter that cannot see external probes by design (AUDIT-SILENT-FAILURE + role README). Enable after the nftables-meter remediation. |
| honeypot | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; AUDIT-SILENT-FAILURE found all four alert-chain links broken. Adds listeners (2222/9000/9100) with zero actionable signal until repaired. |
| cdn-front | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; `CDN-DECISION.md` ADR rules CDN out as the RU baseline. Short-term IP-rotation cover only. |
| naive | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; xcaddy from-source build + v147 preamble breakage. Enable only when HTTP/2+Chromium fingerprint is specifically the threat. |
| warp-outbound | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; changes egress ASN (breaks burn-check/ASN-drift). Enable only when the upstream ASN path is burned. |
| reality-self-steal | TACTICAL | TACTICAL | TACTICAL | **TACTICAL** | Default-off; replaces a borrowed cross-ASN REALITY target with an operator-owned loopback TLS/H2 site without adding a public listener. Promotion still requires DNS, certificate, client SNI, and filtered-vantage evidence. |
| split-hop-egress | RESEARCH | RESEARCH | RESEARCH | **RESEARCH** | Pilot/unconfirmed; Node A has no Ansible coverage (manual iptables); doubles the fleet; watchdog has no per-leg probe so B going down is silent. FOCI-2026 classifier is published but unconfirmed as deployed. |
| hysteria-realm | RESEARCH | RESEARCH | RESEARCH | **RESEARCH** | sing-box **alpha** pin ("treat every minor bump as breaking"); P5 fallback; hole-punch failure is silent server-side. No family NAT-traversal need justifies alpha-upstream risk. |
| dns-morph-bridge | RESEARCH | RESEARCH | RESEARCH | **RESEARCH** | No upstream release artifact (self-built binary); P4 fallback; opens public UDP/53 (reflection surface); only works if the client uses the bridge IP as resolver — not true for RU carrier-DNS family devices. |
| snell | RESEARCH | RESEARCH | RESEARCH | **RESEARCH** | sing-box 1.14 prerelease, no independent field evidence, and a measurement matrix that must remain outside automatic selection and rotation. |

**Tally:** CORE 10 · TACTICAL 7 · RESEARCH 4. This matches exactly what the
repo already ships (all 10 CORE roles are default-on/always-on; all 7 TACTICAL
and all 4 RESEARCH are default-off). The tiering therefore *ratifies and
locks* the current default rather than changing behaviour — which is the point
of the guard: keep it that way.

## Per-doc classification (major docs)

| Doc | Tier | Rationale |
|---|---|---|
| ARCHITECTURE.md | CORE | Canonical profile→role/port map; every enable decision starts here. |
| QUICKSTART.md | CORE | Zero-to-working-VPN runbook; primary standup/recovery entry. |
| RUNBOOK-deploy.md | CORE | Production deploy sequence for every standup / re-deploy after burn. |
| RUNBOOK-incident.md | CORE | IP-burned / key-leaked recovery lifeline. |
| RUNBOOK-rollback.md | CORE | Fast recovery when an Xray bump/config breaks transport. |
| RUNBOOK-restore.md | CORE | Restic restore after host loss; pairs with backup. |
| RUNBOOK-rotate.md | CORE | UUID/shortId/peer-key rotation; routine hygiene + post-compromise. |
| SECRETS.md | CORE | SOPS+age discipline; governs the no-secrets-in-git hard rule. |
| AGE-RECOVERY.md | CORE | Shamir age-key recovery — "the whole game"; lose shares = locked out. |
| CDN-DECISION.md | CORE | ADR keeping CDN off the critical path; prevents an accidental fragile default. |
| AUDIT-SILENT-FAILURE.md | CORE | The 8 silently-broken controls; required reading before trusting any signal. |
| XRAY-RELEASE-LINE.md | CORE | Per-release breaking changes; required before any xray pin bump. |
| CLIENT-NOTES.md | CORE | Client version pins / breakage classes; family devices can't self-diagnose. |
| AWG-COHORTS.md | CORE | AWG obfuscation cohorts; wrong H1..H4 is a trainable fingerprint. Elevated because amneziawg is CORE. |
| RUNBOOK-add-fallback.md | TACTICAL | Second-VPS procedure; CORE only once the operator runs >1 node. |
| MULTI-OPERATOR.md | TACTICAL | Per-scope SOPS split; irrelevant to a single operator. |
| SUBSCRIPTION-HOST-SEPARATION.md | TACTICAL | Blast-radius isolation; v1 default is co-location. |
| TRANSPORT-REACHABILITY-MATRIX.md | TACTICAL | Two-vantage diagnostic; used after a regression, not routinely. |
| SPLIT-HOP-TOPOLOGY.md | RESEARCH | Pilot ADR; the adversary capability is unconfirmed at scale. |
| RUNBOOK-split-hop-pilot.md | RESEARCH | Pilot runbook; Node A is manual, no Ansible coverage. |
| PROBE-MATRIX.md | RESEARCH | Authenticated topology-aware DPI measurement; five public target listeners and controlled multi-vantage evidence are not family baseline features. |
| RUNBOOK-idle-cycle-measurement.md | RESEARCH | DPI measurement workflow; its own probe traffic could become a signal. |

(Docs not listed — RELEASE-PLEASE, BRANCH-PROTECTION, CI-REAL-DEPLOY,
PROVIDER-NOTES, TESTING, REGRESSION-BASELINE, RIPDPI-BUNDLE,
ASN-EXPOSURE-DENYLIST, MULTI-COHORT, SUBSCRIPTION-PLANE — are CI/dev-process
or reference docs, orthogonal to the deploy-tier question.)

## Maintenance-burden estimate (fast-moving-upstream coupling)

The super-linear cost concern is concentrated in a handful of roles. Churn is
the recurring operator tax; silent-failure column is what bites unattended.

| Role | Tier | Upstream | Churn | Burden / silent-failure risk |
|---|---|---|---|---|
| xray | CORE | XTLS/Xray-core (pinned v26.3.27; v26.5.3 pre-release) | **high** | Breaking schema changes between minors (echForceQuery removed; flow-mode silent break). Mandatory staging + secrets-schema migration per bump; ~monthly. Unavoidable — it is the baseline. |
| hysteria-realm | RESEARCH | SagerNet/sing-box **alpha** | **high** | Pinned to an alpha; every minor bump is potentially breaking. Hole-punch failure silent server-side. Research-grade upstream with no stable line. |
| snell | RESEARCH | SagerNet/sing-box **alpha** | **high** | Three staged wire/shape variants plus per-device credentials; promotion requires a stable release and repeated filtered-vantage evidence. |
| dns-morph-bridge | RESEARCH | self-built binary (no release artifact) | **high** | Operator must build+host the binary and hand-update `binary_url`/sha256; plus a second daemon (unbound). Stale URL fails closed but the P4 path vanishes with no alert. |
| amneziawg | CORE | amneziawg-go (built from source at deploy) + client apps | **medium** | **Correction to the angle-analysis:** the role runs `make`/`make install` (installs `make`), i.e. it compiles amneziawg-go on the VPS at deploy — a real first-deploy cost and a Go-toolchain dependency, not a pre-built download. Ongoing tax is server↔client version-pin coordination (AWG 2.0 skew silently falls back to vanilla WG). |
| geodata | CORE | MaxMind GeoLite2 license-free tier | **medium** | "License-free tier dies on a schedule" (role CLAUDE.md). Weekly job fails silently on key revocation → stale GeoIP; named fallbacks (IPinfo/DB-IP) are manual. |
| naive | TACTICAL | klzgrad/naiveproxy (xcaddy from-source) | **medium** | Go toolchain on host; v147 preamble already burned one cycle; major versions need coordinated client+server push. |
| warp-outbound | TACTICAL | Cloudflare WARP CLI (apt) | **medium** | apt-key rotation history; `warp-cli register` may need manual first-boot fix; IPv6 conflicts on some kernels. |
| cdn-front | TACTICAL | Cloudflare IP ranges (daily) | **medium** | Origin-firewall sets rebuilt daily; CDN policy/PoP-TSPU change triggers a CDN-DECISION re-evaluation. |
| hysteria | CORE | apernet/hysteria2 | **medium** | Pinned+sha256 (xray discipline). Main risk: cert renewal shared with nginx — one failure silently breaks P1 and P2. |
| split-hop-egress | RESEARCH | plain WireGuard kernel (stable) | **low** | Upstream is stable; the burden is *operational*: Node A manual (no Ansible), no per-leg health probe (B down = silent on A), doubles VPS+secrets surface. |

Reading: three of the four **high**-churn roles are RESEARCH or research-grade
upstreams (hysteria-realm, dns-morph-bridge) — the guard keeps exactly these
out of the family default. The one unavoidable high-churn CORE role (xray) is
the cost of having a VPN at all and is already disciplined by the release-line
tracker.

## Disagreements (surfaced, not papered over)

1. **amneziawg — CORE vs TACTICAL.** (a) TACTICAL: recurring build/version-skew
   tax. (b)/(c) CORE: 4th transport shape, default-on, declared baseline.
   **Resolved CORE** on repo evidence (default-on + ARCHITECTURE baseline). But
   (a)'s burden point is *upheld and recorded* — and (a)'s premise that the
   build is cheap was itself wrong in the *other* direction: it compiles from
   source at deploy. The tier is CORE; the burden is real and tracked.

2. **geodata — CORE vs TACTICAL.** (a) sees a license-tier liability to keep
   off by default; (b)/(c) note the firewall geo-block silently half-fails
   without it. **Resolved CORE** because it is default-on and load-bearing for
   the perimeter; the license risk is a watch-item, not a demotion.

3. **monitoring — CORE vs TACTICAL.** (a) points at AUDIT-SILENT-FAILURE (the
   alert pipeline is broken). (b)/(c) separate the *collection* layer (sound,
   local-only) from the *alert* layer (broken). **Resolved CORE** — flying
   blind is worse than imperfect alerting; the broken alert path is a fix, not
   a reason to drop log collection.

4. **subscription-host — CORE vs TACTICAL.** (b)/(c) value zero-intervention
   config delivery to non-technical users; (a) notes v1 ships scp/QR and the
   toggle is default-off. **Resolved TACTICAL** — the auto-delivery case is a
   real future need but not the *current* baseline; forcing it into CORE would
   contradict the shipped default. This is the disagreement most likely to flip
   as the family grows; revisit when manual config push stops scaling.

Unresolved tension worth stating plainly: angles (b) and (c) would both accept
a *larger* CORE than (a) is comfortable maintaining. The ADR sides with the
repo's shipped default (which (a) also accepts) — but the operator should read
this as "CORE is already at the upper bound of what one person can keep
healthy; do not grow it." Every future role starts at TACTICAL or RESEARCH and
earns promotion with evidence.

## Ranked recommendation

1. **Fix the CORE before adding anything.** The 10 CORE roles are the family's
   lifeline, and `docs/AUDIT-SILENT-FAILURE.md` found several of them silently
   degraded (watchdog transport-liveness, backup integrity, check-certs EC
   modulus, burn-check freeze). A baseline with no real self-healing signal and
   no certifiable backup is the top priority — ahead of any new capability.
2. **Keep TACTICAL roles default-off and fix-before-enable.** policy-ratelimit
   and honeypot must have their AUDIT-SILENT-FAILURE remediations landed before
   they are turned on anywhere; the rest (cdn-front, naive, warp-outbound,
   subscription-host) enable only on their specific trigger condition.
3. **Quarantine RESEARCH.** split-hop-egress, hysteria-realm, dns-morph-bridge, and snell
   stay out of every family profile (now enforced — see Guard). Promote only
   after: confirmed pilot data (split-hop), an upstream *stable* line
   (hysteria-realm), a published+pinned artifact (dns-morph-bridge), and a stable release plus repeated filtered-vantage evidence (snell).
4. **Recommendation (not done here): consider deprecating** the research roles
   and their docs out of the main tree (an `experimental/` area or a separate
   branch) if the pilots do not produce confirming data within a release cycle.
   This change does **not** remove them — it only tags and guards them.

## Guard (implemented this change)

A RESEARCH or EXCEPTION role can never silently reach a family deploy, enforced in two
layers over one source of truth.

- **Source of truth:** `ansible/role-tiers.yml` — `tiers` (every role → core / tactical / research / exception), `toggle_role_map` (each `enable_*` → role), `family_profiles` (the profiles that must stay free of both gated tiers), and the repository-owned cascade lifecycle status.
- **Static layer (CI / pre-commit):** `scripts/check-deploy-profile.py` fails if any RESEARCH or EXCEPTION role is enabled in a family profile, or anywhere it lacks its exact matching allowlist entry. Wired into `make ci-fast` and `.pre-commit-config.yaml`; covered by `tests/unit/test_deploy_profile_guard.py`.
- **Deploy-time layer:** pre-task assertions in `ansible/playbooks/site.yml` enforce the matching exact-name allowlist. Cascade additionally requires a fresh attestation and a repository-owned `live-authorized` governance state; inventory cannot supply or override that state.

Current family profile files are `all.yml`, `vpn-p0-minimal.yml`, `vpn-family-standard.yml`, `vpn-device-full.yml`, and the legacy aliases `vpn-p0.yml`, `vpn-p1p2.yml`, `vpn-fullstack.yml`. `vpn-lab.yml` is intentionally outside `family_profiles`; it may opt into research only by listing exact role names in `allow_research_roles`.

Override semantics (deliberate): `allow_research_roles` is a **list of role
names**, not a boolean — allowlisting one research role does not implicitly
permit the others. A family profile may **not** set it at all (the lint
forbids the override in `family_profiles`); only a lab/pilot host's inventory
may, where it is visible in the git diff.

Edge cases the guard handles (raised during reconciliation):

- **Inheritance from `all.yml`.** The lint resolves the *effective* enable set
  (all.yml merged with each profile, profile wins), so a research role turned
  on in `all.yml` and not overridden to false in a profile is still caught.
- **TACTICAL is not gated.** Only `research` roles are blocked; enabling a
  tactical role is the operator's call.
- **host_vars and other group_vars.** The lint scans all of `group_vars/` and
  `host_vars/`, not just the named family profiles, so a stray
  `enable_split_hop_egress: true` on a host without the allowlist fails.
- **Manifest drift / unknown roles.** The lint fails closed if a role on disk
  has no tier, a tier value is invalid, a toggle maps to an unknown role, or a
  profile uses an `enable_*` toggle absent from `toggle_role_map` (a new role
  added without a tier assignment cannot slip through).

What is intentionally **not** done in this change: no role is removed,
deprecated, disabled, or moved. The behaviour of the shipped default is
unchanged; the guard simply makes the current (already-correct) default
impossible to break silently.
