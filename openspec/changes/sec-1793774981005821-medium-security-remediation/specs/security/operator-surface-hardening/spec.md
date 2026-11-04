## Purpose

Deployed nodes cannot erase offsite backups or forge telemetry for other nodes. SSH sources stay narrow. The public surfaces reveal no software versions and no cross-network REALITY identity.

## ADDED Requirements

### Requirement: REQ-SEC-OSH-BACKUP-APPEND-ONLY — Deliver only append-only offsite credentials

Before a deploy or backup configuration writes the offsite rclone configuration, the controller MUST refuse a B2 credential unless its capabilities are exactly `listBuckets`, `listFiles`, `readFiles` and `writeFiles`, it is restricted to one private bucket and to the node's `<path>/<hostname>/` prefix, and the remote does not enable `hard_delete`.

#### Scenario: Credential that can delete

- **WHEN** the configured key includes `deleteFiles`
- **THEN** the run stops with `append-only-grant-required` before the credential reaches the node

#### Scenario: Credential scoped to another node or the whole bucket

- **WHEN** the key's name prefix is not this node's replica directory
- **THEN** the run stops with `node-prefix-grant-required`

### Requirement: REQ-SEC-OSH-INGEST-NODE-LABEL — Attribute ingested series to the authenticated node

The collector MUST store every remote-write sample with the `node` label equal to the identity bound to the verified client certificate, whatever `node` value the payload carries.

#### Scenario: Forged node label

- **WHEN** an authenticated node sends a sample labelled with another node's identity
- **THEN** the sample is stored with the sender's own identity

### Requirement: REQ-SEC-OSH-SSH-PREFIX-FLOOR — Refuse broad SSH source networks

Every provider root MUST reject an `allowed_ssh_cidrs` entry broader than /24 for IPv4 or /48 for IPv6.

#### Scenario: Broad IPv4 network

- **WHEN** `allowed_ssh_cidrs` contains `203.0.112.0/23`
- **THEN** plan fails validation

### Requirement: REQ-SEC-OSH-HTTP-VERSION-HIDDEN — Hide the server version on the public site listeners

Every server block of the public nginx-XHTTP site MUST set `server_tokens off`, including the HTTP/80 ACME and redirect server.

#### Scenario: Plain HTTP request by address

- **WHEN** a client sends an HTTP/80 request to the public address
- **THEN** the `Server` header carries no version

### Requirement: REQ-SEC-OSH-REALITY-SAME-HOST — Serve REALITY from an owned same-host target

Production P0 MUST use the self-steal profile, so that unauthenticated probes see a certificate for an owned name that resolves to the P0 address.

#### Scenario: Probe without valid REALITY authentication

- **WHEN** a scanner opens TLS to P0 TCP/443
- **THEN** it receives the owned `edge` certificate, not a third-party certificate
