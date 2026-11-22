## Context

See `proposal.md`. Provider research (source reading, 2026-11-22): hcloud, scaleway, upcloud, vultr, tailscale and both Porkbun providers use Go `http.DefaultTransport` or `ProxyFromEnvironment`, so they should honour `HTTPS_PROXY`; this is unproven at runtime. Vultr has an account-wide API access-control IP allowlist; Scaleway IAM supports `request.ip` conditions; Porkbun keys accept source CIDRs; Hetzner tokens and B2 keys have no IP restriction; UpCloud sub-accounts may support IP filters. The fleet already has `firewall` (nftables), `tailnet-management` and `baseline` roles and the shared cloud-init template.

## Goals / Non-Goals

- Goal: one stable, secretless source address for every provider API call from CI.
- Non-goal: proxying VPN traffic, registry downloads or GitHub; the observer (observer-a) is not reused.
- Non-goal: high availability. A second egress node can be added later by listing both addresses in the allowlists.

## Decisions

- Separate root `terraform/ops/egress-proxy` instead of a node in `terraform/providers/hetzner`, because the provider roots model VPN nodes and their policies (listeners, cohorts) and the egress node has none. Hetzner is chosen because its API has no IP allowlist, so the egress node can always be recreated without the egress node itself. Rejected: observer-a (operator choice), a VPN node (prior art showed it mixes roles).
- `hcloud_primary_ip` with `auto_delete = false` assigned to the server keeps the address across recreation (`REQ-EGRESS-FIXED-ADDRESS`).
- Proxy software: Debian `squid` package, pinned to the exact Debian version, configured with `http_access deny !CONNECT`, `acl SSL_ports port 443`, `http_access deny !SSL_ports`, `acl api dstdomain -n <list>`, `http_access deny !api`, `http_access allow ci_src`, `http_access deny all`, no `ssl_bump`, `cache deny all`, `http_port <tailnet-ip>:3128`, and a custom `logformat` with time, client, host, status and bytes. The `-n` option disables reverse lookup for this ACL. Test IPv4 and IPv6 literals with PTR records matching an allowed name and verify no upstream connection. Rejected: tinyproxy (cannot refuse non-CONNECT methods for allowlisted hosts), a custom proxy (new code on a security boundary).
- Hardened unit: a drop-in for the packaged unit following the `systemd` skill floor (`NoNewPrivileges`, `ProtectSystem=strict`, `ReadWritePaths` for log and spool, `PrivateTmp`, `CapabilityBoundingSet=` empty since 3128 is unprivileged, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `LimitNOFILE`, `Restart=on-failure`), started after `tailscaled` so the Tailnet address exists.
- nftables through the `firewall` role: accept 3128 only on `tailscale0` from `100.64.0.0/10`; no public inbound except what Tailscale needs; outbound 443, DNS and Tailscale.
- Inventory: group `egress` in the ops repository; playbook `ansible/playbooks/egress-proxy.yml` applying `baseline`, `firewall`, `tailnet-management` (tag `tag:egress`) and `egress-proxy`; it does not run VPN roles.
- For normal CI state and provider requests set `HTTPS_PROXY` before backend initialization. Install pinned provider packages separately from a verified cache or mirror. For approved bootstrap or reconstruction of the egress root alone, use direct TLS to the fixed Hetzner and B2 endpoints, the same remote state and W3 lock. The recovery route cannot target other roots. Use the operator workstation with its state key and a verified ops checkout when Actions is unavailable.
- Provider proof: run `tofu plan` per root through the proxy with each provider token, then read the proxy log for the expected `CONNECT` lines. Only then set the Vultr allowlist; after that, a plan without the proxy must fail for Vultr (negative check).

## Contracts and ownership

- New: `terraform/ops/egress-proxy/**` (with `.terraform.lock.hcl`, `tests/*.tftest.hcl` using `mock_provider`), `ansible/roles/egress-proxy/**` with Molecule scenario, `ansible/playbooks/egress-proxy.yml`, `docs/how-to/egress-proxy.md`, `ansible/roles/egress-proxy/CLAUDE.md` with `AGENTS.md` symlink.
- Changed: `Makefile` `tf-test` loop (after W4 in the shared lane), `terraform/policy/` coverage for the new root, `ansible/roles/firewall` inputs if a new port variable is needed, `docs/reference/testing.md` Molecule row, image-scan or digest governance rows if the Molecule image list changes.
- Ops repository: `config/tfvars/egress-proxy/*.tfvars`, `config/backend/egress-proxy.s3.tfbackend`, inventory group, Tailnet grant in `tailnet/policy.hujson`.

## Risks / Trade-offs

- A stopped proxy on a healthy server can be repaired over management SSH on the Tailnet. Grant `tag:ci-deploy` only the management port on `tag:egress`. A lost server requires the direct egress-root path and verified bootstrap before switching normal jobs back to the proxy.
- Allowlisted host can be abused as an exfiltration channel only to those provider APIs → accepted; no general Internet access.
- DNS spoofing of an allowlisted name on the node → TLS is end to end between runner and provider, so a spoofed host fails certificate validation.

## Migration Plan

1. Land root, role, playbook, tests and docs (offline: `make tf-test`, `make tf-policy-verify`, `make molecule-test ROLE=egress-proxy`, `make snapshot-check`).
2. Authorized live steps: apply the egress root (MacBook or CI `tofu-apply`), bootstrap with `vpn-bootstrap` (Tailnet enrollment), dry-run then deploy the playbook, add the Tailnet grant, run the provider proof, then set the Vultr allowlist to the egress address and remove the workstation /32, then optional allowlists.
3. Rollback: re-add the previous Vultr allowlist entry in the console, unset `HTTPS_PROXY`, destroy the egress root; no VPN node depends on it.

## Open verification questions

1. Does every provider client (hcloud, scaleway, upcloud, vultr, porkbun, tailscale) and the B2 S3 backend actually route through `HTTPS_PROXY` under OpenTofu at runtime? Source reading says yes; the proof step decides.
2. Are the API host names complete? Some providers redirect or call secondary hosts (for example a B2 `apiUrl`, Scaleway product-specific endpoints). Capture with the proxy log during the proof, with a temporary log-only allow-all on a staging copy of the node, never on production.
3. Does UpCloud offer an API IP filter for sub-accounts, and does Scaleway support `request.ip` for the API keys the fleet uses? Optional allowlists depend on it.
4. Does Vultr's access control also need an IPv6 entry if the egress node has IPv6 and the runner resolves `api.vultr.com` over IPv6 through the proxy? Force IPv4 on the proxy (`dns_v4_first` or equivalent) or add both.
