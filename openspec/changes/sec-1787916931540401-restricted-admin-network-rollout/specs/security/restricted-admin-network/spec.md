## Purpose

Preserve administrative access during network changes without weakening authentication, exposing new public management ports, or altering VPN data paths.

## ADDED Requirements

### Requirement: REQ-ADMIN-ISOLATION — Enrollment preserves runtime boundaries

Tailnet enrollment MUST be opt-in, retain ordinary OpenSSH authentication and host keys, and disable Tailscale SSH, DNS acceptance, route acceptance, exit-node use/advertisement and automatic netfilter changes. It MUST NOT print registration credentials or change unrelated Tailnet policy.

#### Scenario: Enroll an existing transport node

- **WHEN** a node joins the approved Tailnet
- **THEN** its previous public SSH login and VPN listeners still work, resolver/routing policy remains unchanged, and the same host key authenticates the Tailnet SSH connection.

### Requirement: REQ-ADMIN-SCOPE — Management authorization is narrow and verified

Tailnet policy and guest firewall MUST restrict management to explicitly approved source devices and the existing SSH port. Existing broad grants MUST NOT silently make a new narrow grant ineffective. Policy changes MUST preserve unrelated authorized access and include positive and negative access tests before enrollment.

#### Scenario: Unapproved device attempts management

- **WHEN** an unapproved Tailnet device attempts the protected SSH endpoint
- **THEN** access is denied while the approved controller and existing emergency public sources retain access.

### Requirement: REQ-ADMIN-MIGRATION — Ownership migration preserves effective SSH policy

The explicit migration MUST stage the complete included configuration, own the exact ordered `sshd_config` plus known 10/20/50 paths, and preserve effective settings for global and actual connection contexts after every apply prefix and reverse rollback suffix. It MAY normalize only the exact recognized packaged-main `KbdInteractiveAuthentication no` and `X11Forwarding yes` defaults when they are already shadowed by the canonical fragments. It MAY also normalize exactly one global `PermitRootLogin yes` after the canonical Include, provided the bootstrap fragment explicitly denies root login and real global plus every supplied connection-context output reports exactly `permitrootlogin no`. A root-login directive before Include, duplicate, unexpected value or missing bootstrap denial MUST refuse before activation. It MUST preserve packaged SFTP, metadata and unrelated bytes. It MUST reject unknown values, unsafe paths, unsupported Include/Match layouts or unresolved ownership conflicts before writes. Algorithm hardening MUST be a separate reviewed transaction. The initial planner MUST reject Match blocks, nested or alternate Includes, and any unknown, duplicate or unshadowed occurrence of an owned directive before activation; it MUST compare the complete global output and explicit direct/Tailnet connection-context outputs with bounded sshd invocations. It MUST snapshot the complete read graph to detect concurrent drift.

#### Scenario: Migrate the known legacy fragments

- **WHEN** recognized packaged-main defaults and legacy matching directives occur in main, 10, 20 and 50
- **THEN** the candidate has one owner per managed scalar directive and identical effective authentication, user, port, algorithms, key paths and forwarding policy.
- **AND** every ordered publication boundary preserves that policy while packaged SFTP, unrelated bytes and metadata remain unchanged.

#### Scenario: Unexpected configuration

- **WHEN** an unknown fragment or Match context changes a managed directive
- **THEN** migration fails before mutation and reports the conflicting file without exposing key material.

### Requirement: REQ-ADMIN-ROLLBACK — Guest rollback is autonomous and durable

Every SSH or guest-firewall activation MUST save and validate the original bytes, permissions and owned runtime scope, durably record its transaction, and arm a persistent local recovery mechanism before its first mutation. Unconfirmed changes MUST recover after controller loss or guest reboot. Confirmation and rollback MUST serialize using the current nonce and generation; retries MUST be idempotent. Corrupt backups or third-party changes MUST fail visibly without overwriting unrelated state. SSH migration MUST have its own fixed-path helper, independent of the full baseline deploy; installation or upgrade of that helper and its units MUST publish one validated immutable generation and retain a durable journal through systemd activation, preventing mixed-version execution and new migration during incomplete installation; it MUST NOT run algorithms changes, firewall convergence, backup handlers, or arbitrary operator commands.

#### Scenario: Controller disappears during activation

- **WHEN** the controller disconnects after any activation write without confirming
- **THEN** the node restores the original owned configuration and access without requiring the controller connection; unrelated nftables tables remain intact.

#### Scenario: Guest reboots before confirmation

- **WHEN** an unconfirmed transaction survives a reboot
- **THEN** boot reconciliation restores the previous configuration before normal network service acceptance.

#### Scenario: Periodic recovery contends with activation

- **WHEN** a periodic worker encounters the transaction lock during activation readiness
- **THEN** its deferred exit 75 is not accepted as execution proof; activation obtains one fresh completed successful worker execution outside the lock and revalidates that proof, the prepared state, lease, snapshot and recovery capability under the lock before writing.
- **AND** only an unambiguous later contention with that same lock interval may be distinguished from a real failure; stale or absent proof, unknown execution ordering, expired state and capability drift refuse activation without writes.

#### Scenario: Ordinary baseline follows ownership migration

- **WHEN** baseline installs its desired SSH configuration on a valid single-owner graph
- **THEN** it uses an explicit separate transaction for main and 20, preserves the bootstrap authentication owners and SFTP, and validates candidate policy before publishing.
- **AND** interruption restores the exact original bytes, metadata and fragment membership; a newly created 20-file is removed only when it still matches the verified candidate.

#### Scenario: Ordinary deployment requires the recovery foundation

- **WHEN** an ordinary dry-run or deployment targets a selected node
- **THEN** the controller checks the exact installed recovery generation, canonical root-owned state and lock, strict dispatcher status in `idle`, `committed` or `rolled_back`, and installed-unit readiness over the same frozen strict transport before the first site Ansible invocation.
- **AND** missing, stale, unsafe or unreadable recovery state refuses without invoking site Ansible or automatically running the explicit recovery installer.

#### Scenario: Recovery generation changes with a terminal receipt

- **WHEN** a recovery engine is upgraded or downgraded with an existing terminal transaction
- **THEN** both engines must parse the unchanged receipt before publication; an engine that cannot read a baseline intent refuses before changing current, journal or state.
- **AND** the current engine reads only an exact canonical three-fragment schema-one ownership receipt in `committed` or `rolled_back` state for status and recovery no-op; `prepare` is the sole transition, archives those exact bytes and then creates a distinct schema-two transaction without rewriting the historical receipt.
- **AND** `apply`, `confirm` and `rollback`, plus every nonterminal, unknown or noncanonical schema-one state, refuse.
- **AND** the frozen schema-one engine refuses terminal schema-two ownership or baseline receipts, including `rolled_back`, before pointer, journal or activation changes.

### Requirement: REQ-ADMIN-PROMOTION — Promotion uses independent proof and serial scope

A rollout MUST stop on the first failed node, use an explicit single-node target, and confirm through a new non-multiplexed SSH connection with the existing user/key/port and pinned host identity. It MUST verify transaction identity, DNS, required VPN probes, unchanged public access and the new Tailnet path before confirmation. Provider firewall changes MUST have an external rollback executor and validated prior rules; guest-only recovery MUST NOT count as provider rollback.

#### Scenario: Existing SSH session masks a broken listener

- **WHEN** the old session remains open but a fresh strict connection fails
- **THEN** confirmation is refused, recovery remains armed, and no next node is modified.

### Requirement: REQ-ADMIN-EVIDENCE — Destructive rehearsal precedes production

Production migration MUST require an authorized isolated staging target and observed real SSH login, forced disconnect, reboot recovery, stale-confirmation rejection and repeated rollback success. Local fixtures, Docker transport, check mode, or successful service status MUST NOT substitute for network acceptance. New cloud spending and deletion of the isolated target MUST remain within the explicit user authorization, verified price and exact-resource cleanup deadline.

#### Scenario: Staging or Tailnet authorization is unavailable

- **WHEN** the required target or authenticated administration session is missing
- **THEN** production enrollment/migration remains blocked and existing access stays unchanged.

#### Scenario: Temporary staging cleanup is authorized

- **WHEN** an authorized isolated staging server is ready for deletion
- **THEN** cleanup requires a private canonical manifest bound to the authenticated provider API username, exact Terraform workspace and state digest, hostname, server UUID, root-storage UUID, authenticated provider `server.created` time and exact target/escalation/hard deadlines at 36, 44 and 47 hours.
- **AND** the manifest provider and environment MUST match the exact destroy command, and a new private evidence inode MUST be reserved before any lifecycle override, plan or provider-changing command.
- **AND** one authorization/reservation step MUST bind the same manifest and state inodes and bytes to the authenticated API username before provider refresh or plan; plan validation MUST require that exact reservation, and an immediate pre-apply transition MUST recheck the account, reservation, state and exclusive hard deadline before recording `apply_started` and invoking Terraform apply.
- **AND** the controller refuses a symlink in any path component, foreign owner, non-private mode, noncanonical or expired deadline, changed state, foreign identifier, or a destroy plan containing any create, update, replacement or deletion outside the exact owned resource set before apply.
- **AND** the private binary plan inode inspected by the controller MUST be the same unreplaceable inode passed to apply; an ambient umask or worktree pathname MUST NOT expose or substitute it.
- **AND** cleanup is not accepted until the authenticated API username exactly matches the manifest before resource lookup and read-only provider checks report the exact server and root storage absent in the same reserved inode; provider mismatch, authentication failure, forbidden resources, existing resources or ambiguous responses remain failures and never claim that cumulative billing was reversed.
- **AND** successful guarded cleanup preserves the existing generated fleet inventory and emits only a categorical redacted audit event after exact provider absence; abort, apply failure or ambiguous absence emits no success audit.
- **AND** only an operation with durable `apply_started_at` strictly before the hard deadline MAY complete read-only absence verification after expiry, and such evidence MUST say `verified_after_expiry` and `expired_after_apply`; a reserved-only or at-deadline operation MUST refuse before resource lookup or apply.
