# network/transport-audit-boundaries Specification

## Purpose
Preserve protocol routing, client options and input safety across the audited transport combinations.
## Requirements
### Requirement: REQ-AUDIT-HOPPING — Local hopping admission

The implementation MUST redirect only locally addressed public-ingress hopping packets and preserve transit UDP.

#### Scenario: Local hopping admission boundary

- **WHEN** a forwarded client packet targets a remote address within the hopping range
- **THEN** it retains its remote destination.

### Requirement: REQ-AUDIT-SPLIT — Persistent split-hop boundary

The implementation MUST reject original protected-UID traffic outside its configured tunnel, including when that tunnel stops.

#### Scenario: Persistent split-hop boundary boundary

- **WHEN** the tunnel is stopped while a protected process stays active
- **THEN** new IPv4 and IPv6 originals cannot use the direct uplink; accepted-client replies remain usable.

#### Scenario: Explicit topology retirement

- **WHEN** the role is explicitly disabled
- **THEN** canonical firewall convergence omits its guard, and standalone retirement refuses before mutation if an earlier shared guard remains.

### Requirement: REQ-AUDIT-STRICT — Enabled overlay strict egress

The implementation MUST admit the required overlay UDP for enabled Tailnet management and split-hop initiation without opening all host UDP.

#### Scenario: Enabled overlay strict egress boundary

- **WHEN** strict mode has no proxy transport but enables these overlays
- **THEN** the admitted overlay traffic passes and unrelated host UDP remains denied.

### Requirement: REQ-AUDIT-EXPORT — Complete Hysteria metadata

The implementation MUST emit matching metadata for every Hysteria endpoint and correct official-client bandwidth hints.

#### Scenario: Complete Hysteria metadata boundary

- **WHEN** two Hysteria hosts have hopping and asymmetric bounded server rates
- **THEN** both retain hopping and official sing-box receives correctly directed positive integer Mbps hints; BBR and RIPDPI limitations are stated.

### Requirement: REQ-AUDIT-AWG — Pinned AWG wire admission

The implementation MUST reject equal initiation and response sizes and headers that the pinned engine silently rewrites.

#### Scenario: Pinned AWG wire admission boundary

- **WHEN** S1=0 and S2=56 or a noncanonical header at most four is supplied
- **THEN** controller validation refuses before runtime or export; standard 1,2,3,4 remains supported.

### Requirement: REQ-AUDIT-DNS — DNS-Morph preflight

The implementation MUST require a canonical base64 32-byte Ed25519 seed and a data-plane endpoint before host mutation unless echo-only is explicitly selected.

#### Scenario: DNS-Morph preflight boundary

- **WHEN** an invalid key or an implicit empty endpoint is supplied in normal or check mode
- **THEN** site and standalone role preflight refuse without publishing files or changing services.

### Requirement: REQ-AUDIT-WARP — Armored key publication

The implementation MUST publish the checksum-pinned armored repository key through a matching ASCII keyring suffix.

#### Scenario: Armored key publication boundary

- **WHEN** a fresh WARP package source is rendered
- **THEN** its signed-by path and checksum refer to the same armored key file.

### Requirement: REQ-AUDIT-DOCS — Accurate operator contracts

The implementation MUST describe per-instance AWG headers, qualified negotiated limits, explicit echo mode and research runtime evidence without unsupported diagnosis.

#### Scenario: Accurate operator contracts boundary

- **WHEN** an operator follows the current protocol notes
- **THEN** the notes do not promise a recursive resolver, aggregate bandwidth cap, per-peer headers or proven research data plane.
