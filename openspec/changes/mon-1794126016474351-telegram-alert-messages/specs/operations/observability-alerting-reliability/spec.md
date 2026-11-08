## Purpose

Make each delivered alert tell the operator what failed, where, since when, and what to check first.

## ADDED Requirements

### Requirement: REQ-ALERT-MESSAGE — Render structured Telegram alert messages

The relay MUST render each alert group as valid Telegram HTML with balanced tags and escaped external values. The message MUST show the status, the summary, the environment and node, one line per alert with its role and readable UTC time, and a link to the runbook.

#### Scenario: Grouped alert exceeds the message limit

- **WHEN** a group contains more alert lines than fit in 4096 characters
- **THEN** the relay omits whole alert lines, reports the omitted count, and the message tags stay balanced

#### Scenario: Timestamp cannot be parsed

- **WHEN** an alert has a timestamp that the relay cannot parse
- **THEN** the relay delivers the alert and shows the escaped original value

### Requirement: REQ-ALERT-ACTION — Give every rule an action and an exact runbook section

Every alert rule MUST define an `action` of at most 160 characters and a `runbook` that names an existing section for its incident family. The relay MUST refuse a `runbook` value outside the repository documentation path pattern, because the value becomes a link.

#### Scenario: Firing alert is delivered

- **WHEN** a firing alert from a current rule is delivered
- **THEN** the message contains the action and a link to the section of the incident family

#### Scenario: Hostile runbook value

- **WHEN** a webhook carries a runbook with a URL scheme, a quote or a parent path
- **THEN** the relay refuses the payload

### Requirement: REQ-ALERT-OLDER-RULES — Deliver alerts from an older rule generation

The relay MUST deliver alerts that have no `action` annotation, because a failed Prometheus activation can leave a new relay with older rules.

#### Scenario: Older rules after a failed activation

- **WHEN** a firing alert has no `action` annotation and a runbook without a section anchor
- **THEN** the relay delivers the message without an action line

### Requirement: REQ-KUMA-MESSAGE — Document secondary message formatting

The repository MUST document a Kuma Telegram HTML template and a description for each monitor kind. The template MUST escape every value and MUST render when Kuma sends a test without a monitor or heartbeat.

#### Scenario: Kuma test notification

- **WHEN** an operator presses the Kuma test button with the documented template
- **THEN** the template renders a TEST message without a monitor or heartbeat
