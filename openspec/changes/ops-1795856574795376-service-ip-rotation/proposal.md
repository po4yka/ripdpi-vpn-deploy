# Change: Rotate a node's client-facing IPv4 without replacing the server

Task ID: `OPS-1795856574795376`

## Why

Today the only way to give clients a new address is to replace the node (blue-green, warm spare or `fleet-rotate`). That needs a new VPS, new server keys and a reviewed device migration with separate SOPS authority. When only the client address is blocked and the provider network still works, the same server can keep its disk, keys, SSH and Tailnet identity and only change the address that devices connect to.

The public address also had two meanings: it was the client endpoint and the SSH, Tailnet and host-key identity. A client address change therefore broke management bindings.

## What Changes

- Every provider root gets `service_ipv4_generations` (at most two names). Each name attaches one movable provider IPv4 (Hetzner floating IP, UpCloud floating IP on the primary public interface, Vultr reserved IP, Scaleway routed flexible IP) to the existing server. New outputs `service_ipv4` (newest generation, else the primary IPv4) and `service_ipv4_addresses`. `server_ipv4` keeps its meaning: the host's primary IPv4.
- Inventory splits the address: `vpn_service_address` is the client endpoint, new `vpn_host_address` is the host identity, and `vpn_service_addresses` lists the attached generations. Inventory refuses state that lacks or contradicts the new outputs.
- The `baseline` role owns the guest `/32` of each service address and removes retired ones.
- Host identity consumers (fleet inspection host-key alias, Tailnet checks, vpnd inventory limits) read `vpn_host_address`. Client-path consumers (client payloads, AWG export, liveness target binding, device lifecycle and migration endpoints, burn check, reputation, ASN drift, warm spare, health check, probe matrix) read the service address.
- The secondary-IP plan policy denies only the honeypot floating IP without its opt-in.
- A runbook for the attach, move, retire cycle.

Breaking: existing Terraform state must be applied once (tfvars unchanged) to record the new outputs before `make inventory` renders again, and inventories must be rendered again so they carry `vpn_host_address`.

## Capabilities

### New Capabilities

- `operations/service-ip-rotation`: movable client IPv4 generations on an existing server and the split between client and host addresses.

### Modified Capabilities

- None.

## Impact

- Terraform: all four provider roots, the inert exception root outputs, `terraform/policy/secondary_ip.rego`.
- Scripts: `render-inventory.sh`, `fleet_inspection.py` and its client-path consumers, the data-plane scripts listed above.
- Ansible: `baseline` service address tasks, Tailnet checks, egress host context, subscription field-report addresses.
- vpnd: inventory limit address.
- Docs: `docs/how-to/rotate-service-ip.md` and folder notes.
