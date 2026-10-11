# Prioritized implementation and evolution roadmap

Owner epic: `EPC-1791618453830051`. Plans are complete for review only. All implementation steps are open; no code, private input, deployment or promotion is authorized by this planning request.

## Order and hard dependencies

Priority controls urgency; wave numbers summarize dependency depth, not an instruction to repeat every test or serialize independent inspections. All owned shared-file edits stay in one integration lane. Complete affected cases within each slice, then reuse one exact integrated native/CI run where its named requirements genuinely match.

| Wave | Priority | Task | Observable outcome | Hard blockers | Effort / risk |
|---|---|---|---|---|---|
| 0 | high | [`SCT-1791617687019287`](../transport-input-semantics/proposal.md) | Reject incoherent transport inputs before runtime mutation | None | M / high |
| 1 | critical | [`SEC-1791617841911853`](../resolved-destination-boundary/proposal.md) | Enforce resolved destination isolation for P0 P1 and Hysteria2 | `SCT-1791617687019287` | M-L / high |
| 1 | high | [`ANS-1791617913525586`](../runtime-acceptance-transaction/proposal.md) | Commit transport runtimes only after complete configuration and readiness acceptance | None | L / high |
| 1 | high | [`SCR-1791618039091425`](../awg-device-binding/proposal.md) | Deliver authoritative AmneziaWG device enrollment and client bindings | `SCT-1791617687019287` | M-L / high |
| 1 | high | [`XRY-1791617955392712`](../xhttp-endpoint-contract/proposal.md) | Align XHTTP endpoint paths forwarded attribution and served origins | `SCT-1791617687019287` | M / high |
| 1 | medium | [`SCR-1791617975137354`](../reality-target-validation/proposal.md) | Make REALITY target validation bounded standards-correct and truthful | None | M / high |
| 2 | high | [`ANS-1791618048083304`](../awg-forwarding-dualstack/proposal.md) | Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU | `SCR-1791618039091425` | L / high |
| 2 | high | [`SCR-1791618188806822`](../client-consumed-payload-identity/proposal.md) | Detect client payload drift from every consumed private input | `SCR-1791618039091425`, `XRY-1791617955392712` | M / high |
| 3 | high | [`MON-1791618056169855`](../topology-authenticated-probes/proposal.md) | Deliver topology-aware authenticated transport health and secure smoke probes | `SCR-1791618039091425`, `ANS-1791618048083304`, `XRY-1791617955392712`, `SCT-1791617687019287` | M-L / high |
| 4 | high | [`TST-1791618356595983`](../native-four-protocol-acceptance/proposal.md) | Deliver isolated native acceptance for every baseline transport | `SEC-1791617841911853`, `ANS-1791617913525586`, `SCR-1791618039091425`, `ANS-1791618048083304`, `XRY-1791617955392712`, `MON-1791618056169855`, `SCT-1791617687019287`, `SCR-1791617975137354` | L / high |
| 5 | medium | [`SCR-1791618064422507`](../hysteria-stable-upgrade/proposal.md) | Upgrade Hysteria with validated congestion and UDP resource profiles | `SEC-1791617841911853`, `ANS-1791617913525586`, `MON-1791618056169855`, `TST-1791618356595983` | M-L / high |
| 5 | medium | [`SCR-1791618073850409`](../awg-source-upgrade/proposal.md) | Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings | `SCR-1791618039091425`, `ANS-1791617913525586`, `TST-1791618356595983` | L / high |
| 5 | medium | [`TST-1791618376497512`](../stable-client-parser-upgrade/proposal.md) | Upgrade verified recipient parsers to the current stable client line | `TST-1791618356595983`, `SCT-1791617687019287`, `XRY-1791617955392712`, `SCR-1791618039091425` | M / high |
| 5 | medium | [`XRY-1791617991738391`](../xhttp-alternate-and-tuning/proposal.md) | Deliver selectable alternate XHTTP endpoints and measured typed tuning | `XRY-1791617955392712`, `ANS-1791617913525586`, `SEC-1791617841911853`, `TST-1791618356595983` | L / high |
| 6 | medium | [`ANS-1791618083683925`](../hysteria-ech-profiles/proposal.md) | Deliver coordinated Hysteria ECH server and recipient profiles | `SCR-1791618064422507`, `TST-1791618376497512`, `ANS-1791617913525586` | L / high |

## Candidate release snapshot

The release/channel lookup was refreshed on 2026-10-10. These are source-planning candidates, not observed installed fleet versions. Refresh release/channel, publication time, immutable source/assets, architecture hashes, relevant advisories and exact parser/client compatibility at implementation and again before any promotion. Repository documents retain the selected facts and internal contracts; no external knowledge-store citation is required for execution.

| Runtime | Current repository baseline | Candidate / eligibility | Owned change |
|---|---|---|---|
| Xray | v26.3.27 | Stable Latest remains v26.3.27; v26.9.30 is prerelease and cannot replace the production baseline. No redundant bump task. | Existing release-line and PQ adoption guards; runtime transaction and native acceptance precede a future actual stable update. |
| Hysteria | v2.9.0 | Stable app/v2.13.0, published 2026-10-05; exact hashes and migration details require execution-time review. | `SCR-1791618064422507` |
| AWG Go / tools | v0.2.12 / v1.0.20241018 | Candidate source tags v3.1.20260828 / v3.1.20260812. Go tag resolves to b5928efb6ca19f0153958460c3d141f04abc5c2e; no Go release objects means stable-channel eligibility cannot be inferred from a Latest badge. | `SCR-1791618073850409` |
| sing-box parser | 1.13.16 | Stable v1.14.3, published 2026-10-09T05:35:00Z; production redistribution waits at least 48-hour stable publication eligibility. Source compatibility can be tested independently. | `TST-1791618376497512` |

## Feature integration decisions

| Capability | Integration owner / readiness | Acceptance and boundaries |
|---|---|---|
| Alternate direct XHTTP recipient delivery and typed mode/XMUX profiles | `XRY-1791617991738391` after endpoint contract, isolation, transaction and old-version native baseline. | Exact emitted artifact and actual supported client selection, primary loss/reconnect and alternate TLS identity; comparative sustained upload/download/idle/loss evidence and authenticated rollback. No arbitrary extra JSON, CDN default or automatic fingerprint churn. |
| Hysteria congestion and UDP buffer controls | `SCR-1791618064422507` owns exact-version typed opt-in settings; baseline owns kernel controls. | Measure sustained throughput, socket drops, CPU/memory, reconnects and competing-client fairness. Keep server/client bandwidth semantics distinct from host TCP BBR. No blind increase of QUIC windows or new daemon privilege. |
| Hysteria ECH profiles | `ANS-1791618083683925` after stable server/parser and complete runtime authority. | Supported real recipient negotiates ECH while retaining certificate verification; private key/public config separation, rejected clients, rotation, removal and rollback. Unsupported-client refusal alone leaves the feature unfinished; bare-QUIC cohorts only where evidence justifies benefit. |
| AWG MTU and real IPv4/IPv6 delivery | `ANS-1791618048083304` after authoritative binding. | One typed MTU/address contract across role, registry, bundle, .conf, liveness and consuming client; both-family DNS and TCP/UDP, constrained path, revocation/no-leak and named physical baseline procedure. Never remove IPv6 capture merely to hide failed v6 delivery. |
| AWG I1-I5 and version-specific timing/content padding | Conditional next design after `SCR-1791618073850409`; not a hidden part of baseline upgrade. | Require exact source/client semantics, typed schema/emitter/liveness parity, fingerprint goldens if affected, qualified consumer task and positive packet/data tests. Existing advertised/unsupported fields must be reconciled together. |
| REALITY maxTimeDiff and optional fallback limits | Conditional follow-on after `SEC-1791617841911853` and `SCR-1791617975137354`; no settings enabled here. | A separate typed exact-runtime/client contract must measure clock tolerance, failure, public target appearance and resource behavior. Fallback limiting can itself fingerprint traffic; leave default unchanged until reproducible evidence justifies it. |
| VLESS PQE over REALITY | HOLD under docs/PQ-REALITY-ADOPTION.md. | Real supported client contract, stable server eligibility, coordinated private authority/config, staged traffic and authenticated rollback are mandatory. uTLS X25519MLKEM768 is not VLESS PQE. No guard-only relaxation or manual third-party client can deliver the supported capability. |
| AWG nonzero S3/S4, header protection, RandomTrailers or DisableCookies | HOLD outside the candidate wire-preserving update. | Physical evidence must establish the separately verified arm64 floor before nonzero padding; header protection conflicts with today's zero floor. Unresolved RandomTrailers packet loss and cookie-DoS weakening prohibit default adoption. A tag or issue transition is not physical proof. |

## Ownership and acceptance gates

- Baseline old-version native tests precede candidate upgrades; integration tests the already-supported alternate server through a canonical endpoint-derived real client, while delivered alternate selection belongs to the later feature.
- Exact native Linux/root/systemd/TUN proof, physical arm64 proof, candidate staging soak and production rollout are separate. Missing platform capability is a failed prerequisite, never a skipped success.
- Source-fixed A03/A07/A08/A09/A12/A14 keep their existing review records and limitations. No dropped external acceptance epic is revived.
- Shared schema/profile/listener helpers, Make, CI selection, snapshots and root docs have one integration owner. Future workers own disjoint modules and preserve concurrent edits.
- Published RIPDPI bundle changes require an actual qualified consumer task and `make task-federation PEER_ROOT=<resolved-checkout>` before cross-repository completion. No missing peer ID is fabricated; resolve the consumer ownership before implementing that boundary.
- No new production dependency is installed by planning. A required new dependency must be justified and authorized before future implementation.
- The separate vpnd Python migration is not a blocker; its future callers must consume these canonical contracts when integrated.
- Local/CI source completion does not imply deployment. Upgrade feature tasks retain their named client/staging requirements. Production redistribution and promotion require current authority, exact targets, reviewed private inputs, stable eligibility and successful authenticated rollback.
