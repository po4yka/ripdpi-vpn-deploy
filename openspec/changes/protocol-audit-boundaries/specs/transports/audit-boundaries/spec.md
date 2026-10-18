## Purpose

Keep accepted protocol identities and delivered credentials exact, reject
unsupported recipients, and protect bearer requests on every delivery outcome.

## ADDED Requirements

### Requirement: REQ-PAB-LOG — Protect the complete bearer virtual host

The subscription virtual host MUST use URI-free categorical logging for all
request outcomes, including unmatched paths and disabled delivery routes.

#### Scenario: A bearer request does not match a delivery route

- **WHEN** a synthetic bearer path has an invalid suffix or names a disabled route
- **THEN** the server refuses it without writing the token to access or error logs
- **AND** existing successful, rate-limited and failed-upstream outcomes remain safe

### Requirement: REQ-PAB-URL — Serve generated remote import targets

The share command MUST generate sing-box import and QR URLs that the existing
subscription frontend and backend serve, without changing token authority.

#### Scenario: A generated sing-box link is consumed

- **WHEN** a recipient follows the remote-profile URL from the generated page or QR
- **THEN** the local delivery stack serves the authorized payload at that URL
- **AND** expiry, revocation, rate limits and one-time bootstrap rules remain active

### Requirement: REQ-PAB-UUID — Reject VLESS authentication aliases

Input admission MUST reject distinct client UUID strings that map to the same
authentication identity in the pinned Xray engine before runtime mutation.

#### Scenario: Two device records alias after engine normalization

- **WHEN** UUID case or engine-normalized bytes produce one authentication key
- **THEN** validation refuses both records as an ambiguous configuration
- **AND** distinct authentication identities retain independent device revocation

### Requirement: REQ-PAB-AWG — Reserve all AWG server addresses

AWG input admission MUST reject every peer prefix that contains a server host
address from any configured instance, for both IPv4 and IPv6.

#### Scenario: A peer claims another instance server address

- **WHEN** a device or routed peer prefix contains another instance server address
- **THEN** semantic admission and device delivery refuse before publication
- **AND** nonconflicting multi-instance and routed-peer configurations remain valid

### Requirement: REQ-PAB-JSON — Preserve protocol credential bytes

Snell server and smoke templates and Trojan target templates MUST serialize
credential strings as JSON without changing their values.

#### Scenario: A schema-valid credential needs JSON escaping

- **WHEN** a synthetic credential includes quotes, backslashes or control escapes
- **THEN** parsed server, probe and emitted client documents preserve the exact input
- **AND** existing native authentication and research-only admission remain required

### Requirement: REQ-PAB-HOP — Refuse unsupported RIPDPI hopping artifacts

RIPDPI materialization MUST refuse Hysteria port hopping until its actual client
contract is qualified. It MUST NOT silently remove hopping from the profile.

#### Scenario: RIPDPI delivery selects a hopping-enabled Hysteria profile

- **WHEN** the effective Hysteria port range is nonempty
- **THEN** RIPDPI emission fails before artifact publication
- **AND** the supported official sing-box hopping path remains available

### Requirement: REQ-PAB-SAN — Match certificate SAN names exactly

Certificate preflight MUST use native certificate hostname matching with SAN
authority and reject wildcard names that do not cover the configured host.

#### Scenario: A wildcard parent differs at a domain separator

- **WHEN** a parseable certificate has a similar but different wildcard SAN parent
- **THEN** preflight refuses the certificate
- **AND** valid exact and single-label wildcard SANs pass the name check

### Requirement: REQ-PAB-EXTRAS — Retain every Hysteria host extension

RIPDPI materialization MUST retain Hysteria extension metadata by each emitted
outbound tag rather than only the first host.

#### Scenario: Two hosts emit Hysteria profiles

- **WHEN** a bundle contains Hysteria outbounds for multiple hosts
- **THEN** each outbound tag has its corresponding extension metadata
- **AND** one host cannot replace another host's version or obfuscation metadata

### Requirement: REQ-PAB-GATES — Retain the existing safety boundaries

The repair MUST preserve PQE HOLD, arm64 refusal, research/staging admission,
TLS verification, version pins, required checks and security scanning policy.

#### Scenario: The complete repair is reviewed and validated

- **WHEN** regression, security and complete CI checks evaluate the change
- **THEN** no skip, threshold reduction, CVE exception or credential bypass is added
- **AND** no live deployment, backend migration or automatic credential rewrite occurs
