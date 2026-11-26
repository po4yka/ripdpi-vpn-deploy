# ANS-1795328948145006: Add a secretless egress proxy node for provider APIs

## Objective

A Hetzner node with a retained IPv4 runs a CONNECT-only, Tailnet-only, allowlisted forward proxy with no secrets; every OpenTofu provider and the B2 backend are proven to work through it; provider allowlists name only its address; break-glass is documented and drilled.

## Ownership

New `terraform/ops/egress-proxy/**`, `ansible/roles/egress-proxy/**`, `ansible/playbooks/egress-proxy.yml`, `docs/how-to/egress-proxy.md`. Changed `Makefile` `tf-test` loop (after W4), `terraform/policy/`, `ansible/roles/firewall` inputs, `docs/reference/testing.md`. Ops repository: tfvars, backend file, inventory group, Tailnet grant.

## Execution

- [x] ANS-1795329022845451 Add the egress-proxy OpenTofu root with a retained primary IPv4, encrypted state, mock_provider tests and policy #feature !high @item:ANS-1795328948145006
- [ ] ANS-1795329034006860 Add the egress-proxy Ansible role with the CONNECT-only allowlist, hardened unit, nftables and a Molecule scenario #feature !high @item:ANS-1795328948145006
- [ ] ANS-1795329045195870 Add the egress playbook, inventory group and the Tailnet grant from tag:ci-tofu to the proxy port #feature !high @item:ANS-1795328948145006
- [ ] ANS-1795329056411801 Create and deploy the egress node and prove each provider and the B2 backend through the proxy (authorized live step) #feature !high @item:ANS-1795328948145006
- [ ] ANS-1795329068636739 Enable provider API allowlists and remove the workstation Vultr entry (authorized live step) #feature !high @item:ANS-1795328948145006
- [ ] ANS-1795329082564404 Document egress break-glass for proxy, VPS and GitHub outages and exercise stopped-service and lost-server recovery #feature !high @item:ANS-1795328948145006

## Verification

Local: `make tf-test`, `make tf-policy-verify`, `make molecule-test ROLE=egress-proxy` (method, port, host and IP-literal denials; unit hardening score), `make snapshot-check`, `make shellcheck`. Remote CI: PR checks. Dry-run and live (authorized): egress playbook dry-run then deploy; public port scan negative; provider proof log per root; Vultr direct-call negative check; break-glass drill receipt. Staging: the provider proof runs first against staging workspaces.
