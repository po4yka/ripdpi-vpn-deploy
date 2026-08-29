## Purpose

Runtime concerns that were previously re-implemented per role converge onto single, contract-tested implementations: release installation with rollback support for the six named consumers, one source-build receipt idiom, a uniform sandbox floor for the Ansible-owned units in this change, validate-before-restart with liveness waits on in-scope service roles, single-sourced listener defaults and shape contracts, one validated nftables policy idiom, checker-owned collision defense, activation-safe scaffolds, and asserted mirror restore layout.

## ADDED Requirements

### Requirement: REQ-INSTALL-RELEASE-SHARED — Binary release installation MUST use the shared runtime path

The `xray-runtime`, `hysteria`, `hysteria-realm`, `snell`, `probe-matrix-target` and `dns-morph-bridge` roles MUST use the shared `runtime-release` role and its `runtime_release_*` contract for checksum verification, versioned release directories, a current symlink, and unified arch-slug derivation.

#### Scenario: new transport role onboarding

- **WHEN** a role adopts binary installation from a release artifact
- **THEN** it consumes the shared path and gains rollback-symlink semantics without local reimplementation

### Requirement: REQ-BUILD-RECEIPT-IDIOM — Source builds MUST verify through the shared receipt idiom

Build-from-source tasks MUST record and check build receipts through one implementation rather than per-role idioms or in-file copies.

#### Scenario: amneziawg rebuild decision

- **WHEN** amneziawg converges after an upstream commit bump
- **THEN** the loop-driven descriptor build rebuilds only affected projects and updates receipts once

### Requirement: REQ-UNIT-FLOOR-PARITY — In-scope Ansible service units MUST carry the sandbox floor

The probe-matrix Xray/MTG templates and the real-vps server-AWG, echo and mode-specific firewall services owned by this change MUST include at least the declared hardening floor. External sentinel and backup/geodata units remain outside this requirement; inline content blocks are prohibited for the in-scope units.

#### Scenario: research-tier listener

- **WHEN** probe-matrix units are rendered
- **THEN** they carry no fewer floor directives than family transports modulo documented exemptions

### Requirement: REQ-LIFECYCLE-GATE — Service config changes MUST validate before restart and verify liveness after

Rendered service configs MUST pass a validator before restart where a validator exists for the format, and handlers MUST confirm post-restart liveness via the established is-active wait pattern.

#### Scenario: malformed naive Caddyfile render

- **WHEN** an operator value breaks Caddyfile syntax
- **THEN** convergence fails at validation instead of restarting into a dead service

### Requirement: REQ-SINGLE-SOURCED-DEFAULTS — Listener port defaults MUST have exactly one declaring location

Port defaults MUST be declared once in group_vars/all.yml; role defaults and the listener manifest MUST reference them without literal duplication.

#### Scenario: changing a transport port default

- **WHEN** a port default changes
- **THEN** manifest, firewall contract consumption, and role templates all follow the single declaration with no lockstep edits

### Requirement: REQ-NFT-POLICY-IDIOM — Scoped nftables tables MUST load via validated policy files

Role-owned nftables tables MUST be applied by loading standalone policy files that pass nft -c validation; embedding shell rules in WireGuard hooks is prohibited.

#### Scenario: split-hop egress NAT application

- **WHEN** the egress leg applies its postrouting policy
- **THEN** rules pass validation before load and hooks carry no inline nft shell

### Requirement: REQ-CHECKER-OWNED-COLLISIONS — Port-collision defense MUST be owned by the global checker

Pairwise collision guarantees between roles MUST be enforced by the global collision checker; redundant hand-written asserts MAY remain only as pointers after coverage proof.

#### Scenario: removing a stale assert

- **WHEN** a per-role collision assert is removed
- **THEN** the checker demonstrably rejects the same colliding configuration

### Requirement: REQ-P0-SHAPE-SINGLE-SOURCE — The P0 packet-shape contract MUST be emitted from one source

Client-facing probe rendering and server-side inbound rendering MUST consume one shared template for flow/finalmask shape decisions.

#### Scenario: adding a shape mode

- **WHEN** a new P0 shape mode is introduced
- **THEN** server config and watchdog probes change together through the shared template

### Requirement: REQ-ACTIVATION-SAFE-SCAFFOLD — Governance-gated scaffolds MUST NOT hijack default routes as rendered

Scaffold configurations that would alter host-wide routing when activated MUST pair default-route AllowedIPs with Table = off plus documented routing intent, or pin narrower selectors.

#### Scenario: activating cascade-ingress as rendered

- **WHEN** an operator activates the ingress leg using the scaffolded configuration
- **THEN** host-originated traffic and SSH replies keep their direct path

### Requirement: REQ-MIRROR-RESTORE-ASSERTED — Mirror restore layout MUST be asserted before serving

The mirror script MUST verify restored payloads land at the layout the delivery service reads and fail loudly otherwise.

#### Scenario: restic snapshot with unexpected nesting

- **WHEN** restore produces payload paths deeper than DEST/sub
- **THEN** the script fails naming the mismatch instead of leaving stale state served silently
