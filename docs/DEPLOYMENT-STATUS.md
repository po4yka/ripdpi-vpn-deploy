# Deployment status

This document is the repository-safe record of the currently deployed
infrastructure. It intentionally excludes public and private addresses,
hostnames, client identifiers, credentials, certificates, Terraform state,
and decrypted SOPS values. Those remain in git-ignored operator files.

## Current release

| Field | Value |
|---|---|
| Last verified deployment | 2026-08-09 |
| Git release | [`infra-v1.0.0`](https://github.com/po4yka/ripdpi-vpn-deploy/releases/tag/infra-v1.0.0) |
| Deployed source commit | `52d8e2f8a7463cd9ead4b5addbf8979741996993` |
| Source validation | [GitHub CI run 31306843858](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/31306843858), CodeQL, and Scorecard passed |
| Release state | published `infra-v1.0.0` baseline plus verified post-release `main` updates |

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

The three named workspaces were initialized and reconciled. Each initial plan
contained only the missing `terraform_data.ssh_port` state resource; applying
it did not replace a server. The resulting plans reported `No changes`.

- UpCloud and Scaleway were refreshed against their provider APIs.
- Vultr control-plane preflight passed after admitting the exact operator
  address and disabling the broad IPv4 and IPv6 allowlist entries. A normal
  provider-refreshed plan reported `No changes`. A refresh-only comparison
  reports only the provider's volatile, sensitive, computed `kvm` attribute;
  it does not represent a configured infrastructure change.

### Ansible

The complete site deployment and both post-deploy gates completed without an
unreachable or failed host:

| Gate | P0 | P1 | P2 |
|---|---:|---:|---:|
| `make deploy` | `ok=140 changed=5 failed=0` | `ok=125 changed=14 failed=0` | `ok=115 changed=12 failed=0` |
| `make verify` | `ok=16 failed=0` | `ok=16 failed=0` | `ok=13 failed=0` |
| `make security-verify` | `ok=15 failed=0` | `ok=15 failed=0` | `ok=15 failed=0` |

The P0 verification included both authenticated REALITY round trips. Direct
SSH-path inspection confirmed that all three Ansible sessions traversed
Tailscale.

On 2026-08-08, P0 and P1 converged loopback-only Xray StatsService and a
60-second redacting textfile collector without server replacement. Redacted
`xray-diagnostics` completed on both nodes with `ok=3 failed=0`. The outside-in
ARM64 VLESS sentinel returned `healthy`: its direct control and both REALITY
endpoint variants were `ok`, with no monitoring errors or rotation candidate.
The collector exports only aggregate inbound/outbound counters and freshness;
it does not expose client identifiers.

On 2026-08-09, the dedicated rolling OS-maintenance playbook upgraded the
fleet in P1, P2, P0 order with `serial: 1`. The initial package backlog was
60 packages on P0, 25 on P1, and 8 on P2. All three nodes rebooted when their
package state required it and returned through the Tailscale management path.
The post-maintenance simulation reported zero remaining upgrades and no reboot
marker on every node. Managed unattended security upgrades are installed and
the `apt-daily-upgrade` timer is enabled throughout the fleet.

The maintenance playbook and both post-deploy gates completed without an
unreachable or failed host:

| Gate | P0 | P1 | P2 |
|---|---:|---:|---:|
| `make os-maintenance` | `ok=17 failed=0` | `ok=16 failed=0` | `ok=18 failed=0` |
| `make verify` | `ok=16 failed=0` | `ok=16 failed=0` | `ok=13 failed=0` |
| `make security-verify` | `ok=17 failed=0` | `ok=17 failed=0` | `ok=17 failed=0` |

P0 verification again included authenticated REALITY round trips and fresh
Xray StatsService metrics. P1 verified its XHTTP listener and P2 verified its
Hysteria2 UDP and AmneziaWG listeners after reboot.

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

No provider control-plane limitation was observed during the latest rollout.
The Vultr allowlist entry is intentionally tied to the current exact operator
address and must be updated when that address changes.

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
6. Run the relevant outside-in client-path probes.
7. Run `make clean` and remove plan artifacts.
8. Update this file only from observed results; never copy live endpoints or
   secret material into it.
