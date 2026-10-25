# terraform/providers/scaleway — independent provider root

## Design decisions

REALITY alternate listeners are opt-in: examples and the legacy listener set
only declare the primary port. An enabled `xray_fallback_port` also requires an
explicit matching `public_listeners` entry; runtime/provider parity stays strict.

The shared `nat_source_port_range` output is empty here: this root does not
require forwarded TCP/UDP source-port remapping for stateless return filtering.
Keep the same output names as every provider root and the inert exception root.

**Reserved routed IPs are explicit resources** — the primary IPv4, optional IPv6, and optional honeypot IPv4 use `scaleway_instance_ip` and attach through `ip_ids`; inventory never depends on a transient dynamic address.

**Provider-edge policy is typed and fail-closed** — one stateful security group default-drops inbound traffic and renders only CIDR-scoped SSH plus the canonical `public_listeners` contract for IPv4 and IPv6.

**Credentials stay in the environment** — `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID` are consumed by the provider and never enter tfvars, state inputs, outputs, or cloud-init.

**Inventory stays provider-neutral** — Scaleway exports the canonical output
names, including `ssh_port`, so `render-inventory.sh` needs no provider branch;
only a provider with different output keys or a live guest-convergence
requirement may add one.

**Port inputs are integers** — singleton listeners and legacy XHTTP ports reject
fractions before provider calls. Legacy collision tests clear explicit listeners
so they exercise the effective legacy contract.

## What's done well

- The output schema matches every existing provider root, including `public_listeners`, `zone`, and nullable `honeypot_ipv4`.
- Mock-provider tests pin cloud-init wiring, routed IP allocation, default-deny ingress, listener parity, and SSH CIDR restrictions.
- The Instance keeps Terraform `prevent_destroy`; the normal destroy wrapper uses a temporary lifecycle override.


The root disk is explicit Block Storage 5K (`sbs_volume`, 5000 IOPS), defaults to 20 GB through `root_size_gb`, and is deleted with its instance. Include the disk and the separately billed IPv4 in the cost plan. Changing an existing root type or size requires a reviewed replacement or resize plan.

## Pitfalls

- **Provider refreshes stay within reviewed 2.x resources** — keep the baseline
  and generated Linux amd64/arm64 and Darwin arm64 lock checksums together. The
  Instance root remains project-scoped; provider documentation for
  organization-scoped resources does not add an organization input here.

- **Administrator identity is creation-time state** — username/key edits hit
  replacement guards and `prevent_destroy`. First adoption compares retained
  cloud-init identity, normalizing surrounding key whitespace while checking the
  complete key list, so mismatched inputs fail during planning. Helper and
  build-label updates remain ignored; these checks do not observe guest drift.

- **Example listener completeness** — the explicit staging/prod contracts include
  HTTP/80 for the nginx public-site redirect; deploy fails closed without it.
- Scaleway IPv6 address resources expose a prefix; read the full attached address from `scaleway_instance_server.public_ips`, as `server_ipv6` does.
- Instance type and Marketplace image availability can vary by zone; keep the approved allowlists narrow and verify availability before changing examples.
- A security-group UDP rule proves declared policy, not end-to-end UDP delivery. Confirm Hysteria2 and AmneziaWG from the filtered client path after deployment.
- Provider-managed snapshots are intentionally not exposed by this root; the Ansible restic+age backup role remains the only configured backup path.
