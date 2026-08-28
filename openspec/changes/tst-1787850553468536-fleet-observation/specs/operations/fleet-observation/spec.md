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
