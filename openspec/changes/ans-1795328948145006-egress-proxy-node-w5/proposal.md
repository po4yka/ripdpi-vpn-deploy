# Change: Add a secretless egress proxy node for provider APIs

Task ID: `ANS-1795328948145006`

## Why

GitHub-hosted runners have changing public addresses, and the Vultr API key has an account-wide IP allowlist, so CI cannot call Vultr today. The operator's own rotating /32 in that allowlist is also a standing weakness. Earlier temporary Vultr-only CONNECT proxies on node-b and node-c proved the pattern but put operator traffic on VPN nodes. A dedicated node with a fixed address, no secrets and a CONNECT-only allowlist gives every provider API one stable source address that provider-side allowlists can name. Part of W5 of epic `EPC-1795327697650892`.

## What Changes

- New OpenTofu root `terraform/ops/egress-proxy` (Hetzner) with one small node and a retained primary IPv4 that survives recreation, encrypted remote state from the start (W3), and the shared cloud-init admin bootstrap.
- New Ansible role `egress-proxy`: a CONNECT-only forward proxy bound to the node's Tailnet address, allowlisting only the API hosts of Hetzner, Scaleway, UpCloud, Vultr, the OpenTofu state backend S3 host, Porkbun and Tailscale on port 443, with no TLS termination, a hardened systemd unit and nftables rules. The node holds no operator or provider credential.
- Tailnet grant: `tag:ci-tofu` (and optionally one operator device) to `tag:egress` on the proxy port only.
- Provider-side API allowlists: Vultr set to the egress address only and the workstation /32 removed (mandatory); UpCloud sub-account, Scaleway IAM condition and Porkbun key source IP set to the egress address where available (optional, per provider).
- A recorded proof that each OpenTofu provider and the state backend work through `HTTPS_PROXY`.
- Break-glass procedures for a down proxy, a lost VPS and a GitHub outage.

## Capabilities

### New Capabilities

- `network/provider-api-egress`: the fixed-address CONNECT proxy, its allowlist, its access path and the provider-side allowlists that depend on it.

### Modified Capabilities

- None.

## Impact

- Terraform: new root `terraform/ops/egress-proxy`, conftest policy coverage, `make tf-test` loop gains the root.
- Ansible: new role `ansible/roles/egress-proxy`, new playbook or `site.yml` group `egress`, `firewall` role input for the proxy port, `tailnet-management` tag `tag:egress`.
- Ops repository: inventory group, tfvars, Tailnet policy grant (W4 policy file).
- External (authorized live steps): Hetzner server and primary IP, Vultr API access control, optional allowlists at UpCloud, Scaleway and Porkbun.
