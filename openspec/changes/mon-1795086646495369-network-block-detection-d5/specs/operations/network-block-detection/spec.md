## Purpose

Define the alert and rotation hint that identify a network-specific block when server probes are healthy but client reports show failure.

## ADDED Requirements

### Requirement: REQ-BLOCK-ALERT — Divergence alert

The system MUST fire a "blocked in network" alert for a protocol and ASN when the sentinel probe for that protocol is healthy and the client failure ratio exceeds the threshold with at least the configured attempts for the configured duration.

#### Scenario: divergence alert

- **WHEN** sentinel success is 1 and client failure ratio is 70 percent for an ASN with enough attempts
- **THEN** the alert fires with protocol, ASN and country labels

### Requirement: REQ-BLOCK-NOT-SERVER — No block alert when the server is down

The block alert MUST NOT fire when the sentinel for that protocol is failing, so server outages stay under the existing protocol alerts.

#### Scenario: no block alert when the server is down

- **WHEN** sentinel success is 0 and client failures are high
- **THEN** only the server alert fires

### Requirement: REQ-BLOCK-LOWSAMPLE — Low sample suppression

The alert MUST NOT fire when attempts for the ASN and protocol are below the configured floor, or when fewer distinct reports than the report floor carry them.

#### Scenario: low sample suppression

- **WHEN** client failure ratio is 100 percent with fewer attempts than the floor
- **THEN** no alert fires

#### Scenario: one large report

- **WHEN** one report carries every attempt of a 70 percent failure divergence
- **THEN** neither field-report alert fires

### Requirement: REQ-BLOCK-ORIGIN — Trusted origins only

The field-report alerts MUST read field-report series only from the configured subscription hosts, and the sentinel term MUST read probe series that the relay admits only from the collector's own agent.

#### Scenario: an untrusted node sends the divergence

- **WHEN** an enrolled node that is no configured subscription host sends field-report series for a full divergence
- **THEN** neither field-report alert fires

### Requirement: REQ-BLOCK-NAMED-NETWORK — Only a named network can be blocked

The block alert MUST NOT evaluate the folded `network` values `other` and `unknown` in any of its selectors, because each folds many networks and names none to rotate away from. The fleet-wide failure-ratio alert MUST keep counting them.

#### Scenario: the folded values pass every threshold

- **WHEN** reports labelled `network="other"` or `network="unknown"` show a full divergence while the sentinel sees the protocol healthy
- **THEN** the block alert does not fire and the failure-ratio alert fires for that value

### Requirement: REQ-BLOCK-HINT — Rotation hint is advisory

The alert annotation MUST include the failure-stage mix and a rotation hint, and `scripts/fleet-rotate.sh` PLAN mode MUST be able to show the hint while MUST NOT start any rotation from it.

#### Scenario: rotation hint is advisory

- **WHEN** the alert is active and the operator runs fleet-rotate in PLAN mode
- **THEN** the hint is shown and no rotation or deploy action happens

### Requirement: REQ-BLOCK-RUNBOOK — Runbook and action annotations

The alert MUST carry the action and runbook annotations required by the alert-message rules and have an anchored runbook section.

#### Scenario: runbook and action annotations

- **WHEN** the alert rules are rendered and linted
- **THEN** the annotation and anchor tests pass
