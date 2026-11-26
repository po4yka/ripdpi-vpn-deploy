## Purpose

Record the result of node-initiated connections beside the client-direction result, so a block can be classed as one-way or two-way.

## ADDED Requirements

### Requirement: REQ-DIR-PROBE — Node-initiated probe

The system MUST test connections that a node starts toward a configured set of domestic targets and export the stage result with a direction label.

#### Scenario: targets reachable

- **WHEN** the node connects and completes TLS to a target
- **THEN** the metric shows success for the node-initiated direction

#### Scenario: targets blocked

- **WHEN** the node connect or TLS stage fails
- **THEN** the metric shows the failed stage for the node-initiated direction

### Requirement: REQ-DIR-HINT — Direction in the rotation hint

The block detection hint MAY include the direction label. It MUST NOT start or change rotation.

#### Scenario: client-only block

- **WHEN** client probes fail and node-initiated probes pass
- **THEN** the hint says unreachable for clients only

#### Scenario: two-way block

- **WHEN** client probes and node-initiated probes both fail
- **THEN** the hint says blocked both ways

### Requirement: REQ-DIR-BOUNDED — Bounded probe traffic

The probe MUST bound its rate and its target count and MUST NOT carry client data.

#### Scenario: over the bound

- **WHEN** the configured target count is above the maximum
- **THEN** the role refuses the configuration
