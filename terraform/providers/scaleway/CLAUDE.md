# terraform/providers/scaleway — independent provider root

## Design decisions

**Reserved routed IPs are explicit resources** — the primary IPv4, optional IPv6, and optional honeypot IPv4 use `scaleway_instance_ip` and attach through `ip_ids`; inventory never depends on a transient dynamic address.

**Provider-edge policy is typed and fail-closed** — one stateful security group default-drops inbound traffic and renders only CIDR-scoped SSH plus the canonical `public_listeners` contract for IPv4 and IPv6.

**Credentials stay in the environment** — `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID` are consumed by the provider and never enter tfvars, state inputs, outputs, or cloud-init.

**Inventory stays provider-neutral** — Scaleway exports the canonical output
names, including `ssh_port`, so `render-inventory.sh` needs no provider branch;
only a provider with different output keys or a live guest-convergence
requirement may add one.

## What's done well

- The output schema matches every existing provider root, including `public_listeners`, `zone`, and nullable `honeypot_ipv4`.
- Mock-provider tests pin cloud-init wiring, routed IP allocation, default-deny ingress, listener parity, and SSH CIDR restrictions.
- The Instance keeps Terraform `prevent_destroy`; the normal destroy wrapper uses a temporary lifecycle override.

## Pitfalls

- Scaleway IPv6 address resources expose a prefix; read the full attached address from `scaleway_instance_server.public_ips`, as `server_ipv6` does.
- Instance type and Marketplace image availability can vary by zone; keep the approved allowlists narrow and verify availability before changing examples.
- A security-group UDP rule proves declared policy, not end-to-end UDP delivery. Confirm Hysteria2 and AmneziaWG from the filtered client path after deployment.
- Provider-managed snapshots are intentionally not exposed by this root; the Ansible restic+age backup role remains the only configured backup path.
