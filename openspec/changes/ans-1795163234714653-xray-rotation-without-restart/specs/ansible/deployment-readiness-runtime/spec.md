## RENAMED Requirements

- FROM: `### Requirement: REQ-DRR-ROTATE — Rotate Xray logs through guarded recovery`
- TO: `### Requirement: REQ-DRR-ROTATE — Rotate Xray logs without a restart`

## MODIFIED Requirements

### Requirement: REQ-DRR-ROTATE — Rotate Xray logs without a restart

Xray log rotation MUST use `copytruncate` and MUST NOT run a rotation script. It MUST NOT call the generation controller or `systemctl restart xray.service` on any profile.

#### Scenario: A production profile omits the optional toggle

- **WHEN** the rotation policy renders for any `group_vars/vpn-*.yml` profile
- **THEN** it contains `copytruncate`
- **AND** it contains no `postrotate`, `prerotate`, `firstaction` or `lastaction` script

#### Scenario: No protected frontend is enabled

- **WHEN** the profile is subscription-only or disables every protected frontend
- **THEN** the policy is the same and still runs no restart

#### Scenario: A nonempty log rotates under a running Xray

- **WHEN** logrotate forces the rendered policy against a running Xray with a nonempty access log
- **THEN** the Xray main PID is unchanged, a rotated copy exists and authenticated client traffic still succeeds

## ADDED Requirements

### Requirement: REQ-DRR-XRAY-RUNTIME — Bounded Xray sniffing, sandbox and file limit

Every Xray inbound that enables sniffing MUST set `routeOnly` so the requested destination reaches egress unchanged. The Xray unit MUST set `ProtectProc=invisible`, `PrivateDevices`, `ProtectClock`, `ProtectKernelLogs`, `ProtectHostname` and `UMask=0077`, and its `LimitNOFILE` MUST be lower than the baseline `fs.file-max`.

#### Scenario: Sniffed name differs from the requested destination

- **WHEN** a client requests an address and the sniffed TLS name differs
- **THEN** routing rules can match the sniffed name and the outbound request keeps the requested address

#### Scenario: Unit file limit

- **WHEN** the unit and the baseline sysctl render
- **THEN** the unit `LimitNOFILE` is lower than `fs.file-max`
