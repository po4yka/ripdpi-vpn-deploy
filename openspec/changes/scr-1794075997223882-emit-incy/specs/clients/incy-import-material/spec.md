## Purpose

Convert one issued device's canonical client payload into INCY share links for P0 REALITY, P1 XHTTP and P2 Hysteria2, written only to a private file, complete for every field the payload requires and refusing what the links cannot carry.

## ADDED Requirements

### Requirement: REQ-INCY-LINKS-COMPLETE — One complete link per enabled endpoint

The implementation MUST emit exactly one share link for every enabled P0 REALITY, P1 XHTTP (including the alternate endpoint) and P2 Hysteria2 endpoint of the selected device. It MUST derive every field from the canonical client payload and carry every field that the payload requires for that path.

#### Scenario: Device with all three link paths enabled

- **WHEN** the operator runs `make emit-incy CLIENT=<device> OUTPUT=<new path>` for a device with P0, P1 primary and alternate, and Hysteria2 with Salamander and port hopping
- **THEN** the output file contains one `vless://` line per REALITY endpoint, one `vless://` line per XHTTP endpoint and one `hysteria2://` line, and each line equals the expected literal for the fixture

#### Scenario: Required fields per path

- **WHEN** the links are emitted
- **THEN** a P0 link carries `security=reality`, `type=tcp`, SNI, fingerprint, REALITY public key, short ID and flow
- **AND** a P1 link carries `security=tls`, `type=xhttp`, SNI, HTTP host, the full path and the mode
- **AND** a Hysteria2 link carries the full `<device>:<password>` auth in userinfo, SNI and, when configured, `obfs=salamander` with its password and the hopping port list and interval

#### Scenario: Components are encoded once

- **WHEN** an XHTTP path or a Hysteria2 password contains reserved URI characters
- **THEN** each component is percent-encoded exactly once and decodes back to the original value

### Requirement: REQ-INCY-LINKS-REFUSE — Refuse fields the links cannot carry

The implementation MUST fail without writing output when the payload contains a field that the INCY link formats cannot carry: an XHTTP mode other than `auto`, XHTTP pool tuning (`xmux`), Hysteria2 ECH, a Hysteria2 BBR resource profile, a P3 Snell outbound, any other outbound type or field, or a per-app or expiry option. It MUST NOT omit such a field silently.

#### Scenario: XHTTP stream-up profile

- **WHEN** the selected device's P1 profile uses mode `stream-up`
- **THEN** the command exits non-zero with a named refusal and no output file exists

### Requirement: REQ-INCY-LINKS-PRIVATE — Output stays private

The implementation MUST write links only to a new file created with owner-only permissions in an owner-only directory, MUST refuse an existing output path, and MUST NOT print link values, UUIDs, passwords or keys to stdout, stderr or logs.

#### Scenario: Existing output path

- **WHEN** `OUTPUT` names an existing file
- **THEN** the command exits non-zero, leaves the file unchanged and prints no credential material

#### Scenario: Successful run output

- **WHEN** the command succeeds
- **THEN** stdout reports only the output path and the count of links per protocol, and the file mode is `0600`

### Requirement: REQ-INCY-LINKS-READONLY — No fleet or delivery side effects

The implementation MUST NOT contact hosts, publishers or providers, and MUST NOT create, refresh or revoke device credentials. AmneziaWG material MUST stay in its existing private `.conf` delivery and MUST NOT appear in the link file.

#### Scenario: Device with AmneziaWG enabled

- **WHEN** the selected device also has an AmneziaWG peer
- **THEN** the link file contains no `awg://`, `amneziawg://` or `wg://` line and no AWG key material
