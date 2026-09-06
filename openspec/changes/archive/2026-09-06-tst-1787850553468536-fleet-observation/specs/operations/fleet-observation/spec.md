## Purpose

Provide bounded passive fleet inspection and separately invoked authenticated
client probes without conflating runtime state, repair, and recovery evidence.

## ADDED Requirements

### Requirement: REQ-OBS-PASSIVE — Inspection does not invoke managed-state changes

`make inspect` MUST collect only allowlisted reads over strict SSH. It MUST NOT
invoke Ansible, watchdog, protocol probes, package tools, validators that open
service logs, restore, restic locks, provider APIs, or service mutations. It MUST
NOT upload a remote script, create remote temporary files, or update known_hosts.
The documented guarantee MUST exclude unavoidable SSH audit logs, atime, and
network connection accounting from a claim of absolutely zero host writes.

#### Scenario: Unhealthy service is observed without repair

- **WHEN** an explicitly selected host reports a failed service
- **THEN** inspection reports that failure without restart, reset-failed, probe,
  or any fallback to an active verifier.

### Requirement: REQ-OBS-SSH — Explicit scope and pinned transport

Inspection MUST require explicit hosts, user, port, key, and existing host-key
pins. Transport overrides MUST preserve the identity alias. Connections MUST
use an isolated SSH configuration, disable inherited commands/forwarding,
proxy commands and multiplexing, and have bounded connect and
total timeouts. Unknown keys and unreachable hosts MUST fail closed per host
without widening the selected fleet.

#### Scenario: Unknown key or unreachable host

- **WHEN** one selected endpoint is unreachable or lacks a matching pin
- **THEN** its result is unavailable with a nonzero aggregate exit status, other
  explicitly selected hosts may complete, and no pin or firewall rule is changed.

### Requirement: REQ-OBS-EVIDENCE — Missing proof never becomes health

Inspection MUST distinguish observed service state, deployed source identity,
listener metadata, reported backup freshness, and restore marker source/time. Output
MUST contain only allowlisted redacted fields. Missing, malformed, future-dated,
or stale evidence MUST remain unknown or stale, never success. Backup timer
activity MUST NOT count as backup or restore proof; local restore MUST NOT count
as offsite restore. Passive inspection MUST NOT mint a client traffic verdict.
Files MUST be bounded regular-file reads without symlink traversal. Raw command
output, stderr, configuration content, and credential-derived hashes MUST NOT
be copied to reports. Unknown backup freshness MUST remain unknown when no
safe existing metadata provides it; inspection MUST NOT invoke restic to fill it.

#### Scenario: Local backup without a restore marker

- **WHEN** the timer is active but restore evidence is absent
- **THEN** the result explicitly reports restore as unknown and offsite proof
  absent, without attempting a restore or printing configuration secrets.

### Requirement: REQ-OBS-RESTORE — Cleanup removes only this restore's resources

The isolated restore runner MUST acquire its private target before installing
cleanup that can remove it. An existing target, including a symlink, MUST cause
failure without modification of that target or its contents. Failure MUST
preserve prior success evidence; success MUST publish new evidence only after
cleanup. This change MUST NOT alter retention, invoke prune, target live paths,
select a remote backend, or fall back from remote to local restore.

#### Scenario: Existing target at invocation

- **WHEN** a restore invocation encounters an existing target with prior data
- **THEN** it fails before restore and cleanup leaves that data and any previous
  success marker untouched.

### Requirement: REQ-OBS-BACKUP-CONFIG — Configure offsite replication without execution

`make backup-configure` MUST require clean committed controller source, an
explicit exact single inventory alias (not a group, pattern, exclusion, or
unknown host), and strict canonical secret validation.
Git cleanliness and provenance MUST use the actual controller checkout under a
controlled environment before any Ansible process. Inventory selection MUST use
one immutable private snapshot and pin the selected SSH identity/transport. Child
processes MUST NOT inherit execution/plugin/callback overrides. Automatic vars
plugins MUST be disabled; tracked all/vpn/cohort variables, SOPS and validated
extra-vars MUST retain their canonical order through actual Ansible loading.
External host_vars and arbitrary inventory backup overrides are unsupported.

It MUST configure the existing rclone remote and backup/restore scripts through
shared role configuration tasks. It MAY install the already-declared rclone
package when absent, without upgrading packages or refreshing all package
indexes. It MUST require an initialized existing local repository and matching
private restic password; it MUST NOT initialize or change either. It MUST NOT
import site/baseline/firewall tasks, skip safety checks, run backup, prune, sync,
restore, or modify/start/restart units or timers. Secret content and diffs MUST
remain private. Whole-site source identity MUST NOT be rewritten by this command.
Repository preflight MUST use only the installed restic binary with the explicit
canonical local repository/password paths, `--no-cache --no-lock cat config`, a
bounded timeout, and discarded captured output. Failure MUST precede lock,
package, or configuration writes. This proves configuration decryption only,
not repository integrity or recovery. Enabled Ansible debug MUST be rejected
and disabled explicitly for child processes so `no_log` cannot be bypassed by
inherited configuration.

#### Scenario: Ambient controller or inventory overrides

- **WHEN** another Git directory, adjacent host_vars, or an Ansible plugin/SSH
  environment override is present
- **THEN** it cannot change source validation, selected transport, variable
  loading or execution; canonical cohort rendering remains unchanged.

#### Scenario: Existing local backup gains remote configuration

- **WHEN** the selected host has a valid local repository and matching password,
  rclone is absent, and the owner has quiesced backup execution
- **THEN** the command installs rclone, validates and installs the remote config
  and both scripts, leaves services/timers unchanged, and is idempotent on rerun.

### Requirement: REQ-OBS-BACKUP-QUIESCENCE — Configuration owns a finite exclusive window

The configuration command MUST require an owner-controlled exclusive maintenance
window, both backup timers persistently disabled, both timers and services
inactive, and no queued jobs for those units. It MUST recheck quiescence before and after file installation, serialize
configuration using an exclusive per-host lock, and reject existing locks.
All candidate files MUST be staged and validated before live replacement; prior
files MUST remain recoverable privately. Failure MUST NOT start services, remove
operator resources, or conceal partial installation. Concurrent privileged
manual execution or deployment outside that window is not guaranteed safe.
Any publication or postcheck failure MUST restore previous bytes, modes, and
absence for all three files. If restoration cannot be confirmed, the command
MUST retain its private recovery bundle and lock and explicitly prohibit timer
resumption until operator repair.
It MUST reject incomplete or malformed persistent recovery bundles even when
the runtime lock has disappeared. This does not promise atomic multi-file
publication across power loss; disabled timers prevent the canonical automatic
trigger while recovery remains pending.

#### Scenario: Active timer or overlapping configuration

- **WHEN** a timer/service is active, a unit job is pending, or another invocation
  owns the lock
- **THEN** configuration fails before replacing live files, does not stop the
  other work, and does not remove the existing lock or prior configuration.

### Requirement: REQ-OBS-OFFSITE-PROOF — Configuration is not recovery evidence

A successful configuration command MUST NOT be reported as an uploaded backup
or successful recovery. Actual offsite acceptance MUST separately verify an
initial copy and an isolated restore from the configured remote without local
fallback, with no retention pruning or restore into live configuration paths.

#### Scenario: Remote configuration exists without an initial copy

- **WHEN** configuration has completed but the destination has no verified copy
- **THEN** offsite and recovery acceptance remain pending, regardless of timer
  state or configuration success.

### Requirement: REQ-OBS-XHTTP — Fullstack onboarding uses compatible runtimes

Required REALITY and Hysteria2 profiles MUST use the official pinned sing-box
runtime; XHTTP MUST use an independently pinned Xray runtime and verified TLS.
Fullstack installation MUST validate every required profile before remote
installation. Every configured endpoint variant MUST retain its result, and a
successful variant MUST establish that logical profile's liveness. Missing or
incompatible runtime/configuration MUST be error, not blocked or healthy.

#### Scenario: Fullstack profile rendering

- **WHEN** the named client has valid material for all four transports
- **THEN** onboarding renders XHTTP as an Xray profile rather than asking stock
  sing-box to accept RIPDPI-only JSON, and parser checks run before installation.

### Requirement: REQ-OBS-PATH — HTTP probes cannot bypass the selected tunnel

Every direct and tunneled curl invocation MUST disable user curl configuration
and neutralize ambient proxy variables. Direct control MUST explicitly avoid
proxies; SOCKS probes MUST explicitly override NO_PROXY bypass. Expected HTTPS
status and TLS validation MUST be mandatory. A network failure MUST contribute
blocked evidence only with a successful contemporaneous direct control.

#### Scenario: Ambient bypass configuration

- **WHEN** curlrc, HTTPS_PROXY, ALL_PROXY, or NO_PROXY would change the path
- **THEN** control still uses the direct path and a selected tunnel still carries
  the authenticated request; a refused SOCKS port cannot become a direct success.

### Requirement: REQ-OBS-IDENTITY — Dedicated client material and explicit AWG binding

Onboarding MUST use a unique named client per sentinel, refuse revoked clients,
and transfer only that client's material. AWG MUST select an explicit provider,
environment, and instance, validate its peer/address, and compare the supplied
private key's derived public key with the selected peer before remote writes.
Private keys MUST travel through private files or stdin/FDs, never argv or env.
Decryption MUST use the canonical materializer; no full SOPS document may reach
the sentinel. A missing key MUST NOT trigger reuse of another device's identity.

#### Scenario: Wrong or revoked AWG key

- **WHEN** the supplied private key does not match the active selected peer, or
  the client has a revoked lifecycle state
- **THEN** onboarding fails before installation, peer changes, or remote writes.

### Requirement: REQ-OBS-LIFECYCLE — Active probes own and clean their resources

Active probes MUST use private temporary configuration, loopback-only listeners,
bounded child processes, and cleanup on success, failure, timeout, or signal.
They MUST terminate only their own processes and remove only their own temporary
namespace/interfaces. They MUST NOT restart production services, change host
default routes, rotate identities, or modify provider rules.

#### Scenario: Interrupted AWG probe

- **WHEN** a probe is interrupted after interface creation
- **THEN** its interface, namespace, process, and temporary secrets are removed
  while pre-existing interfaces, routes, and production services remain intact.

### Requirement: REQ-OBS-DISPOSABLE-EXECUTOR — One-shot consumer-uplink execution is exact and removable

The retired Raspberry Pi MUST NOT remain an acceptance prerequisite. A one-shot
replacement MAY use an operator-owned disposable systemd Linux VM only when a
private controller manifest proves a non-default profile, no host mounts, no
reachable VM address or port forwarder, no generated SSH config, unchanged
Docker context, bounded lifetime, and an exact root-owned executor identity.
Before any dedicated material reaches the VM, the installer MUST bind that
identity to the exact config, cleanup manifest, sentinel, client, generation,
provenance and target identity. The evaluator MUST reject a report that does not
match the private binding exactly.

#### Scenario: Executor drifts before credential transfer

- **WHEN** the profile, config, root marker, mount table, context or expiry no
  longer satisfies its prepared private manifest
- **THEN** onboarding refuses before key input, decryption or remote writes.

#### Scenario: Guarded target is absent and the executor is retired

- **WHEN** the exact bound provider cleanup evidence records authenticated
  absence of the server and root storage with no active owned resources
- **THEN** de-onboarding removes the dedicated encrypted client entries, exact
  local assignment and single-sentinel config, then deletes only the exact
  root-marker-bound profile, while retaining categorical private evidence.
- **AND** malformed, foreign or partially matching artifacts fail closed without
  deleting them; a partially completed exact de-onboarding is safely retryable.

### Requirement: REQ-OBS-ACCEPTANCE — Live proof has explicit limits

Completion MUST include actual external authenticated REALITY, XHTTP, Hysteria2,
and AWG HTTPS traffic using pinned client runtimes and a fresh AWG handshake.
Evidence MUST record controller/runner source identity, client generation ID,
public-profile digest, runtime versions, vantage, address family, time, and
tested transport without secrets. Deployed server identity MUST be reported
separately and never inferred from the controller checkout. IPv4 HTTPS proof MUST NOT be claimed
as UDP payload, IPv6, Android client, filtered-path quorum, rotation, or offsite
restore acceptance. An unavailable prerequisite MUST leave live acceptance open.

#### Scenario: One external sentinel passes four profiles

- **WHEN** a single ordinary external vantage completes all four probes
- **THEN** evidence identifies exactly that vantage and tested paths, and neither
  two-vantage quorum nor recurring Android AWG acceptance is marked complete.

### Requirement: REQ-OBS-ROLLOUT — Explicit configuration migration and rollback

All repository callers, schemas, examples, and documentation MUST adopt the
Xray pin and explicit AWG binding. Old ambiguous fullstack configuration MUST
fail with a precise migration error. Installation MUST stage and validate a
complete candidate before replacing the active sentinel; failed validation or
initial active probe MUST preserve or restore the previous complete installation
and assignment. It MUST NOT publish a healthy assignment on failure.

#### Scenario: Candidate profile parser fails

- **WHEN** candidate Xray or sing-box validation fails
- **THEN** the prior sentinel configuration and registry assignment remain
  unchanged, and the operator sees a configuration failure rather than success.
