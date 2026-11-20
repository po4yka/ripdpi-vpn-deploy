## MODIFIED Requirements

### Requirement: REQ-AUDIT-GENERATION — Scoped log rotation

Xray log rotation MUST NOT restart, recover or signal any frontend, with or without the transport guard. It MUST rotate by truncating the held log files in place.

#### Scenario: Scoped log rotation

- **WHEN** Xray logs rotate while Xray and Hysteria are healthy
- **THEN** both keep their running processes and no generation recovery is requested.
