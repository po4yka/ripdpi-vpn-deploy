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
| Deployed source commit | `0c22a24cff5733947900ad345da4b9fe830a528e` (`fix(infra): start ssh unit before first-boot reload in cloud-init`, includes all audit remediation through #86) |
| Source validation | PR #87 CI fully green, CodeQL and Scorecard passing on the deployed commit |
| Release state | full-fleet recreation: every server was deliberately destroyed and rebuilt from git + secrets |

Every server in the fleet was deliberately destroyed and rebuilt from git +
secrets through the sanctioned disposable-node path; no prior-generation node
survives.

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

SSH host keys were regenerated on every node by design. On nodes with new
addresses the first connection simply pins the new key. The P1 IPv4 is
unchanged, so a client holding the previous P1 key gets a host-key-change
failure instead: `StrictHostKeyChecking=accept-new` (used by
`scripts/wait-cloud-init.sh` and `make wait`) rejects changed keys until the
stale entry is removed. Clear it first with `ssh-keygen -R <p1-host>` (repeat
for the Tailscale name if that path was pinned), then reconnect to accept the
new key. All public endpoints changed except the P1 IPv4 — client devices must
re-fetch the subscription or update endpoints manually. Static `/sub/`
payloads rendered by `scripts/issue-sub-token.sh` are stored once as hashed
files and are not regenerated on fetch; before telling any device to re-fetch,
rerun the issuer for every outstanding token with
`scripts/issue-sub-token.sh <client> --refresh-token <token>` so the stored
payload picks up the current Terraform outputs. Since the encrypted
`client_registry` exists (change `sec-1787489155988233-client-config-registry`),
a bare `--refresh-token` resolves the original format, hosts, and cohorts from
the registry and fails closed for unregistered tokens; explicit `--format`
flags override and are audit-logged. For tokens issued before the registry
existed there is no recorded option set — re-issue those tokens with the full
original invocation (`--format`, `--expires`, the correct `PROVIDER`/`ENV`
pair, and for `--format ripdpi` the emitter environment: `HOSTS`, plus
`COHORTS`/`SOPS_FILES` if non-default). Use
`make client-drift CLIENT=<device>` before refreshing to check whether the
last delivery still matches current inputs.

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
5. Run the deployment gates with the cohort limit and the decoy-origin
   override required by DEPLOY-PROFILES.md ("Decoy site identity") — the
   committed P1/P2 profiles carry only a placeholder origin and their identity
   asserts fail without it:
   `ANSIBLE_LIMIT="<all cohort hosts>" ANSIBLE_EXTRA_VARS_FILE=secrets/local/decoy-origin.yml make deploy`,
   then the same prefix for `make verify` and `make security-verify`. When
   package backlog or reboot markers are present, run `make os-maintenance`
   with the same variables; it rolls one node at a time and repeats both
   verification gates.
6. Confirm `make source-drift` is green for every node; `deploy` and `verify`
   run it automatically, but the standalone command is the fastest parity
   check.
7. Run the relevant outside-in client-path probes.
8. Run `make clean` and remove plan artifacts.
9. Update this file only from observed results; never copy live endpoints or
   secret material into it.
