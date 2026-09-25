## Purpose

Establish restricted ordinary OpenSSH over Tailnet on a fresh node before
dual-path deployment, without sacrificing public recovery or rollback safety.

## ADDED Requirements

### Requirement: REQ-TFB-INPUT — Bootstrap is an explicit one-node operation

The implementation MUST provide a canonical Make bootstrap command selecting
one exact inventory alias through literal private inputs. It MUST validate
clean source identity, strict host-key pins, effective SSH port, exact approved
Tailnet controller sources, and recovery readiness before host mutation.
Unknown state, unsafe input ownership, source drift, ambiguous selection, or
an unpinned public connection MUST refuse. Provider credentials and enrollment
keys MUST NOT appear in Make arguments, inventory, SOPS, logs, or receipts.

#### Scenario: A fresh public-only node is selected

- **WHEN** one approved node has completed cloud-init and has a pinned public SSH path
- **THEN** bootstrap can begin without a fabricated management address or a VPN promotion receipt.

#### Scenario: Input validation fails

- **WHEN** any required pin, ownership, selection, source, or recovery check fails
- **THEN** no package, firewall, enrollment, provider, or ACL mutation occurs.

### Requirement: REQ-TFB-BOUNDARY — Bootstrap changes only the access foundation

Bootstrap MUST install the pinned Tailnet and recovery components through
Ansible and provision only the minimal firewall foundation needed for exact
approved `tailscale0` SSH sources. All other SSH on that interface MUST be
denied before public-source rules. Existing public SSH, host keys, sshd policy,
resolver bytes and ownership, and default routes MUST be preserved. Tailscale
SSH, DNS management, route acceptance/advertisement, exit-node use, and
automatic netfilter changes MUST remain disabled. Provider and ACL policy
changes MUST remain outside bootstrap.

#### Scenario: Fresh enrollment succeeds locally

- **WHEN** the guest reports a running Tailnet identity
- **THEN** both canonical Tailnet address families are observed, required policy snapshots are unchanged, and the transaction remains unconfirmed.

#### Scenario: Existing state has unrelated ownership

- **WHEN** another firewall manager, unknown ruleset, pending transaction, or conflicting Tailnet identity is found
- **THEN** bootstrap refuses without replacing, flushing, disabling, or logging out that state.

#### Scenario: Daemon startup leaves only empty baseline tables

- **WHEN** the unmanaged baseline contains exactly ip/filter, ip/nat, ip6/filter and ip6/nat, without chains, rules, sets, maps or extra attributes
- **THEN** bootstrap MUST snapshot and preserve those tables through apply and rollback; partial, duplicated or extended table sets MUST NOT qualify for this exception.

### Requirement: REQ-TFB-RECOVERY — Enrollment and firewall publication share durable recovery

Before the first access-changing write, the implementation MUST durably arm
one generation-, target-, nonce-, snapshot-, and deadline-bound transaction
covering enrollment and firewall state. A verified persistent timer and boot
recovery sequence MUST restore the original firewall files, service activation
state, and effective rules, and log out only the identity created by that
transaction after failure, expiry, controller loss, or reboot. Ambiguous state
MUST retain evidence and refuse. Confirmed recovery MUST never log out a
committed identity. Installed inert packages may remain but MUST confer no
additional network access after rollback. Boot recovery MUST restore firewall
policy before nftables and network-pre.target without depending on tailscaled;
it MUST then revoke the owned enrollment after tailscaled and before
`ssh.service` can serve/authenticate ordinary SSH. Early recovery MUST gate
`ssh.socket`; late recovery MUST NOT gate the socket. A listening socket
after early recovery MUST NOT permit sshd activation before late recovery
succeeds. Both phases MUST share one durable rollback decision and lock. Once
rollback begins, confirmation MUST refuse. Early-worker failure MUST block
network/firewall startup rather than permit an unconfirmed policy to load.

#### Scenario: Reboot interrupts enrollment

- **WHEN** an armed transaction is found by the early boot worker
- **THEN** firewall recovery runs without tailscaled, persists its progress, and the late worker completes logout before SSH without a dependency cycle.

#### Scenario: Recovery is interrupted between phases

- **WHEN** firewall restoration or its durable progress write is interrupted
- **THEN** recovery safely retries under the same transaction and no confirmation can reverse the rollback decision.

#### Scenario: Controller disappears after enrollment

- **WHEN** no durable external confirmation exists at expiry or boot
- **THEN** autonomous recovery restores the prior access policy without controller connectivity.

#### Scenario: Confirmation durability is ambiguous

- **WHEN** a write or fsync fails around the confirmed record
- **THEN** the command reports failure, preserves diagnosable state, and cannot claim successful rollback or success without verification.

### Requirement: REQ-TFB-PROOF — Confirmation requires fresh independent SSH connections

The controller MUST obtain the node's real Tailnet addresses through pinned
public SSH, then create fresh public and Tailnet SSH sessions with proxies,
agent, connection sharing, and inherited SSH configuration disabled. Both
connections MUST verify the same pre-enrollment host key and observed target
and socket identities. Both MUST prove ordinary SSH command and SFTP access.
Guest postconditions MUST be rechecked before durable confirmation. Replayed,
foreign, stale, or expired confirmations MUST refuse.

#### Scenario: Tailnet control plane works but SSH does not

- **WHEN** enrollment is running but either fresh SSH path fails
- **THEN** bootstrap does not confirm and recovery restores the previous access state.

#### Scenario: Both paths are proven

- **WHEN** fresh target-bound public and Tailnet proofs pass within the transaction deadline
- **THEN** a private target-bound handoff records observed socket contexts and a redacted result reports bootstrap success, not VPN acceptance.

### Requirement: REQ-TFB-DEPLOY — Ordinary deployment remains dual-path and verification-only

Ordinary deploy MUST continue rejecting missing or identical public and
management paths and MUST retain the exact-node protocol promotion gate.
First enrollment MUST move to bootstrap; deploy MUST reject enrollment keys
and verify existing Tailnet state without invoking login. All existing callers
and tests MUST migrate; no legacy credential-forwarding fallback is permitted.
An already bootstrapped node may be verified idempotently without consuming a
new key, mutating its identity, or replacing mismatched operator inputs.

#### Scenario: Deploy receives a new enrollment capability

- **WHEN** an enrollment key is supplied to ordinary deploy
- **THEN** it refuses before SSH or Ansible rather than silently retaining the old enrollment path.

#### Scenario: Bootstrap succeeds but protocol proof fails

- **WHEN** ordinary deployment cannot prove required VPN profiles
- **THEN** deployment fails under its existing rollback contract and bootstrap evidence cannot satisfy that gate.

### Requirement: REQ-TFB-ACCEPTANCE — Positive runtime behavior is required for delivery

The implementation MUST pass regression and failure-path tests, native Linux
firewall/systemd recovery checks, applicable local gates, exact-revision hosted
CI, and authorized disposable staging with fresh dual-path SSH, reboot and
controller-loss recovery. Staging MUST then exercise normal deployment and
real protocol proof followed by UUID-bound deletion and provider absence.
Fixtures, refusal-only behavior, and source checks MUST NOT close this feature.

#### Scenario: Local tests pass without staging

- **WHEN** only unit or container evidence exists
- **THEN** the feature remains incomplete for staging/live acceptance.
