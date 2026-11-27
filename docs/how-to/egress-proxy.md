# Converge the egress proxy node

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-11-27

## Purpose and scope

The egress node is one non-VPN host that runs a CONNECT-only squid proxy for provider API calls (the `egress-proxy` role). It listens only on its Tailnet IPv4 address, port 3128, and holds no secrets. This page shows how to converge it with `ansible/playbooks/egress-proxy.yml`. It runs `baseline`, `firewall`, `tailnet-management` and `egress-proxy`, and no VPN role.

## Inputs

- A rendered inventory with one host in the group `egress`, already enrolled in the Tailnet with `tag:egress` through the bootstrap-tailnet command. The playbook verifies the tag and fails closed without it.
- `egress_proxy_b2_region`, the Backblaze B2 region for the S3 host. The role refuses an empty value.
- The usual `allowed_ssh_cidrs`, `vpn_service_address` and `tailnet_management.approved_sources` inventory values.

The Tailnet grants already exist: `tag:ci-tofu` reaches `tag:egress` on 3128 and `tag:ci-deploy` reaches it on 22. The playbook reads the listen address from the node (`tailscale status --json`), so no address input is needed.

## Run

```bash
ansible-playbook ansible/playbooks/egress-proxy.yml -i inventory/<env>.yml --limit <egress-host> -e egress_proxy_b2_region=<region>
```

There is no Make target. The firewall policy is `strict`: DNS, NTP and TCP 80/443 are the only host-originated traffic, which is all squid needs.
