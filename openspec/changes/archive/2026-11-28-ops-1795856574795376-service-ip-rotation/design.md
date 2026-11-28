## Context

`server_ipv4` was both the client endpoint and the host identity. The deploy controller, fleet inspection, Tailnet bootstrap, SSH recovery and vpnd bind the host identity; client payloads, liveness and device tooling bind the client endpoint. The honeypot role already owns a provider secondary `/32` inside the guest on Hetzner.

## Goals / Non-Goals

- Goal: give an existing node a new client IPv4 with an overlap period, then retire the old one, using only plan, apply, inventory, deploy and device refresh.
- Goal: keep SSH, Tailnet, host-key and recovery bindings unchanged across a rotation.
- Non-goal: a new ASN or prefix. A blocked network still needs node replacement.
- Non-goal: automatic DNS changes or automatic device moves.

## Decisions

- An ordered generation list, not a single toggle: two names give the overlap period in which old and new devices both connect; the last name is the endpoint. Rejected: replacing the primary IP in place (Hetzner primary IPs need a power-off, Vultr and UpCloud cannot change the main address, and there is no overlap).
- `server_ipv4` keeps its meaning and a new `service_ipv4` output carries the endpoint, so the many SSH consumers of `server_ipv4` and existing Tailnet or recovery bindings stay valid. Rejected: redefining `server_ipv4`, which would break every recorded binding.
- One uniform guest step for all providers: an exact `/32` on the default interface, owned by a oneshot unit, reusing the honeypot role's exact-address removal helper. Rejected: provider-specific guest paths, which cannot be verified offline.
- `fleet_inspection.select_hosts` returns both `address` (host) and `service` (client); each consumer picks the one it binds.

## Contracts and ownership

- Terraform roots own allocation and attachment. Inventory owns the address split. `baseline` owns guest `/32`s. One writer.

## Risks / Trade-offs

- Same provider network: the new address often shares the blocked prefix or ASN -> the runbook says when to use blue-green instead.
- Provider-edge behaviour (attach timing, firewall coverage of the new address, Vultr guest routing) is not provable with mock providers -> deploy refuses when the address does not reach the guest; live acceptance is a separate staging step.
- Existing state lacks the new outputs -> inventory refuses with a message to apply once.

## Migration Plan

Apply each provider root once with unchanged tfvars, then render the inventory again. Rollback reverts the change; nodes without generations behave as before.
