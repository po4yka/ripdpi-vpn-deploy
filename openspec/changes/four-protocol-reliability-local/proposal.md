# Change: Deliver local four-protocol reliability

Task ID: `EPC-1792155716043904`

## Why

The owner selected complete local implementation without external staging soak,
recipient devices or production operations. This is the local successor to
`EPC-1791618453830051`; its former external acceptance scope is superseded,
not represented as passed. Existing taskctl evidence-transfer gates remain intact.

## What Changes

- Deliver isolated authenticated REALITY, direct XHTTP, Hysteria2 and AmneziaWG traffic, rejection, lifecycle and recovery behavior.
- Deliver authoritative device and consumed-payload identity, interface-correct dual-stack forwarding, selectable XHTTP endpoints and typed tuning.
- Deliver secure topology-aware probes, finite target validation and monitoring, eligible local runtime/parser adoption and compensation.
- BREAKING: RIPDPI-format XHTTP transports carry explicit mode and optional bounded XMUX settings; adapters require exact material parity.
- Require real local Linux/systemd/TUN engines and complete source checks. Exclude external staging, physical/emulated recipients and production promotion from completion.

## Capabilities

### New Capabilities

- `transport/reliable-four-protocol-portfolio`: complete local protocol and recovery delivery.
- `transport/native-acceptance`: complete native traffic and lifecycle acceptance.
- `transports/awg-forwarding-dualstack`, `transports/awg-source-runtime`: typed device paths and real local source candidates.
- `transports/hysteria-stable-runtime`, `transports/hysteria-ech-profiles`: bounded resources, trusted ECH and stable local adoption.
- `transports/xhttp-alternate-and-tuning`, `transports/reality-target-validation`: exact endpoint selection, measured tuning and bounded hygiene.
- `clients/stable-parser-adoption`, `clients/payload-identity`: actual parser adoption and consumed-input drift detection.
- `operations/topology-authenticated-probes`: effective target sets and secure authenticated observation.

### Modified Capabilities

- `clients/config-registry`: bind issuance and refresh to the material actually consumed.

## Impact

Ansible runtime templates, canonical Python materialization and liveness,
secrets contracts, operator scripts, native fixtures and the Make/CI surface.
The successor retains the positive requirements of the prior linked changes;
no toolchain gate, terminal-history rule or runtime security boundary is relaxed.
