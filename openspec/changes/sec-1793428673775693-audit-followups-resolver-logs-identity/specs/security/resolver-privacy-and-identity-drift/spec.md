## Purpose

Keep recipient destination names and visitor identity off the hosting network and the node's logs, and watch the borrowed identities the node depends on.

## ADDED Requirements

### Requirement: REQ-RPI-ENCRYPTED-RESOLVER — Recipient names resolve through the loopback DoH forwarder

The built normalizer topology MUST list `127.0.0.2` as its only nameserver unless `vpn.enable_dns_morph_bridge` is true, and the direct gateway MUST answer that address over DNS-over-HTTPS only, with the kernel policy admitting its replies and only the direct gateway unit carrying `CAP_NET_BIND_SERVICE`.

#### Scenario: Default profile

- **WHEN** the topology is built without DNS-Morph
- **THEN** the normalizer resolver is `["127.0.0.2"]`; the direct gateway renders a `dokodemo-door` inbound on `127.0.0.2:53` (TCP and UDP) routed to a `dns` outbound with `nonIPQuery: reject` and only `https+local://` DNS servers; the kernel policy admits the gateway's port-53 replies from `127.0.0.2` toward `127.0.0.1` before the `0.0.0.0/8` deny set; the WARP gateway renders neither forwarder nor capability.

#### Scenario: Frontend resolver

- **WHEN** the Xray frontend is rendered outside cascade and DNS-Morph profiles
- **THEN** its DNS servers are `["127.0.0.2"]`.

#### Scenario: DNS-Morph profile

- **WHEN** `vpn.enable_dns_morph_bridge` is true
- **THEN** the resolver keeps the numeric upstream pair, no forwarder inbound or reply rule is rendered, and the direct gateway keeps an empty capability set.

#### Scenario: WARP namespace resolver

- **WHEN** the vendor namespace resolver is rendered from a `127.0.0.2` topology
- **THEN** it lists the numeric upstream pair, because no forwarder is reachable inside the namespace.

### Requirement: REQ-RPI-ADDRESS-FREE-LOGS — Decoy access logs keep no client address or user agent

The nginx-xhttp and reality-self-steal vhosts MUST define a `log_format` without `$remote_addr` or `$http_user_agent` that keeps `$status` as the ninth field, and every enabled `access_log` directive MUST use it.

#### Scenario: Primary and fallback vhosts

- **WHEN** the nginx-xhttp site is rendered with or without the fallback listener
- **THEN** every `access_log` that is not `off` ends with `vpn_public;` and the format carries no client address or user agent.

### Requirement: REQ-RPI-TARGET-DRIFT — The watchdog detects REALITY target drift

The watchdog environment MUST carry `XRAY_REALITY_TARGET` and `XRAY_REALITY_SNI` when REALITY is enabled and empty values otherwise. The handshake probe MUST exit 0 only for a trusted TLS 1.3 handshake that negotiates ALPN `h2` for the first server name, and the watchdog MUST record `reality_target_drift` when it fails for a non-loopback target.

#### Scenario: Target negotiates h2

- **WHEN** the probe reaches a trusted TLS 1.3 server offering `h2`
- **THEN** it exits 0.

#### Scenario: Target lost h2 or trust

- **WHEN** the server offers only `http/1.1` or presents an untrusted chain
- **THEN** the probe exits non-zero.

### Requirement: REQ-RPI-MEASURED-WIREGUARD-SHAPE — Production refuses an unmeasured WireGuard-shaped instance

The AmneziaWG role MUST refuse convergence on a host whose inventory `env` is `prod` when an instance has `S1 = S2 = 0` and `H1..H4 = 1,2,3,4` and `awg_wireguard_shaped_measurement` is empty or blank.

#### Scenario: Unmeasured production instance

- **WHEN** `env` is `prod`, an instance is WireGuard-shaped and the measurement variable is empty
- **THEN** the guard fails before any mutation and names the instance.

#### Scenario: Measured, staging or padded instance

- **WHEN** the measurement variable is set, or `env` is not `prod`, or the instance has nonzero `S1`/`S2` or non-default headers
- **THEN** the guard passes.

### Requirement: REQ-RPI-DUAL-STACK-REALITY — REALITY inbounds listen dual-stack

Every rendered REALITY inbound MUST listen on `::`.

#### Scenario: Rendered frontend

- **WHEN** the Xray frontend is rendered
- **THEN** each `vless-reality*` inbound has `"listen": "::"`.
