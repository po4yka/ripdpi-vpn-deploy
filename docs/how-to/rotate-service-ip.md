# Rotate a node's client IPv4 without replacing the server

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-11-28

## Purpose and scope

Move client traffic of one existing node to a new public IPv4 address. The server, its disk, its SSH host identity, its Tailnet identity and every device credential stay the same. Only the address that devices connect to changes.

Each provider root has a `service_ipv4_generations` list. Each name in the list allocates one movable provider address and attaches it to the server: a Hetzner floating IP, an UpCloud floating IP on the primary public interface, a Vultr reserved IP, or a Scaleway routed flexible IP. The last name is the client endpoint (`service_ipv4` output, inventory `vpn_service_address`). An earlier name stays attached while devices move. The list holds at most two names. An empty list keeps the primary IPv4 as the client endpoint.

The primary IPv4 (`server_ipv4` output, inventory `vpn_host_address`) never moves. SSH, Tailnet bindings, host-key aliases, recovery and egress use it. The `baseline` role adds each service address as a `/32` on the default interface and removes the `/32` of a retired name. Every listener binds the wildcard address, so no service restarts.

Use this procedure when the client address is blocked but the provider network still works. A new address from the same provider usually has the same ASN and often the same prefix. When the block covers the prefix or the ASN, replace the node in another network with [blue-green](rollback.md#level-3--blue-green-vps-replacement) or `make fleet-rotate`.

## Preconditions

- The provider root was applied after this feature landed, so its state records the `service_ipv4` and `service_ipv4_addresses` outputs. `make inventory` refuses a state without them; one `make plan` and `make apply` of the unchanged tfvars records them.
- Management access does not depend on the client address: either the [Tailnet transport](tailnet-management.md) or public SSH on the primary IPv4.
- Every DNS name that must follow the client address is known: the `nginx_xhttp.server_name` record and any public site or subscription origin that devices resolve. Deploy waits until the XHTTP name resolves to the new client address.
- Each device has a subscription URL whose origin is a DNS name that you can point at the new client address. A bare-IP origin keeps devices on the blocked address: on the first rotation the old client address is the primary IPv4.
- Disposable onboarding, recovery promotion and cloud promotion bind the target to the server's provider-listed primary IPv4. Run them only while the node has no service generations.

## Authorization

`make plan`, `make apply`, `make dry-run`, `make deploy`, `make verify`, `make burn-check` and `make device-lifecycle` act on real infrastructure and need an explicit operator request for this node. A new address can add a provider charge. Review every plan: the only acceptable changes are the creation or deletion of service address resources (and, on Scaleway, the in-place `ip_ids` update of the server). Stop at any server replacement.

## 1. Attach the new address

In the node's private tfvars, append one new name. Names are 1-31 lowercase letters, digits or hyphens; use a new name for every rotation so the provider allocates a new address.

```hcl
service_ipv4_generations = ["g1", "g2"]
```

```bash
make PROVIDER=<provider> ENV=<env> plan
make PROVIDER=<provider> ENV=<env> apply
make PROVIDER=<provider> ENV=<env> inventory
```

The rendered host line now has `vpn_service_address=<new>`, the unchanged `vpn_host_address=<primary>` and `vpn_service_addresses='[<old>,<new>]'`. For the first rotation of a node the old client address is the primary IPv4, and the list has one name.

## 2. Move DNS and converge the guest

Point each DNS name from the preconditions to the new client address. For records that the Vultr root manages, change `managed_dns_records` and apply that root. Then converge the node:

```bash
make PROVIDER=<provider> ENV=<env> dry-run ANSIBLE_LIMIT=<alias>
make PROVIDER=<provider> ENV=<env> deploy ANSIBLE_LIMIT=<alias>
```

The baseline role refuses to continue when a provider address does not reach the guest interface.

## 3. Verify the new address

```bash
make PROVIDER=<provider> ENV=<env> verify ANSIBLE_LIMIT=<alias>
make PROVIDER=<provider> ENV=<env> burn-check
make PROVIDER=<provider> ENV=<env> check-ip-reputation
```

Both checks now use the new client address. Add `--udp-probe` to a manual burn check when Hysteria2 is enabled.

## 4. Move every device

Refresh each device through its unchanged subscription URL with [the device lifecycle](device-lifecycle.md) `refresh` action. The refresh publishes a payload with the new endpoint and requires authenticated traffic from the device path. A refresh does not change any device credential. Keep the old address attached until every device has its evidence.

## 5. Retire the old address

Remove the old name from the list, keeping the new one:

```hcl
service_ipv4_generations = ["g2"]
```

```bash
make PROVIDER=<provider> ENV=<env> plan
make PROVIDER=<provider> ENV=<env> apply
make PROVIDER=<provider> ENV=<env> inventory
make PROVIDER=<provider> ENV=<env> deploy ANSIBLE_LIMIT=<alias>
```

The plan must delete only the old address resource. The deploy stops and removes the old guest `/32` unit. To return every client to the primary IPv4, set an empty list and repeat steps 2 to 5 in the same order: refresh devices before you remove the last name.

## Verification

- `make inventory` shows the expected `vpn_service_address` and `vpn_service_addresses` values.
- `make verify` passes for the alias, and `make burn-check` reaches the new address.
- Every device refresh in step 4 completed with authenticated traffic.

Mock-provider Terraform tests, inventory tests and Molecule prove the plan shape and the guest `/32` lifecycle only. They do not prove provider attach timing, provider-edge firewall coverage of the new address or delivery from filtered networks.

## Rollback

Before step 5, put the old name back at the end of the list (`["g2", "g1"]`), apply, render the inventory, move DNS back, deploy and refresh the devices. After step 5 the provider has released the old address and you cannot get it back; continue with a new name instead.

## Evidence to record

Record the provider, environment, alias, generation names, plan summary (resource counts only), deploy and verify results, and the number of refreshed devices. Do not record the addresses in tracked files or task notes.
