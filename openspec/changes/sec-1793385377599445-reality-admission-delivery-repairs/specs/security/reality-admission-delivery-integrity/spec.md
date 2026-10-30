## Purpose

Keep P0 REALITY nodes indistinguishable under ClientHello replay and keep production Xray builds within reviewed releases. Watchdog and smoke probes, share URIs, bundle topology and XHTTP paths must describe the recipient path that devices actually use.

## ADDED Requirements

### Requirement: REQ-REALITY-REPLAY-WINDOW — Bound the REALITY client time window

Every rendered REALITY inbound MUST set `realitySettings.maxTimeDiff` to a positive millisecond value, 90000 by default. Rendering MUST refuse a zero, negative or non-integer value.

#### Scenario: Default replay window

- **WHEN** the xray role renders primary, fallback or cohort REALITY inbounds with default inputs
- **THEN** each inbound carries `maxTimeDiff: 90000`.

#### Scenario: Disabled replay window refused

- **WHEN** an operator sets the replay window to zero
- **THEN** the role refuses before rendering, and the accepted configuration is unchanged.

### Requirement: REQ-XRAY-PRODUCTION-PIN — Admit only reviewed production Xray builds

Xray runtime acquisition for a production environment MUST refuse any `xray.version` outside the reviewed production allowlist, before any download or build. The allowlist MUST contain the release tracker's repository pin. Non-production environments MUST keep their existing staging evaluation path.

#### Scenario: Unreviewed production pin

- **WHEN** `env` is `prod` and `xray.version` names a tag outside the allowlist, including an upstream prerelease without a suffix
- **THEN** acquisition fails before download and publishes no runtime.

#### Scenario: Staging evaluation

- **WHEN** `env` is `staging` and `xray.version` names an unreviewed tag with valid checksums
- **THEN** admission does not refuse on allowlist membership.

#### Scenario: Allowlist drift

- **WHEN** the release tracker's repository pin is absent from the allowlist
- **THEN** the repository test suite fails.

### Requirement: REQ-PROBE-FINGERPRINT — Probe with the recipient fingerprint

The watchdog REALITY and XHTTP probe clients and the smoke REALITY client MUST present the configured `xray_utls_fingerprint` that recipient profiles carry, defaulting to `chrome`.

#### Scenario: Operator fingerprint override

- **WHEN** an operator sets `xray_utls_fingerprint: firefox`
- **THEN** the rendered watchdog REALITY and XHTTP clients and the smoke client all send `firefox`.

### Requirement: REQ-SHARE-URI — Emit complete read-only share URIs

`emit-qr.sh --type uri` MUST NOT enroll or modify a device. It MUST encode exactly one complete VLESS+REALITY URI for an existing device, derived from the canonical client materializer: resolved server address and port, SNI, public key, short ID, flow and uTLS fingerprint. It MUST refuse a device without credentials, and it MUST refuse a selection that yields zero or several REALITY endpoints, before rendering a QR code.

#### Scenario: Existing device

- **WHEN** an operator requests a URI QR code for an existing device on one REALITY endpoint
- **THEN** the QR code payload is a single `vless://` URI with no placeholder, and the encrypted secrets are byte-identical.

#### Scenario: Ambiguous endpoint selection

- **WHEN** the selection resolves a primary and a fallback REALITY endpoint
- **THEN** emission refuses, names the HOSTS/COHORTS selection, and writes no QR code.

### Requirement: REQ-BUNDLE-TOPOLOGY-TRUTH — Declare split-hop egress only for routed family traffic

RIPDPI bundle emission MUST NOT set `topology.split_hop_egress=true` for family transport outbounds whose egress stays on the entry host, including hosts where the split-hop research responder is enabled.

#### Scenario: Research responder on a family host

- **WHEN** a selected host enables `enable_split_hop_ingress`
- **THEN** the emitted bundle declares `split_hop_egress: false`.

### Requirement: REQ-XHTTP-PATH-SECRECY — Keep XHTTP paths unguessable

Bootstrap MUST generate XHTTP paths with at least 128 random bits. Transport admission MUST refuse an absent `xray.xhttp_path` when XHTTP is enabled, and it MUST refuse the published `/app-sync` value. Existing explicit paths that pass syntax validation MUST remain admissible.

#### Scenario: Published default path

- **WHEN** secrets set `xray.xhttp_path: /app-sync` or omit it while XHTTP is enabled
- **THEN** admission refuses before host changes or client emission.

#### Scenario: Existing explicit short path

- **WHEN** secrets carry a previously generated eight-hex-digit path
- **THEN** admission accepts it, and rotation remains an operator decision.
