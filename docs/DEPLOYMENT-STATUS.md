# Deployment status

This document is the repository-safe record of the currently deployed
infrastructure. It intentionally excludes public and private addresses,
hostnames, client identifiers, credentials, certificates, Terraform state,
and decrypted SOPS values. Those remain in git-ignored operator files.

## Current release

| Field | Value |
|---|---|
| Last verified deployment | 2026-08-23 |
| Git release | post-`infra-v1.0.0` `main` |
| Deployed source commit | `0c22a24` (`fix(infra): start ssh unit before first-boot reload in cloud-init`, includes all audit remediation through #86) |
| Source validation | [#87 CI](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/32634672153) green, CodeQL and Scorecard passing |
| Release state | full-fleet recreation: every server was deliberately destroyed and rebuilt from git + secrets |

The deployed source was applied to the existing fleet. No server was replaced
or recreated during this update.

## Active fleet

| Provider | Terraform environment | Ansible cohort | Runtime purpose |
|---|---|---|---|
| UpCloud | `p0-upcloud` | `p0-self-steal` | P0 VLESS + REALITY + Vision with owned loopback self-steal target |
| Scaleway | `p1-scaleway` | `p1-web` | P1 nginx landing site + direct XHTTP |
| Vultr | `p2-vultr` | `p2-udp` | P2 Hysteria2 + AmneziaWG |

Tailscale is the management plane only. The generated inventory preserves the
Terraform-owned public endpoint as `vpn_service_address`; local extra vars may
override only `ansible_host` for Tailscale administration. Watchdog and other
data-plane probes therefore continue to target the public service address.

## Observed convergence

### Terraform

On 2026-08-23 all three servers were destroyed and recreated through the
sanctioned disposable-node path (`scripts/destroy.sh` with its interactive
confirmations, then plan + apply per environment).

- The operator egress CIDR in every environment tfvars was rotated from the
  stale address to the current one before the firewall applies; the Vultr
  control-plane allowlist was updated in the provider console to the same new
  exact address.
- Scaleway assigned P1 the same IPv4 as the previous generation, but its IPv6
  changed; P0 and P2 received entirely new public addresses.
- A fresh Ubuntu 24.04 image socket-activates SSH, leaving `ssh.service`
  inactive during cloud-init first boot. The fail-closed bootstrap marker
  chain died at `systemctl reload ssh`, which is fixed on `main` by #87
  (enable the unit before the reload) and verified live on the recreated P1.
- The recreated P1 required a DNS AAAA rotation for the owned site identity;
  the `verify.yml` hostname-resolution gate caught the stale record and went
  green after the update.

### Ansible

The complete site deployment and both post-deploy gates completed without an
unreachable or failed host:

| Gate | P0 | P1 | P2 |
|---|---:|---:|---:|
| `make deploy` | `failed=0` | `failed=0` | `failed=0` |
| automatic `make source-drift` | `ok=4 changed=0 failed=0` | `ok=4 changed=0 failed=0` | `ok=4 changed=0 failed=0` |
| `make verify` | `ok=16 failed=0` | `ok=19 failed=0` | `ok=13 failed=0` |
| `make security-verify` | `ok=17 failed=0` | `ok=17 failed=0` | `ok=17 failed=0` |

Deployment ran with the validated decoy-origin override
(`secrets/local/decoy-origin.yml`, see DEPLOY-PROFILES.md "Decoy site
identity") so the `nginx-xhttp` and `hysteria` identity asserts hold against
the real owned origin.

First-provision dry-run note: three check-mode-only failures are expected on
fresh nodes because package-install/download/directory tasks are skipped under
`--check` while their dependents still evaluate (baseline timesyncd enable,
xray archive unpack destination, hysteria binary staging). They do not occur
in a real run and are not repo-to-live drift.

Outside-in probes after convergence: P0 REALITY TCP/443 reachable, P1 site
answers HTTPS 200 with the correct SNI identity, P2 exposes exactly its
listener contract (Hysteria2 UDP/443, AmneziaWG UDP/51820).

SSH host keys were regenerated on every node by design; clients that pinned
old host keys will see a host-key-change warning once and must accept the new
keys. All public endpoints changed except the P1 IPv4 — client devices must
re-fetch the subscription or update endpoints manually.

Secret schema validation, placeholder checks, certificate checks, and private
key/certificate matching passed before deployment. The decrypted SOPS file was
shredded with `make clean`, and local Terraform plan artifacts were removed.

## Verification boundary

The results above prove configuration convergence, service health, hardening,
and the authenticated probes implemented by the repository. They do not by
themselves prove every transport from a filtered client network. Outside-in P1
XHTTP, public P2 UDP/AmneziaWG, and filtered-vantage SNI survival remain
separate client-path checks.

No `vpn-deploy-known-good-*` tag was created for this rollout. The release tag
identifies source code; it is not a substitute for future live drift evidence.

## Current operator limitations

The Vultr allowlist entry is intentionally tied to the exact operator address
admitted on 2026-08-23 and must be updated in the provider console whenever
that address changes; the API rejects all requests from unlisted addresses.
Fresh-node dry-runs show the three documented check-mode-only failures listed
above until the first real convergence.

## Refresh procedure

1. Confirm the checkout is at the intended reviewed commit, its required CI is
   green, and the working tree is clean.
2. Decrypt only into the configured git-ignored `SECRETS_FILE`.
3. Run a provider-refreshed plan for every named environment. Stop on any
   replacement or unexplained drift.
4. Rebuild the inventory, restore the documented Tailscale SSH override, and
   prove the SSH path before deployment.
5. Run `make deploy`, `make verify`, and `make security-verify`. When package
   backlog or reboot markers are present, run `make os-maintenance`; it rolls
   one node at a time and repeats both verification gates.
6. Confirm `make source-drift` is green for every node; `deploy` and `verify`
   run it automatically, but the standalone command is the fastest parity
   check.
7. Run the relevant outside-in client-path probes.
8. Run `make clean` and remove plan artifacts.
9. Update this file only from observed results; never copy live endpoints or
   secret material into it.
