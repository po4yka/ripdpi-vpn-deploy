# Converge the egress proxy node

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-11-28

## Purpose and scope

The egress node is one non-VPN host that runs a CONNECT-only squid proxy for provider API calls (the `egress-proxy` role). It listens only on its Tailnet IPv4 address, port 3128, and holds no secrets. This page shows how to converge it with `ansible/playbooks/egress-proxy.yml`. It runs `baseline`, `firewall`, `tailnet-management` and `egress-proxy`, and no VPN role.

## Inputs

- A rendered inventory with one host in the group `egress`, already enrolled in the Tailnet with `tag:egress` through the bootstrap-tailnet command. The playbook verifies the tag and fails closed without it.
- `egress_proxy_state_host`, the S3 host of the OpenTofu state backend (path-style), for example `s3.fr-par.scw.cloud`. The role refuses an empty value or an IP address.
- The usual `allowed_ssh_cidrs`, `vpn_host_address` and `tailnet_management.approved_sources` inventory values.

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

The Tailnet uses Tailnet Lock, so sign the enrollment key before bootstrap (`tailscale lock sign file:<key file>` on a trusted device, see [tailnet-management.md](tailnet-management.md#bootstrap-one-node)). With an unsigned key the node enrolls, but the controller never sees it as a peer and the management proof fails. Public SSH must come from one stable source address for the whole bootstrap; a network that sends connections through several NAT addresses fails at random steps.

After `make migrate-ssh-ownership`, switch the inventory entry to the Tailnet transport: set `ansible_host` to the node's Tailnet IPv4 and move the `server_ipv4` value to `vpn_host_address`, which the tooling uses as the host key alias and the Tailnet check uses as the public address. Then restore the documentation-range placeholder in `allowed_ssh_cidrs` and apply it. The converge takes `tailnet_management.approved_sources` from the `binding.approved_sources` of the bootstrap handoff; a different list fails the Tailnet check with `tailnet-binding-mismatch`.

Open item (W7): CI runners that reach `tag:egress` on port 22 need Tailnet source addresses that the exact `approved_sources` firewall admits. Until that is resolved, only the operator controller sources in `approved_sources` can reach the node.

## Run

```bash
ansible-playbook ansible/playbooks/egress-proxy.yml -i inventory/<env>.yml --limit <egress-host> -e egress_proxy_state_host=<state S3 host>
```

There is no Make target. The firewall policy is `strict`: DNS, NTP and TCP 80/443 are the only host-originated traffic, which is all squid needs.

## Call provider APIs through the proxy

The Vultr API access list names only the egress IPv4, so a Vultr call from any other address returns HTTP 401. Run OpenTofu and other provider clients from a Tailnet controller with `HTTPS_PROXY=http://<egress Tailnet IPv4>:3128` and an empty `NO_PROXY`. The proxy admits only the hosts in `egress_proxy_api_hosts` and `egress_proxy_state_host`; any other HTTPS host fails at CONNECT with 403. A client that also needs another host, such as an ACME directory, must list that host in `NO_PROXY`.

To change the Vultr access list, open the API Access page of the Vultr console. Keep exactly one entry, the egress IPv4 as `/32`, and keep the any-address entries disabled. The UpCloud, Scaleway and Porkbun access lists are optional; when one is enabled, it names only the egress IPv4.

## Break-glass

Every path below runs from the operator MacBook with the local operator kit and a local clone of the ops repository. None of them needs GitHub.

### The proxy service stops

Symptom: a proxied call fails before CONNECT (`curl` exit 7, connection refused, on port 3128) while the node still answers on the Tailnet. Rerun the egress playbook from a Tailnet controller, as in [Run](#run). Its `Enable and start squid` task starts the service and the run changes nothing else. Then make one proxied call to an allowlisted host and expect `CONNECT 200`. For a fast manual repair, connect over the Tailnet with the pinned key (`ssh -o HostKeyAlias=<vpn_host_address> <admin_user>@<Tailnet IPv4>`) and run `sudo systemctl start squid`, then rerun the playbook so the node matches its configuration.

### The server is lost

Use this path when the node does not answer on the Tailnet or its management access is gone. The node is disposable; recreate it rather than repairing it. Do not set `HTTPS_PROXY` for any step, because the proxy is the thing that is down: the egress root talks to Hetzner and the state backend directly.

1. Put one stable operator source address in `allowed_ssh_cidrs` of the egress tfvars. A network that sends connections through several NAT addresses fails later steps at random.
2. Plan and apply a destroy of only the server with the write state identity, so OpenTofu takes the state lock: `PROVIDER=egress-proxy ENV=prod scripts/terraform-env.sh plan -destroy -target=hcloud_server.egress -var-file=<egress tfvars> -out=<private plan>`, review that it destroys exactly one resource, then `scripts/terraform-env.sh apply <private plan>`. `make destroy` does not support this root, and a full destroy stops at the primary IP's `prevent_destroy`. The primary IP and the provider firewall stay.
3. Run `make plan` and `make apply` for `PROVIDER=egress-proxy ENV=prod`. The new server takes the retained primary IPv4, so provider allowlists stay valid.
4. Scan the new ed25519 host key, compare its fingerprint with the cloud-init output in the provider console, and pin it. Update `host_key_sha256` in the bootstrap config.
5. Run `make wait`, `make install-ssh-recovery`, `make bootstrap-tailnet` with a fresh signed `tag:egress` key, and `make migrate-ssh-ownership`, as in [First enrollment](#first-enrollment). A fresh node needs no `policy_approval`.
6. Switch the inventory to the Tailnet transport, converge, check one proxied call per provider, and restore the `allowed_ssh_cidrs` placeholder. Only then send proxied jobs back to the proxy.

### The proxy and GitHub are down and a Vultr change cannot wait

The Vultr API rejects every address except the egress IPv4. If a Vultr node must change before the proxy is back:

1. Write a private receipt in the operator kit with the time, the reason and the address you are about to admit.
2. In the Vultr console, add the operator's current stable source as one `/32` to the API access list.
3. Run the Vultr plan and apply from the MacBook without `HTTPS_PROXY`.
4. Remove the temporary entry at once, confirm that only the egress `/32` is left, and record the removal time in the receipt. Never enable the any-address entries.
