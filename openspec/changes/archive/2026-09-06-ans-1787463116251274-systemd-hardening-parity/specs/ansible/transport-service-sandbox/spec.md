## Purpose

Define the minimum systemd sandbox that every internet-facing transport
service unit in this repository must enforce, so a parser exploit in any
listener meets the same narrow kernel and syscall surface.

## ADDED Requirements

### Requirement: REQ-SANDBOX-BASELINE — Uniform sandbox floor for transport units

Every unit that runs an internet-facing transport daemon MUST declare, at
minimum: non-root `User`/`Group`, `NoNewPrivileges=true`, `PrivateTmp=true`,
`ProtectHome=true`, `ProtectSystem=strict`, `ProtectKernelTunables=yes`,
`ProtectKernelModules=yes`, `ProtectControlGroups=yes`,
`RestrictNamespaces=yes`, `MemoryDenyWriteExecute=true`, `LockPersonality=yes`,
`RestrictRealtime=yes`, `RestrictSUIDSGID=yes`,
`SystemCallArchitectures=native`, and a `SystemCallFilter=@system-service`
allowlist with `@privileged @resources` denied.

#### Scenario: New transport role is added

- **WHEN** a contributor adds a role whose unit starts an internet-facing
  daemon
- **THEN** its unit template carries every directive of the baseline

#### Scenario: Existing unit drifts below the baseline

- **WHEN** a contract check inspects the hysteria, hysteria-realm, or snell
  unit templates
- **THEN** all baseline directives are present

#### Scenario: Service still runs under the tightened sandbox

- **WHEN** the molecule scenarios for hysteria and snell converge with the
  updated units
- **THEN** the services start and pass their existing verification steps
