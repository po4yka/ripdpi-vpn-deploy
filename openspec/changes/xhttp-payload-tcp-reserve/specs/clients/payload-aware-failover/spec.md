## Purpose

Recover useful encrypted traffic through a verified TCP reserve after UDP payload failure.

## ADDED Requirements

### Requirement: REQ-FAILOVER-TCP-RESERVE — Prefer a verified TCP reserve after UDP failure

The paired recipient MUST prefer a TCP reserve when the active Hysteria2 transport
fails the existing payload check. It MUST verify exact payload content through
the reserve and retain failure and recovery thresholds, cooldown, bounded retry
and the current encrypted selection when all candidates fail. The version 2
policy and healthy-path quality comparison MUST remain unchanged.

#### Scenario: UDP stalls while TCP transfers useful data

- **WHEN** the active Hysteria2 candidate cannot complete the required body and a TCP reserve succeeds
- **THEN** the TCP reserve is checked before other UDP reserves
- **AND** selection changes only after the existing failure and recovery requirements pass

#### Scenario: All candidates fail

- **WHEN** neither UDP nor TCP candidates pass the payload check
- **THEN** the current encrypted path remains selected and no direct path is selected

#### Scenario: Mixed delivery preserves control policy

- **WHEN** the producer emits a mixed XHTTP and Hysteria2 bundle with an explicit policy
- **THEN** both primary and alternate TCP endpoints remain selector candidates with complete tuning
- **AND** both independent HTTPS controls and every version 2 policy field reach the recipient
