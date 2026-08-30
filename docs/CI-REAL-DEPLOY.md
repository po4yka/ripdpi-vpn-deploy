# Real-VPS CI deploy gate

The `real-vps-deploy` workflow is a **partial-fidelity** production-deploy
approximation in GitHub Actions: provision an ephemeral UpCloud VPS, run the
full playbook plus `verify.yml` against it, then destroy it. Docker molecule
scenarios catch most regressions; this gate catches the ones that depend on the
real cloud environment (template behaviour, cloud-init quirks, provider firewall
ordering, real systemd unit startup, etc.). It does not currently run
`make smoke-test`; that remains an operator-driven live-traffic check.

Partial-fidelity is intentional, not a production-equivalence claim. The job
uses synthetic secrets, skips the strict pre-deploy secret/certificate checks,
and disables roles that require real upstreams, persistent state, or platform
features that CI cannot reproduce safely. A green run means "the real VPS deploy
skeleton converges and verifies under CI constraints", not "the full production
surface is healthy".

## When it runs

The workflow is intentionally NOT triggered on every push — it burns
provider credit and takes ~15-20 minutes per run. Three triggers:

  * **workflow_dispatch** — manual: Actions → "real-vps-deploy" →
    Run workflow. Optional `zone` input.
  * **pull_request labeled `ci-real-deploy`** — a maintainer
    consciously adds the label when a PR touches provisioning,
    role ordering, or cloud-init.
  * **schedule** — Mondays at 06:00 UTC.

Every trigger waits for a required reviewer to approve the deployment on the
protected `ci-real-deploy` GitHub Environment before any job step runs. A PR
label alone is insufficient. The same gate applies to
`transport-reachability-matrix`. Before trusting a credentialed run, execute
`make check-ci-deploy-gate`: this read-only check fails if the environment is
missing, has no required reviewer, or cannot be verified through the GitHub API.
The local workflow contract tests cannot inspect hosted repository settings.

Workflow authors remain trusted: a job is protected only while it references
the protected environment. Keep deployment credentials as environment secrets;
repository-level secrets are also available to workflows that omit that gate.

The job refuses to start on a fork PR (secrets aren't exposed there)
and uses per-distro concurrency groups so two runs for the same distro
never race against the UpCloud account.

## Required GitHub secrets

| Secret | Purpose |
|---|---|
| `UPCLOUD_USERNAME` | UpCloud sub-account with VPS create + destroy |
| `UPCLOUD_PASSWORD` | sub-account password — use a tightly scoped sub-account, NOT the master account |
| `CI_SOPS_AGE_KEY` | age private key staged onto the runner so any later step needing SOPS works; CI does not commit an encrypted blob |
| `CI_SSH_PRIVATE_KEY` | SSH key the ephemeral VPS authorises; not reused outside CI |
| `CI_REALITY_TARGET` | Operator-owned REALITY target in `host:port` form; kept out of the repository |
| `CI_REALITY_SERVER_NAME` | TLS server name accepted by the owned REALITY target |
| `CI_WATCHDOG_CANARY_URL` | Operator-owned HTTPS endpoint that returns exactly `204` |
| `CI_UPCLOUD_TEMPLATE_UUID` | **Debian 13** minimal cloud-image template UUID. List candidates via `upctl storage list --public --template`. |
| `CI_UPCLOUD_TEMPLATE_UUID_UBUNTU24` (optional) | **Ubuntu 24.04** minimal cloud-image template UUID. When set, the deploy matrix fans out to both distros in parallel; when empty, the Ubuntu matrix entry skips with a notice and only Debian runs. |

## Matrix fan-out across distros

The deploy job runs as a `strategy.matrix` over `[debian13, ubuntu2404]`.
Each matrix entry pulls a distinct UpCloud template (the `template_secret_name`
column above), gets its own concurrency group key (`real-vps-deploy-debian13`
vs. `real-vps-deploy-ubuntu2404`), and writes its own tfvars file with a
distro-suffixed env name so the two provisions don't collide on UpCloud
state. When an operator hasn't populated `CI_UPCLOUD_TEMPLATE_UUID_UBUNTU24`,
that matrix entry short-circuits at the first step with a GitHub notice
— no apply, no destroy, no cost.

Cost note: enabling Ubuntu doubles the run minutes + UpCloud credit per
PR-labeled run. Use the label sparingly.

## CI secrets generated at runtime

The workflow does **not** carry a `secrets/ci.secrets.sops.yaml` blob.
`scripts/ci-bootstrap-secrets.sh` runs in the workflow and writes a
complete synthetic secrets YAML to
`/tmp/vpn-${CI_ENV}.secrets.yaml`:

  * fresh REALITY keypair (from `ghcr.io/xtls/xray-core:<version>`
    `x25519`)
  * fresh recipient and dedicated watchdog UUIDs + shortIds, fresh Hysteria
    password, fresh AmneziaWG keypair + random H1..H4
  * self-signed certificate covering the CI server hostname
  * Xray + Hysteria release-asset sha256 computed live by curl +
    sha256sum from the upstream URLs

The certificate is self-signed and the geodata URLs are placeholders,
so the `pre-deploy-check` chain would reject the secrets. CI runs
with `SKIP_PRECHECK=1`; ansible's per-role validate-before-restart
still gates a broken render.

`verify.yml` runs the deployed watchdog immediately and requires an
authenticated REALITY round trip through the ephemeral node to
`CI_WATCHDOG_CANARY_URL`. This is the load-bearing successful-handshake test;
it remains an on-node, unfiltered-vantage check and does not replace
`make smoke-test` or the managed sentinel quorum.

Disabled roles in CI (via `ANSIBLE_EXTRA_VARS`):

  * `enable_amneziawg=false` — kernel module + NAT not portable
  * `enable_geodata=false`   — placeholder URLs would 404
  * `enable_backup=false`    — restic-against-localhost adds noise
  * `enable_monitoring=false` — node_exporter not interesting here
  * `enable_warp_outbound=false` / `enable_honeypot=false` /
    `enable_policy_ratelimit=false` — defensive roles tested in
    their own molecule scenarios

## Cleanup invariants

The `destroy` step runs in `always()` so a half-built VPS never
outlives the job. The `cleanup CI tfvars file` step deletes the
per-run tfvars even if `destroy` failed, so the next run starts
from a clean slate. Operators verifying after a failed run should
re-check UpCloud billing once a quarter.

### UUID-bound operator staging cleanup

Authorized operator staging uses an environment named `ci-staging-*` and is
stricter than the recurring CI workflow. Use a dedicated worktree so its local
Terraform workspace state is isolated. Keep the state file mode `0600` under a
same-owner directory that is not group/other writable. Keep the cleanup
manifest and post-destroy evidence in one operator-owned `0700` directory;
each file is a regular `0600` file. Do not put that private directory in the
repository. After the server exists, create the manifest through the canonical
Make goal directly from the exact local state before running any destructive
command. The goal authenticates `/1.3/account`, stores the exact API username
only in private artifacts, reads the exact state-bound server through
`/1.3/server`, and derives creation, target, escalation and hard deadlines from
the provider's integer `server.created` value at 36, 44 and 47 hours. Provider
credentials remain one complete ambient `UPCLOUD_USERNAME`/`UPCLOUD_PASSWORD`
or `UPCLOUD_API_USERNAME`/`UPCLOUD_API_PASSWORD` pair; do not pass them as Make
variables. This binds the
exact API principal used for creation and deletion, not a parent billing
account, and does not claim that provider usernames are immutable identifiers.

The private staging tfvars must explicitly keep `enable_backups=false` and
`additional_public_ip=false`. The guard refuses a server state with a provider
backup rule, more than one public IPv4 interface, any nested additional IP, or
any additional Terraform resource outside the exact owned cleanup set.

```bash
ENV=ci-staging-<run>
STATE_PATH="$PWD/terraform/providers/upcloud/terraform.tfstate.d/${ENV}/terraform.tfstate"
umask 077
PROVIDER=upcloud ENV="$ENV" \
STAGING_CLEANUP_MANIFEST=/absolute/private/path/cleanup-manifest.json \
STAGING_CLEANUP_STATE="$STATE_PATH" \
STAGING_CLEANUP_HOSTNAME=vpn-ci-staging-<run> \
make staging-cleanup-manifest
```

The exact state must contain only `upcloud_server.vpn`, its
`upcloud_firewall_rules.vpn` resource and `terraform_data.ssh_port`. The guard
extracts both owned UUIDs and calculates the state digest from those same state
bytes; an operator does not type either UUID or account identity into the
manifest. Every path ancestor is opened without following symlinks, and final
files are accessed relative to a held parent directory descriptor.

Destroy the staging environment through the guarded path. One authorization
step validates the same manifest/state inodes and bytes, rechecks its
authenticated account username, and reserves evidence before creating the
lifecycle override or allowing Terraform to refresh provider state. Plan
validation requires that exact reservation. Immediately before apply, the
controller rechecks the account, reservation, state and exclusive hard
deadline, then durably changes the same evidence inode to `apply_started`.
Only exact deletes of the manifest-bound
server, root storage, server firewall resource and local SSH-port identity are
accepted. Create, update, replacement, foreign deletion, changed state or an
expired deadline refuses before apply. The post-destroy evidence path is
reserved as a new `0600` inode before the lifecycle override or Terraform plan
is created. Existing paths, symlinks in any ancestor, unsafe parent permissions and a manifest
whose environment differs from the command's exact `ENV` refuse without any
Terraform invocation. An interactive refusal before apply removes only an
unchanged exact reservation; a started or failed apply retains it for manual
inspection.

An apply that started before the hard deadline may finish read-only provider
absence verification after expiry, but evidence is then explicitly
`verified_after_expiry` / `expired_after_apply`; an expired reserved operation
cannot begin or query resources.

The binary plan is created under the same private directory with `umask 077`,
opened once, unlinked, and passed through the same inherited file descriptor to
both `terraform show` and `terraform apply`. The applied inode is therefore the
one whose JSON view passed the guard; no worktree pathname remains available
for substitution or disclosure between validation and apply.

```bash
PROVIDER=upcloud ENV=ci-staging-<run> \
STAGING_CLEANUP_MANIFEST=/absolute/private/path/cleanup-manifest.json \
STAGING_POST_DESTROY_EVIDENCE=/absolute/private/path/post-destroy.json \
make staging-destroy
```

After apply, the command verifies the authenticated account username matches
the private manifest before any resource GET, then performs bounded read-only
UpCloud GETs and replaces the reservation content in the same inode.
Success requires the exact server and root storage to return their typed
not-found responses; authentication failure, forbidden resources, an existing
resource or an ambiguous response keeps cleanup failed and preserves the
reservation and Terraform state for diagnosis. The staging path preserves the
shared generated inventory byte-for-byte; generic CI destroy keeps its existing
inventory cleanup behavior. A categorical redacted audit record is appended
only after exact provider absence succeeds. The unlinked binary
plan is never republished after apply. The categorical
`billing_status=no-active-owned-resources` means those exact chargeable
resources are absent. It does not rewrite, reverse or predict cumulative invoice
entries. Retain manifest and evidence in encrypted operator storage until the
account billing view has been reviewed, then remove the temporary state and
credentials through their separately approved cleanup path.

## What this does NOT test

  * Strict pre-deploy secret hygiene (`validate-secrets --strict`,
    `spot-check-secrets`, `check-certs`) because the CI secrets are
    intentionally synthetic.
  * The full production role surface; several roles are disabled via
    `ANSIBLE_EXTRA_VARS` as listed above.
  * Production traffic patterns (no real users dial the ephemeral
    REALITY endpoint).
  * Burn-check (the ephemeral IP isn't on RKN's radar long enough
    to provoke a block).
  * Long-running ASN / IP-reputation drift.

Those stay in operator-driven cadence (`make pre-deploy-check`,
`make smoke-test`, `make burn-check`, `make asn-drift`,
`make check-ip-reputation`).
