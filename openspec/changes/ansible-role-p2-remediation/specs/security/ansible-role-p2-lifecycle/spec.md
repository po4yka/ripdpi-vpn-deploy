## Purpose

Guarantee complete, recoverable runtime ownership and truthful evidence for
the audited P2 Ansible role configuration and lifecycle paths.

## ADDED Requirements

### Requirement: REQ-P2-ACCESS — Complete delivery and management prerequisites

Enabled services MUST receive their own complete TLS and restricted SSH
authority before activation. Read-only inspection MUST execute in check mode
without enrollment or publication writes; mandatory sysctl failures MUST fail.

#### Scenario: Clean delivery host and restricted evidence account

- **WHEN** subscription-only delivery or the forced-command evidence identity is selected
- **THEN** HTTPS starts without a transport role, and SSH admits only the intended restricted identity while shell and forwarding remain denied

#### Scenario: Predictive inspection and mixed sysctl failure

- **WHEN** an installed Tailnet is inspected with check mode or mandatory sysctl application fails alongside optional congestion control
- **THEN** inspection returns actual read-only state without enrollment writes and the mandatory failure is not hidden

### Requirement: REQ-P2-ENFORCEMENT — Correct and durable dynamic enforcement

The complete effective proxy transport set MUST drive egress allowance.
Disabled update/jail policy MUST converge disabled runtime. Unexpected ban
failures MUST remain errors, and firewall replacement MUST preserve bounded
IPv4/IPv6 ban membership and remaining expiry.

#### Scenario: Proxy egress and policy transitions

- **WHEN** XHTTP-only or Snell-only strict egress is selected, or updates/jails transition enabled to disabled
- **THEN** intended client destinations remain reachable, non-proxy default drop remains enforced, and repeated disable is idempotent

#### Scenario: Existing bans survive a firewall change

- **WHEN** an unrelated firewall setting changes with active dynamic bans
- **THEN** enforcement and remaining expiry survive, and a failed nft operation cannot be reported as success

### Requirement: REQ-P2-PUBLICATION — Complete candidate and rollback authority

Nginx and geodata publication MUST validate complete candidate inputs before
changing live authority and MUST compensate ordinary failed activation with
exact prior files, links, permissions and relevant service state. CDN trust
MUST remain confined to its vhost; transport logs MUST respect privacy.

#### Scenario: Invalid candidate and failed activation

- **WHEN** a key/config, second geodata download, checksum or activation fails
- **THEN** the previous complete authority remains restartable and no mixed generation or invalid live tree survives

#### Scenario: Vhost attribution and integration fixtures

- **WHEN** CDN, direct and subscription requests carry the same forwarded header, or fallback XHTTP traffic is served
- **THEN** only the CDN vhost applies its proxy trust and transport/bearer material does not leak into ordinary logs; valid AOP fixtures exercise actual authentication

### Requirement: REQ-P2-TRANSPORT — Supported exact runtime and listener contracts

Transport configuration MUST pass the exact pinned native parser and provide
positive forwarding behavior. Stable version policy and complete TCP/UDP
listener contracts MUST agree across every repository consumer. Runtime and
unit changes MUST activate and removed owned instances MUST retire safely.

#### Scenario: Exact runtime and effective instance change

- **WHEN** Realm/WARP configuration is selected or AWG/probe units receive a pin/unit-only update or instance removal
- **THEN** the supported pinned runtime forwards actual test traffic, production rejects prereleases, running processes adopt changes, and only removed owned interfaces/private config retire

#### Scenario: UDP and investigated packet paths

- **WHEN** HTTP/3 or investigated split-hop/DNS/source-build boundaries are exercised
- **THEN** protocol-aware listener declarations are complete and any demonstrated bypass, recursion or release-identity defect is corrected with positive and failure regressions

### Requirement: REQ-P2-LIFECYCLE — Disabled intent reconciles owned absence

Site dispatch MUST enter ownership-aware reconciliation for disabled roles.
It MUST stop owned units before retiring their runtime/configuration and MUST
preserve unrelated services, interfaces and explicit recovery retention.
Manifests MUST describe reconciled runtime rather than falsely accepting intent.

#### Scenario: Full profile becomes minimal

- **WHEN** a previously enabled role or protocol is disabled through the site profile
- **THEN** owned active surfaces converge absence, repeated reconciliation is idempotent, and retained queues/recovery material remain private under their explicit contract

### Requirement: REQ-P2-OBSERVABILITY — Predictive execution and complete authority

Observability read-only probes MUST run in check mode and mutation/activation
MUST remain predictive. Pin changes MUST restart the exact runtime. Candidate
failure MUST restore complete prior authority and unchanged convergence MUST
preserve the prior distinct rollback generation. Retired topology MUST stay retired.

#### Scenario: Fresh and existing predictive namespaces

- **WHEN** supported enabled role task graphs run in check mode
- **THEN** they consume valid probe results without fabricated artifacts, create no authority, and start no services

#### Scenario: Pin, rollback and repeated generation

- **WHEN** a binary pin changes, candidate authority fails, or A becomes B followed by unchanged B
- **THEN** the selected process adopts the pin, prior complete readiness is restored on failure, and previous remains A after unchanged B

### Requirement: REQ-P2-EVIDENCE — Bounded truthful detector and watchdog state

Policy heartbeat MUST be independent of input traffic, with bounded expiring
source cardinality and separately visible input/enforcement failures. Shared
metrics and watchdog budget state MUST use exclusive atomic durable publication.
Every listener-dependent watchdog check MUST use the effective manifest.
Malformed external evidence MUST replace last-good health with redacted error state.

#### Scenario: Idle detector and adversarial publication

- **WHEN** traffic is absent, many sources expire, or an attacker precreates a temporary symlink
- **THEN** healthy heartbeat stays fresh, retained keys remain bounded, and another producer's bytes stay intact

#### Scenario: Cohorts, interrupted budgets and malformed evidence

- **WHEN** healthy cohorts exclude the base port, publication fails, or evidence contains nested invalid values
- **THEN** no false restart occurs, prior complete recovery budgets remain intact, and fresh healthy metrics cannot survive malformed input

### Requirement: REQ-P2-ACCEPTANCE — Verified P2 coverage and preserved P1 guarantees

Every confirmed P2 audit ID MUST have a current-source repair or demonstrated
prior correction. P2 investigation candidates MUST have bounded evidence and
explicit qualification. The existing P1 guarantees MUST remain covered by
regressions, independent review, required local gates and exact-source PR checks.

#### Scenario: Incremental source PR completion

- **WHEN** the P2 source revision is added to PR 282
- **THEN** focused positive/failure, check-mode, lifecycle, snapshot and hosted checks identify their exact source and do not claim fleet, client or human acceptance
