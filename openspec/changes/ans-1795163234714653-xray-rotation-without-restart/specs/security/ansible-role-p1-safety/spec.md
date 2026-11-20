## MODIFIED Requirements

### Requirement: REQ-P1-XRAY — Safe log authority and activation

Xray startup MUST NOT modify arbitrary filesystem targets through runtime-owned log entries. Rotation MUST leave the running process and its listener in place with writable current logs. Geodata activation MUST use a supported operation that restores an active listener.

#### Scenario: Runtime log entry substitution

- **WHEN** a log entry names an unrelated target
- **THEN** startup cannot change that target's bytes, owner or mode through privileged repair.

#### Scenario: Pinned runtime log rotation

- **WHEN** a nonempty log rotates
- **THEN** no signal or restart is sent, the log is truncated in place with its owner and mode kept, and the same process keeps writing to it.

#### Scenario: Geodata activation

- **WHEN** geodata activation runs
- **THEN** no unsupported HUP is sent and the selected active runtime is reconciled.
