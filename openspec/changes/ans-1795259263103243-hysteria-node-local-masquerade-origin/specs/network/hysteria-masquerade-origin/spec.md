## Purpose

Define where the Hysteria masquerade site comes from, so that a probe of a UDP node gets a site that the node itself hosts.

## ADDED Requirements

### Requirement: REQ-HY-MASQUERADE-NODE-LOCAL — Serve the masquerade site from the node

The implementation MUST serve the Hysteria masquerade site from the published site bundle tree on the node when the node has a site bundle.

#### Scenario: Node with a site bundle

- **WHEN** a `vpn-p2-udp` node has a published site bundle
- **THEN** the Hysteria configuration uses the `file` masquerade type with the published directory, and HTTP/3, HTTPS and HTTP requests return pages of that bundle

#### Scenario: Node without a site bundle

- **WHEN** a `vpn-p2-udp` node has no site bundle
- **THEN** the Hysteria configuration keeps the proxy origin, and the self-origin refusal still applies

### Requirement: REQ-HY-MASQUERADE-FILE-ADMISSION — Refuse an unusable node-local origin

The implementation MUST refuse a `file` masquerade origin whose directory is missing, empty or writable by a user other than the bundle publisher, before Hysteria restarts.

#### Scenario: Missing published tree

- **WHEN** the configured directory does not exist on the node
- **THEN** the role fails before it changes the Hysteria configuration
