## Purpose

Define continuous per-protocol authenticated probe metrics and privacy-preserving aggregate peer exporters for AmneziaWG and Hysteria2.

## ADDED Requirements

### Requirement: REQ-PROBE-CONTINUOUS — Continuous probe metric per protocol

For each of vless-reality, xhttp, hysteria2 and amneziawg the system MUST export a probe success gauge and a latency histogram with only the labels protocol, node and vantage, refreshed at the configured interval, and MUST mark a stale series as unknown rather than healthy.

#### Scenario: continuous probe metric per protocol

- **WHEN** a probe for one protocol is stopped for longer than twice the interval
- **THEN** the metric reports unknown or absent and the staleness alert fires; the other three protocols are unaffected

### Requirement: REQ-PROBE-AUTH — Probe authenticates as a real client

Each probe MUST complete the protocol handshake with the probe credential and fetch a payload, so a REALITY, XHTTP, QUIC or WireGuard handshake failure counts as failure.

#### Scenario: probe authenticates as a real client

- **WHEN** the node denies the probe credential
- **THEN** the probe reports failure and the metric records the failing protocol only

### Requirement: REQ-AWG-AGGREGATE — AmneziaWG fresh handshake count

The AmneziaWG exporter MUST expose only the number of peers whose latest handshake is within the configured window and total peer count, MUST NOT expose a peer key, address or per-peer series, and MUST run without printing peer keys to logs.

#### Scenario: amneziawg fresh handshake count

- **WHEN** the exporter runs against a fixture with 3 peers, 2 fresh
- **THEN** the output has fresh 2 and total 3 and contains none of the fixture peer keys or addresses

### Requirement: REQ-HY2-AGGREGATE — Hysteria2 aggregate traffic

The Hysteria2 exporter MUST read the traffic API and expose only aggregate bytes and online-connection counts, MUST NOT expose a per-user series, and MUST report exporter failure as a metric.

#### Scenario: hysteria2 aggregate traffic

- **WHEN** the traffic API fixture lists 3 users with traffic
- **THEN** the output has summed bytes and a count and no user identifier; with the API down the failure metric is 1

### Requirement: REQ-PROBE-ORIGIN — Probe and report series only from their owner

The relay MUST read the sender identity only from a label that no sender can put in its payload, MUST accept `vpn_protocol_probe_*` only from the collector's own agent and `vpn_field_report_*` only from configured subscription hosts, and MUST store every other family under the sender's certificate identity.

#### Scenario: an enrolled node spoofs the collector

- **WHEN** an enrolled node pushes `vpn_protocol_probe_success` with a payload `ingress_node` or `node` naming the collector or a probed node
- **THEN** the relay drops the series, and the same spoof on `vpn_awg_*` is stored only under the sender's identity

### Requirement: REQ-PROBE-MANIFEST — Metrics are registered

Every new metric MUST be listed in the metric manifest and MUST pass the observability manifest tests.

#### Scenario: metrics are registered

- **WHEN** a metric is emitted but not in the manifest
- **THEN** the manifest test fails
