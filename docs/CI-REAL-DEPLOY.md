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
