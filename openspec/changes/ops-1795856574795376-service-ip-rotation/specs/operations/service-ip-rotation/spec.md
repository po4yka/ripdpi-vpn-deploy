## Purpose

Change the IPv4 address that clients use on an existing node without replacing the server, its keys or its management identity.

## ADDED Requirements

### Requirement: REQ-SIP-GENERATIONS — Movable client address generations

Every provider root MUST accept an ordered `service_ipv4_generations` list of at most two unique names and MUST attach one provider-movable IPv4 to the existing server for each name. The `service_ipv4` output MUST be the address of the last name, or the primary IPv4 when the list is empty. `server_ipv4` MUST stay the primary IPv4.

#### Scenario: no generations

- **WHEN** the list is empty
- **THEN** no movable address is allocated and `service_ipv4` equals `server_ipv4`

#### Scenario: two generations during a move

- **WHEN** the list holds an old and a new name
- **THEN** both addresses are attached to the same server, `service_ipv4` is the new address and `service_ipv4_addresses` lists both in order

#### Scenario: invalid list

- **WHEN** the list holds more than two names, a duplicate or a malformed name
- **THEN** planning fails on the variable

### Requirement: REQ-SIP-SPLIT — Client and host addresses stay separate

Inventory MUST publish the client endpoint as `vpn_service_address` and the primary IPv4 as `vpn_host_address`. SSH host-key aliases, Tailnet bindings and inventory limits MUST use the host address. Client payloads, liveness target bindings, device endpoints and reachability checks MUST use the service address.

#### Scenario: rotated node

- **WHEN** a node has an attached service generation
- **THEN** its host-key alias and Tailnet binding still name the primary IPv4 and its client payloads name the service address

#### Scenario: inconsistent state

- **WHEN** Terraform state lacks the service outputs or `service_ipv4` is not the newest listed address
- **THEN** inventory rendering refuses and keeps the previous inventory

### Requirement: REQ-SIP-GUEST — Guest ownership of service addresses

The `baseline` role MUST add every listed service address as a `/32` on the default IPv4 interface, MUST refuse convergence when an address is absent from the guest afterwards, and MUST remove only the `/32` of a retired address.

#### Scenario: retire the older generation

- **WHEN** a name is removed from the list and the node converges
- **THEN** its guest `/32` and its unit are removed and the remaining address stays

### Requirement: REQ-SIP-POLICY — Plan policy distinguishes service addresses

The secondary-IP plan policy MUST keep refusing a honeypot address without `additional_public_ip` and MUST NOT refuse a service address.

#### Scenario: service floating IP without honeypot opt-in

- **WHEN** a plan creates `hcloud_floating_ip.service_ipv4["<name>"]` and `additional_public_ip` is false
- **THEN** the policy reports no violation
