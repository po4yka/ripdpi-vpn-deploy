## Purpose

Admit the management SSH route to a cloud liveness sentinel only when the reached host is provably the managed server recorded in Terraform state.

## ADDED Requirements

### Requirement: REQ-SENTINEL-TRANSPORT-PUBLIC — The state address stays an admitted route

The scope check MUST admit a sentinel whose `ssh_transport_host` is the state-derived public IPv4 and whose `ssh_host_key_alias` is that address, or `[address]:port` for a non-22 port.

#### Scenario: Public route

- **WHEN** the sentinel record names the state-derived public address and the pinned key matches the guest probe
- **THEN** the scope check returns the sentinel identity

### Requirement: REQ-SENTINEL-TRANSPORT-TAILNET — A Tailnet route must prove the same pinned key

The scope check MUST admit a Tailnet address in `100.64.0.0/10` or `fd7a:115c:a1e0::/48` only with the sentinel's inventory alias as `ssh_host_key_alias`, and only when the key pinned for that alias equals the key pinned for the state-derived public address. The SSH connection MUST use the Tailnet address and the inventory alias.

#### Scenario: Tailnet route bound to the state address

- **WHEN** the pin file lists the inventory alias and the public address on one key, and the record names a Tailnet address with the inventory alias
- **THEN** the probe connects to the Tailnet address with that alias and the scope check returns the sentinel identity

#### Scenario: Alias pinned to another key

- **WHEN** the key pinned for the inventory alias differs from the key pinned for the public address
- **THEN** the scope check refuses before the probe

#### Scenario: Public alias on a Tailnet route

- **WHEN** a Tailnet record uses the public address as its host key alias
- **THEN** the scope check refuses

### Requirement: REQ-SENTINEL-TRANSPORT-REFUSE — Other transports are refused

The scope check MUST refuse a sentinel transport that is neither the state-derived public address nor a Tailnet address, including a missing transport, a loopback address and an unrelated public address.

#### Scenario: Unrelated address

- **WHEN** the record names a public address that is not the sentinel's state address
- **THEN** the scope check refuses with `cloud-sentinel-transport-refused`
