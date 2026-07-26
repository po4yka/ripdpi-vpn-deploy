# Deployment status

This document is the repository-safe record of the currently deployed
infrastructure. It intentionally excludes public and private addresses,
hostnames, client identifiers, credentials, certificates, Terraform state,
and decrypted SOPS values. Those remain in git-ignored operator files.

## Current release

| Field | Value |
|---|---|
| Last verified deployment | 2026-07-26 |
| Git release | [`infra-v1.0.0`](https://github.com/po4yka/ripdpi-vpn-deploy/releases/tag/infra-v1.0.0) |
| Source commit | `93128afc8bcd3449a739edaa17861e844a99a4c4` |
| Release state | published, latest, not a pre-release |

The release source was applied to the existing fleet. No server was replaced
or recreated during this update.

## Active fleet

| Provider | Terraform environment | Ansible cohort | Runtime purpose |
|---|---|---|---|
| UpCloud | `p0-upcloud` | `p0-self-steal` | P0 VLESS + REALITY + Vision with owned loopback self-steal target |
| Scaleway | `p1-scaleway` | `p1-web` | P1 nginx landing site + direct XHTTP |
| Vultr | `p2-vultr` | `p2-udp` | P2 Hysteria2 + AmneziaWG |

Tailscale is the management plane only. Public provider addresses remain the
data-plane identity used by rendered service and verification templates. The
git-ignored generated inventory keeps that public `ansible_host` value and
uses a per-host SSH `HostName` override to route administrative SSH through
Tailscale MagicDNS. Re-running `make inventory` overwrites the generated file,
so the local override must be restored before the next Ansible operation until
the renderer owns this split explicitly.

## Observed convergence

### Terraform

The three named workspaces were initialized and reconciled. Each initial plan
contained only the missing `terraform_data.ssh_port` state resource; applying
it did not replace a server. The resulting plans reported `No changes`.

- UpCloud and Scaleway were refreshed against their provider APIs.
- Vultr reported no configuration-to-state change with `-refresh=false`.
  Provider-live refresh remains outstanding because the current operator
  egress address is not admitted by the Vultr API allowlist.

### Ansible

The complete site deployment and both post-deploy gates completed without an
unreachable or failed host:

| Gate | P0 | P1 | P2 |
|---|---:|---:|---:|
| `make deploy` | `ok=127 changed=3 failed=0` | `ok=109 changed=1 failed=0` | `ok=104 changed=2 failed=0` |
| `make verify` | `ok=14 failed=0` | `ok=12 failed=0` | `ok=13 failed=0` |
| `make security-verify` | `ok=15 failed=0` | `ok=15 failed=0` | `ok=15 failed=0` |

The P0 verification included both authenticated REALITY round trips. Direct
SSH-path inspection confirmed that all three Ansible sessions traversed
Tailscale.

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

- A live Vultr refresh requires admitting the operator's current egress
  address in the provider API allowlist, then re-running `make plan`.
- At `infra-v1.0.0`, `make dry-run` can stop in the firewall role because the
  read-only `sshd -T` discovery task is skipped by Ansible check mode, leaving
  `firewall_effective_ssh_ports` empty. Do not bypass the failure or treat the
  diagnostic-only workaround as committed source. The production deploy and
  verification gates above ran without that patch.
- The Tailscale SSH `HostName` override is local post-processing of the
  git-ignored inventory and is not yet reproduced by `make inventory`.
- On macOS, a full `pip install --require-hashes -r requirements.txt` can fail
  because the resolved `ruamel-yaml-clib` dependency is not pinned with a
  hash. The rollout used a git-ignored local virtual environment for the
  required Python validators; this does not make the lock defect resolved.

## Refresh procedure

1. Confirm the checkout is at the intended signed or published release and the
   working tree is clean.
2. Decrypt only into the configured git-ignored `SECRETS_FILE`.
3. Run a provider-refreshed plan for every named environment. Stop on any
   replacement or unexplained drift.
4. Rebuild the inventory, restore the documented Tailscale SSH override, and
   prove the SSH path before deployment.
5. Run `make deploy`, `make verify`, and `make security-verify`.
6. Run the relevant outside-in client-path probes.
7. Run `make clean` and remove plan artifacts.
8. Update this file only from observed results; never copy live endpoints or
   secret material into it.
