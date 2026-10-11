## Context

The P2 extension starts from the published P1 PR revision. The current schema-2
observability topology supersedes the audit's older dedicated sender design;
retained dead-man source is maintained without activating its operator path.
Every audit ID is revalidated against current code before implementation.

## Goals / Non-Goals

- Goal: repair all 32 confirmed P2 paths or prove their current-source correction.
- Goal: investigate six P2 candidates with bounded evidence and repair demonstrated causes.
- Goal: add independently reviewed, positively exercised source to PR 282.
- Non-goal: P3 cleanup, provider/fleet operations, credential issuance, private-state retirement or live acceptance.

## Decisions

- Disabled roles enter reconciliation through the site while each role retains
  exact unit/interface/file ownership. Stop owned runtime before removing it;
  protect retained queues, historical WAL, authority recovery and unrelated state.
- Internal update/jail policy reconciles both boolean states. Dynamic nftables
  membership is carried through complete firewall replacement with bounded expiry
  and real errors; no catch-all success marker is permitted.
- Nginx publication uses one reusable complete-candidate and compensation
  interface across co-resident web consumers. The isolated collector keeps its
  dedicated namespace and uses the same transaction guarantees without acquiring
  the VPN nginx tree. Geodata validates both inputs before paired publication.
- SSH identity changes use the existing recoverable authority transaction;
  role-specific forced commands and forwarding restrictions remain enforced.
- Native parser/runtime behavior determines transport configuration. Correct
  unsupported contracts and all callers instead of compatibility branches or
  refusal-only capability claims. Stable pin and protocol-aware listener rules
  remain shared across runtime, schema and provider-contract consumers.
- Read-only probes execute in check mode. Candidate writes, publication,
  readiness and services remain predictive and cannot depend on fake files.
- Policy tailing returns idle ticks, publishes on an independent cadence and
  distinguishes missing/unreadable input or enforcement failures. Expire inactive
  keys and enforce a finite cardinality cap without discarding active-window bans.
- Metrics and watchdog budgets use descriptor-checked exclusive temporary
  files, fsync and atomic replacement. Listener diagnostics derive from the
  same effective REALITY probe manifest as authenticated completion.
- Retained authority rollback covers the complete mutable file/service set;
  unchanged generation convergence preserves the distinct previous generation.
- Evidence validation checks element scalar types before set/hash operations
  and publishes bounded malformed status rather than preserving old health.

## Contracts and ownership

- Host/web worker owns baseline, real-vps-awg-nat restricted SSH integration,
  tailnet-management, firewall, package_updates, intrusion_prevention,
  nginx-xhttp, cdn-front, geodata, subscription-host and direct tests/role notes.
  This covers F11-F24 and bounded I05/I06. It owns the shared nginx transaction
  interface; collector integration requests are serialized with the primary.
- Transport worker owns hysteria-realm, amneziawg, naive, warp-outbound,
  probe-matrix-target and directly involved measurement roles, split-hop
  ingress/egress, dns-morph-bridge, xray-runtime mode identity and direct tests/notes.
  This covers F25-F31 and bounded I01-I04.
- Primary owns observability_agent/control_plane/deadman, policy-ratelimit,
  watchdog, remaining role disable reconciliation and direct tests/notes. This
  covers F32-F42 and current-contract verification.
- Primary serializes all shared lanes: site dispatch and ansible notes,
  group_vars, listener/profile contracts, schemas/examples, shared scripts,
  topology source, snapshots, CI, task/spec files and PR publication.
- Workers preserve concurrent and P1 edits, never stage/commit or refresh
  snapshots, and request shared-lane updates before writing them.
- Terraform changes are limited to source contract call sites only if a proven
  listener correction requires them; no provider or state access is involved.
  Cloud-init and vpnd remain outside scope unless a direct published consumer
  requires its contract update.

## Risks / Trade-offs

- Service retirement and firewall/SSH changes affect reachability on deployment;
  exact ownership, successful stops, recovery transactions and idempotent
  transition tests gate source acceptance. No live deployment is part of this PR.
- Complete nginx/authority compensation must preserve other owners' bytes and
  service state. Failed restore retains private recovery state and blocks reuse.
- Finite policy history can reject new source tracking at capacity; make the
  condition visible and preserve already tracked active windows.
- Local synthetic endpoints and command adapters are regressions, not provider,
  fleet, independent client or human-delivery proof. Native parser, socket,
  namespace and real service scenarios are required for their named boundaries.

## Migration Plan

The next separately authorized convergence applies corrected runtime contracts
and owned retirement. Unsupported native schemas or production prereleases
become supported, explicitly documented inputs with every repository caller
updated; old compatibility paths are removed. Retained recovery data is not
silently migrated or deleted. Source rollback uses the reviewed prior revision;
runtime transaction compensation is independently tested. Focused regressions,
native role/check-mode/transition cases, reviewed snapshots, full local gates,
independent review and exact-source PR checks gate the incremental handoff.
