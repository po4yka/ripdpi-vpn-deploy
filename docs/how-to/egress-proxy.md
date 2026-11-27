# Converge the egress proxy node

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-11-27

## Purpose and scope

The egress node is one non-VPN host that runs a CONNECT-only squid proxy for provider API calls (the `egress-proxy` role). It listens only on its Tailnet IPv4 address, port 3128, and holds no secrets. This page shows how to converge it with `ansible/playbooks/egress-proxy.yml`. It runs `baseline`, `firewall`, `tailnet-management` and `egress-proxy`, and no VPN role.

## Inputs

- A rendered inventory with one host in the group `egress`, already enrolled in the Tailnet with `tag:egress` through the bootstrap-tailnet command. The playbook verifies the tag and fails closed without it.
- `egress_proxy_state_host`, the S3 host of the OpenTofu state backend (path-style), for example `s3.fr-par.scw.cloud`. The role refuses an empty value or an IP address.
- The usual `allowed_ssh_cidrs`, `vpn_service_address` and `tailnet_management.approved_sources` inventory values.

The Tailnet grants already exist: `tag:ci-tofu` reaches `tag:egress` on 3128 and `tag:ci-deploy` reaches it on 22. The playbook reads the listen address from the node (`tailscale status --json`), so no address input is needed.

## First enrollment

Enroll the node through the canonical path before the first converge: `make wait`, `make install-ssh-recovery`, `make bootstrap-tailnet`, then `make migrate-ssh-ownership`, as in [tailnet-management.md](tailnet-management.md#bootstrap-one-node). The three scripts accept the inventory section `egress` with the provider `egress-proxy`, as a production node only. A VPN provider with `egress`, or `egress-proxy` with another section, is refused. A `ci-staging-*` environment, a `cleanup_manifest` and a `build_environment` other than `prod` are refused for it.

The inventory is hand-written because no renderer emits the `egress` group. Keep the entry in its own inventory file in the ops repository, never in the generated `generated.ini`, and never list the host under `[observability:children]`; the inspection parser refuses that. Use documentation addresses only in examples, and take the real values from the `terraform/ops/egress-proxy` outputs:

```ini
[egress]
egress-proxy-1 ansible_host=203.0.113.20 ansible_port=22 ansible_user=<admin_user output> ansible_ssh_private_key_file=<absolute path of the admin key> provider=egress-proxy env=prod vpn_build_environment='"prod"'
```

`ansible_host` is the `server_ipv4` output, `ansible_port` the `ssh_port` output, and the host alias the `server_hostname` output. `vpn_build_environment` is a JSON string in shell quotes and must match `/etc/vpn-build-id` on the node. The environment variable `SSH_RECOVERY_INVENTORY_SECTION` and the config field `inventory_section` are both `egress`.

The `bootstrap-tailnet` config for this node uses these fields:

| Field | Value |
|---|---|
| `inventory_section` | `egress` |
| `provider` | `egress-proxy` |
| `environment`, `build_environment` | `prod` and `prod` |
| `cleanup_manifest` | JSON `null` |
| `inventory_alias`, `public_address`, `ssh_port` | The host alias, `server_ipv4` and `ssh_port` of the inventory entry |

The other fields follow the table in [tailnet-management.md](tailnet-management.md#bootstrap-one-node). The scripts do not choose or verify the Tailnet tag. Create the one-node enrollment key with `tag:egress` as its only tag. Before `make migrate-ssh-ownership`, confirm in the Tailscale admin console that the node's tags are exactly `tag:egress`. The converge playbook then fails closed, before any role runs, unless the node's tags are exactly `['tag:egress']`. Production bootstrap reads no Terraform state: the server binding is the pinned host key, the `server_ipv4` match against the inventory address and the `/etc/vpn-build-id` check. All three scripts also read the host's own `provider`, `env` and `vpn_build_environment`: section `egress` needs `egress-proxy`, `prod` and `"prod"`, and any other section refuses provider `egress-proxy`.

Open item (W7): CI runners that reach `tag:egress` on port 22 need Tailnet source addresses that the exact `approved_sources` firewall admits. Until that is resolved, only the operator controller sources in `approved_sources` can reach the node.

## Run

```bash
ansible-playbook ansible/playbooks/egress-proxy.yml -i inventory/<env>.yml --limit <egress-host> -e egress_proxy_state_host=<state S3 host>
```

There is no Make target. The firewall policy is `strict`: DNS, NTP and TCP 80/443 are the only host-originated traffic, which is all squid needs.
