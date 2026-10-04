# Deployment status — last verified snapshot

This document records the last verified deployment snapshot, observed on
**2026-08-23** at source commit
`0c22a24cff5733947900ad345da4b9fe830a528e`. It does not establish the current
fleet, deployed revision, or service health as of a later date. Repository
`main`, a green CI run, and this snapshot are separate evidence.

The snapshot intentionally excludes public and private addresses,
hostnames, client identifiers, credentials, certificates, Terraform state,
and decrypted SOPS values. Those remain in git-ignored operator files.

## Snapshot release

| Field | Value |
|---|---|
| Last verified deployment | 2026-08-23 |
| Git release | post-`infra-v1.0.0` `main` |
| Deployed source commit | `0c22a24cff5733947900ad345da4b9fe830a528e` (`fix(infra): start ssh unit before first-boot reload in cloud-init`, includes all audit remediation through #86) |
| Source validation | PR #87 CI fully green, CodeQL and Scorecard passing on the deployed commit |
| Release state | full-fleet recreation: every server was deliberately destroyed and rebuilt from git + secrets |

At verification, every server in the fleet had been deliberately destroyed
and rebuilt from git + secrets through the sanctioned disposable-node path;
no prior-generation node survived that recreation.

## Fleet at verification

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

All results and operational notes in this section describe the 2026-08-23
rollout. Follow the current runbooks linked below for a new operation; the
historical command examples do not supply today's deployment prerequisites.

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

## Snapshot operator limitations

The Vultr allowlist entry is intentionally tied to the exact operator address
admitted on 2026-08-23 and must be updated in the provider console whenever
that address changes; the API rejects all requests from unlisted addresses.
Fresh-node dry-runs show the three documented check-mode-only failures listed
above until the first real convergence.

## Refresh procedure

Refreshing the snapshot requires an explicitly authorized live operation;
editing this document does not refresh the evidence.

1. Confirm the intended reviewed source revision, clean checkout, and its
   required CI using [TESTING.md](TESTING.md#ci-dependency-selection).
2. Follow [RUNBOOK-deploy.md](RUNBOOK-deploy.md) for the current deployment
   prerequisites and gate sequence, or [QUICKSTART.md](QUICKSTART.md) for
   first provisioning. These own inventory selection, SSH recovery, Tailnet
   bootstrap, private socket contexts, promotion inputs, and failure receipts.
   Apply the required origin inputs from
   [DEPLOY-PROFILES.md](DEPLOY-PROFILES.md#decoy-site-identity).
3. Record the observed deployment date, exact deployed source revision,
   selected fleet, convergence and source-drift gates, and any unresolved
   client-path checks. Preserve the distinction between source/CI evidence
   and live or client-path evidence.
4. Complete the runbook cleanup. Update this snapshot only from those
   observed results; never copy live endpoints or secret material into it.
