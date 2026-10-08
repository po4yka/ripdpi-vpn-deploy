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

#### Scenario: Readiness overlaps periodic SSH recovery

- **WHEN** the verified periodic SSH recovery worker is executing
- **THEN** readiness waits within its existing 30-second budget for that same invocation's completed success, without starting or restarting the service.
- **AND** failure, contention, timeout, or a change of invocation, generation, boot, or boot-recovery execution refuses; cached success cannot replace the current execution.

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

#### Scenario: Daemon readiness precedes backend initialization

- **WHEN** late recovery sees `NoState` or `Starting` before owned logout or immediately after it
- **THEN** it polls only those states within one fixed 30-second monotonic budget shared across both checks, bounds each query by the remaining time, and rejects a reply arriving at or after the deadline.
- **AND** malformed, unknown and authorization states refuse immediately; timeout preserves the durable transaction, foreign identity is never logged out, and normal enrollment/status callers remain strict.

#### Scenario: Recovery is interrupted between phases

- **WHEN** firewall restoration or its durable progress write is interrupted
- **THEN** recovery safely retries under the same transaction and no confirmation can reverse the rollback decision.

#### Scenario: OpenSSH has not created its volatile runtime directory

- **WHEN** boot recovery runs before `ssh.service` and `/run/sshd` is absent
- **THEN** effective-policy syntax validation and full-policy comparison succeed without creating that service-owned directory; invalid configuration and policy drift still refuse.

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
Deploy mode MUST require a private exact-alias mapping to fresh absent SSH
baseline failure-receipt paths before readiness or SSH. Each path MUST be
absolute, distinct, and beneath a same-owner mode-`0700` directory. The deploy
controller MUST recheck every selected sink in one all-host pass before the
first SSH or mutation of any selected host. The
baseline controller MUST publish a receipt for any handled deploy-mode
controller failure after safe receipt-sink validation. When a transaction has
been armed, publication occurs only after rollback has either completed or
become categorically uncertain. Publication MUST be atomic, no-follow,
no-clobber, mode `0600`, and fsync both data and directory. Its exact schema is
`schema_version: 1`, `status: failed`, and `reason`, where `reason` is exactly
one of `apply-rpc-failed`, `confirm-rpc-failed`, `controller-failure`,
`fresh-sftp-failed`, `management-transport-required`, `onboarding-refused`,
`promotion-proof-failed`, `promotion-proof-mismatch`, `prepare-rpc-failed`,
`rollback-uncertain-recovery-armed`, `status-rpc-failed`,
`transaction-identity-mismatch`, or `transaction-receipt-invalid`. It MUST NOT contain
an alias, address, path, key, nonce, capability, digest, child output,
exception text, or traceback. Public output and the Ansible task MUST remain
generic and `no_log`. A successful transaction MUST leave the fresh receipt
path absent. A missing receipt after controller death or publication failure
is an unknown outcome, never success or acceptance evidence. Check mode MUST
not require or write a failure receipt.
An already bootstrapped node may be verified idempotently without consuming a
new key, mutating its identity, or replacing mismatched operator inputs.
On a fresh Debian node with known shadowed packaged SSH directives, an
explicit policy-preserving ownership transaction MUST precede ordinary
deployment. It MUST preview without writes, bind one source revision and node,
retain durable rollback, and require fresh pinned public and Tailnet SSH/SFTP
proof before confirmation. Bootstrap and ordinary deploy MUST NOT perform this
migration implicitly.

#### Scenario: Fresh Debian has packaged main-file SSH directives

- **WHEN** bootstrap confirms both access paths but the packaged main SSH file still has recognized shadowed directives
- **THEN** the separate ownership transaction normalizes only those directives while preserving full effective policy, and ordinary dry-run can subsequently preview baseline hardening.

#### Scenario: One management path fails after ownership activation

- **WHEN** either fresh SSH/SFTP path fails before ownership confirmation
- **THEN** the controller requests bounded rollback and cannot report success; uncertain rollback remains subject to durable recovery.

#### Scenario: Controller public address changes after bootstrap

- **WHEN** the operator renders one node with its private confirmed bootstrap handoff
- **THEN** the renderer binds the handoff digest, alias, public address, SSH port and external path contexts to the selected Terraform node, then uses only the Tailnet IPv4 or IPv6 whose path was actually confirmed while the Terraform public service address remains distinct.
- **AND** a malformed or wrong-length handoff path list refuses before Terraform access; an unsafe, unconfirmed, non-Tailnet or node-mismatched handoff refuses before publication and preserves the previously rendered inventory.

#### Scenario: Deploy receives a new enrollment capability

- **WHEN** an enrollment key is supplied to ordinary deploy
- **THEN** it refuses before SSH or Ansible rather than silently retaining the old enrollment path.

#### Scenario: Bootstrap succeeds but protocol proof fails

- **WHEN** ordinary deployment cannot prove required VPN profiles
- **THEN** deployment fails under its existing rollback contract and bootstrap evidence cannot satisfy that gate.

#### Scenario: SSH baseline convergence fails under hidden Ansible output

- **WHEN** a handled baseline pre-transaction validation, onboarding, prepare, apply, fresh transport proof, promotion proof, confirmation, or rollback operation refuses during ordinary deploy
- **THEN** the deployment remains failed and a fresh private receipt records only the final allowlisted category, while Ansible output remains redacted and the receipt cannot satisfy deployment or VPN acceptance.

#### Scenario: Apply overlaps periodic SSH recovery

- **WHEN** SSH apply observes the verified periodic recovery worker executing
- **THEN** it waits for that invocation within the existing activation deadline, refusing failure, timeout or identity changes; only completed success or known exit-75 contention permits requesting the one fresh execution.
- **AND** that requested execution must finish with exit zero and pass the existing lock fence; observation and fresh proof share one 30-second budget.

#### Scenario: Prepare arms state but returns a malformed receipt

- **WHEN** the prepare RPC returns an invalid receipt after it may have armed durable guest state
- **THEN** the controller attempts bounded rollback when the generation and nonce are safely recoverable, otherwise records `rollback-uncertain-recovery-armed`, and publishes no receipt before that outcome is known.

#### Scenario: Prepare returns no receipt

- **WHEN** a deploy-mode prepare RPC times out, disconnects, or is interrupted before the controller receives a receipt
- **THEN** the controller records `rollback-uncertain-recovery-armed` without attempting rollback because durable guest state may exist but no capability was received; an operator interruption retains its original nonzero exit status.
- **AND** check-mode preview failures retain their non-mutating RPC category and publish no receipt.

#### Scenario: Failure receipt authority is unsafe before SSH

- **WHEN** the alias mapping is missing or mismatched, a pathname contains an unencodable surrogate, paths collide including same-directory names that differ only by case or canonical Unicode normalization, a receipt already exists, path ancestry is unsafe, or the parent changes before the deploy controller's pre-SSH recheck
- **THEN** the controller's single all-host recheck refuses deployment before readiness, SSH, or mutation of any selected host; no existing receipt is replaced and no transaction is armed.

#### Scenario: Failure receipt authority changes after preflight

- **WHEN** the receipt parent or final path changes after preflight or after the baseline transaction is armed
- **THEN** no existing file is replaced, deployment remains failed, and an absent receipt is an unknown outcome rather than success or acceptance evidence.

#### Scenario: AWG protocol proof resolves a hostname in its namespace

- **WHEN** ordinary deployment validates the required AWG profile with a hostname probe
- **THEN** the sentinel uses the validated role-profile IPv4 DNS servers through a private resolver file for the generated network namespace and removes the resolver file and directory on success, failure, or partial creation.

#### Scenario: Provider examples drive listener parity

- **WHEN** an operator starts from any tracked production or staging provider example
- **THEN** its public listener contract includes nginx's TCP/80 redirect listener as well as the enabled VPN listeners, so ordinary deployment can reach protocol proof without a known example-contract mismatch.

### Requirement: REQ-TFB-ACCEPTANCE — Positive runtime behavior is required for delivery

The implementation MUST pass regression and failure-path tests, native Linux
firewall/systemd recovery checks, applicable local gates, exact-revision hosted
CI, and authorized disposable staging with fresh dual-path SSH, reboot and
controller-loss recovery. Staging MUST then exercise normal deployment and
real protocol proof followed by UUID-bound deletion and provider absence.
Fixtures, refusal-only behavior, and source checks MUST NOT close this feature.

Failed bootstrap MUST also support retirement of an issued but never-bound
client and its prepared executor after registered guarded provider absence.
The client transaction MUST hold cleanup authority and the canonical SOPS
locks, require the genuine current empty Terraform state at the registered
path, freeze its new digest, and reject copied manifests, unclaimed absence,
onboarding outputs and state replacement. Pre-destroy and destroyed hashes
MUST NOT be required to be equal. Prepared VM removal MUST require that
client's completed receipt and absent onboarding outputs, verify its prepared
manifest/configuration/marker and Docker context, serialize against binding,
retain interrupted removal intent, and publish success only after exact
profile absence. Expiry MUST NOT block verified cleanup.

#### Scenario: Destroy changes state before unbound retirement

- **WHEN** registered guarded destruction succeeds and Terraform writes its empty new state
- **THEN** only the exact issued client can retire under unchanged registered authority and a frozen post-destroy digest; copied authority or nonempty/replaced state refuses before secret mutation.

#### Scenario: An executor was prepared but never bound

- **WHEN** that client's unbound retirement receipt is complete and its onboarding outputs remain absent
- **THEN** the separate removal operation verifies and deletes only the exact owned prepared VM, safely resumes interrupted removal, and never synthesizes onboarding state.

The supported staging interface MUST expose distinct controller-loss and reboot
recovery operations rather than a caller-selected arbitrary fault. Each
operation MUST accept only a disposable `ci-staging-*` target with current
cleanup ownership and a new private evidence path distinct from the positive
bootstrap handoff. It MUST obtain a durable pending enrollment, prevent the
enrollment worker from confirming or requesting rollback, and terminate that
worker if its controller parent disappears. It MUST accept success only after
the corresponding autonomous recovery path, fresh pinned public SSH and SFTP,
and a final idle unconfirmed state.
Reboot acceptance MUST additionally prove a changed boot identity and current-
boot success of both recovery phases. Published evidence MUST be mode `0600`,
atomic, redacted, and exclude addresses, enrollment keys, raw capabilities,
nonces, provider state, and remote command output. After durable evidence
publication, the controller MUST append the categorical operation and result
through the canonical best-effort audit interface without forwarding the
enrollment key, addresses, or private artifact paths.

#### Scenario: The enrollment controller disappears

- **WHEN** the staging controller-loss operation receives a durable pending enrollment
- **THEN** it terminates that exact worker without confirmation or rollback and waits through the lease for a fresh successful recovery invocation before accepting restored public SSH/SFTP and idle state.

#### Scenario: The node reboots while enrollment is pending

- **WHEN** the staging reboot operation receives a durable pending enrollment
- **THEN** it terminates that exact worker, reboots through pinned public SSH, and accepts only a new boot whose early firewall and late identity recovery both succeeded before fresh public SSH/SFTP and idle state.

#### Scenario: Recovery proof is stale or ambiguous

- **WHEN** a recovery unit result predates the transaction, the controller worker was not killed as specified, a boot identity did not change, or final state is not idle
- **THEN** no success evidence is published and the remaining private/guest state is retained for diagnosis.

#### Scenario: Public SSH does not return within the reboot proof budget

- **WHEN** the reboot request has been attempted, public SSH loss was observed, and every bounded post-reboot SSH attempt fails
- **THEN** no success evidence or passed audit is published, and a distinct private mode-`0600` diagnostic records only `status: incomplete`, the categorical reboot-request result, SSH down/up observations, `recovery_status: not_observed`, and `unit_proof_stage: not_started`.

#### Scenario: A later reboot proof stage refuses

- **WHEN** public SSH returned but status inspection, current-boot unit proof, or final public postconditions refuse
- **THEN** no success evidence or passed audit is published, and the distinct private mode-`0600` diagnostic records only the last observed categorical recovery status and `unit_proof_stage` of `not_started`, `rejected`, or `passed`, without exception text or remote output.

#### Scenario: Recovery controller exits unexpectedly

- **WHEN** the parent controller disappears before it can terminate the paused enrollment worker
- **THEN** the worker observes loss of parent ownership and exits without confirmation or explicit rollback, while durable guest recovery remains authoritative.

#### Scenario: Recovery evidence collides with positive bootstrap output

- **WHEN** a recovery operation names the referenced bootstrap handoff path as its evidence path
- **THEN** it refuses before enrollment, reboot, or any other destructive action.

#### Scenario: Recovery success and diagnostic outputs collide

- **WHEN** a recovery operation names the same path for success evidence and incomplete diagnostics
- **THEN** it refuses before enrollment, reboot, or any other destructive action.

#### Scenario: An operator supplies an obsolete recovery wrapper

- **WHEN** the recovery wrapper declares schema 1 or omits the distinct diagnostic path
- **THEN** it refuses before SSH, enrollment, reboot, or any other guest change; the operator must replace it with schema 2 and a fresh absent diagnostic path.

#### Scenario: Local tests pass without staging

- **WHEN** only unit or container evidence exists
- **THEN** the feature remains incomplete for staging/live acceptance.
