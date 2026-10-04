# Runbook — deploy

Two flows: **first-time deploy** (handled by `QUICKSTART.md`) and
**re-deploy after editing configs** (this runbook).

For the last verified release snapshot, provider-to-role mapping, recorded gate
results, and unresolved operator limitations, start with
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md).

## Re-deploy after a config or secrets edit

When you've edited a role template, group_vars, or the secrets file, and
want to push the change to an existing VPS, prepare the selected node's inputs
before using the [ordinary re-deploy recipe](#ordinary-re-deploy-recipe).
The file paths in that recipe refer to prepared private files, not files the
controller creates for you.

| Artifact | Producer | When needed / input or output |
|---|---|---|
| Exact inventory alias, SSH key and reviewed host-key pins | Operator selects the canonical generated inventory entry and verifies its transports | Inputs before recovery, bootstrap or ordinary deploy; an empty `ANSIBLE_LIMIT` selects all `vpn` hosts |
| Disposable staging cleanup manifest | Operator follows [UUID-bound staging cleanup](CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup) | Input before either installer on disposable staging |
| Installed recovery generation | `make install-ssh-recovery` for the exact alias | Guest output required before bootstrap and ordinary `dry-run` / `deploy`; reinstall only at the documented boundary below |
| Tailnet bootstrap handoff | Successful [one-node bootstrap](TAILNET-MANAGEMENT.md#bootstrap-one-node) | Private output containing observed contexts; use it to render inventory with `TAILNET_HANDOFFS=<private-handoff-path> make inventory` before ordinary deploy |
| `DEPLOY_SSH_CONTEXTS_FILE` | Operator assembles the exact-alias mapping from observed socket contexts | Private mode-`0600` input before SSH ownership migration, `dry-run` and `deploy`; never fabricate contexts |
| `DEPLOY_PROMOTION_CONFIG_FILE` | Operator prepares the exact-alias mapping using [the promotion schema](PROTOCOL-LIVENESS.md#decision-and-promotion-behavior) | Private mode-`0600` input for `deploy`; the controller validates copies before SSH and obtains fresh exact-node proof after convergence |
| `DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE` | Operator maps each exact alias to a distinct, absent absolute sink under a private mode-`0700` directory | Private mode-`0600` input for `deploy`; the mapping must exist, its receipt sinks must not |
| SSH baseline failure receipt | Deploy controller handles an SSH baseline failure | Private diagnostic output only on that failure; absent after success and never an acceptance receipt |
| Configured `SECRETS_FILE` | `make decrypt` from the selected SOPS source | Private mode-`0600` runtime input before ordinary `dry-run` / `deploy`; remove with `make clean` afterwards |

On a fresh node, or whenever the reviewed recovery generation changes, install
the recovery foundation for that one exact inventory alias before the first
ordinary `dry-run` or `deploy`:

```bash
make install-ssh-recovery ANSIBLE_LIMIT='<exact-inventory-alias>' \
  SSH_RECOVERY_EXCLUSIVE_WINDOW=1
```

For a fresh Tailnet node, stop after the recovery installer and run the
[one-node Tailnet bootstrap](TAILNET-MANAGEMENT.md#bootstrap-one-node) before
`dry-run`. Bootstrap obtains the real management address and socket contexts.
On disposable staging, first run both fixed
[autonomous recovery exercises](TAILNET-MANAGEMENT.md#disposable-staging-recovery-exercises)
with separate one-use keys. They deliberately leave enrollment unconfirmed and
must publish their redacted private evidence before the later positive
bootstrap; do not substitute `SIGTERM` or an ordinary bootstrap failure.
On a fresh Debian node, run the separate policy-preserving SSH ownership
migration after bootstrap and before ordinary `dry-run`:

```bash
SSH_OWNERSHIP_CONFIG="$HOME/.config/vpn-provision/ssh-ownership.json" make migrate-ssh-ownership
```

The same target accepts `mode: check` for a read-only preview, then
`mode: deploy` for the bounded transaction. The private input file must be mode 0600
and contain exactly `schema_version: 1`, `mode`, one `inventory_alias`, absolute
`inventory_path`, `known_hosts_path`, `contexts_path`, and the current checkout's
`source_revision` and `deployable_digest` from `scripts/deploy-source-identity.sh`.
The contexts file is the same private per-alias JSON used by ordinary deploy.
Migration requires the installed recovery generation and fresh strict SSH/SFTP
proof on both public and Tailnet paths before confirmation. It preserves the
effective SSH policy; the later baseline transaction applies desired hardening.
Do not manufacture socket contexts to pass deployment readiness. On disposable staging,
create the cleanup manifest before either installer. Unset the enrollment
key before ordinary `dry-run`/`deploy`, which now reject it.

Run the installer serially in an exclusive maintenance window. Ordinary
deployment never installs or repairs this capability implicitly. Before its
first site-playbook write, the deploy controller uses the same frozen strict
transport to require the exact local bundle generation, root-owned recovery
state and lock, a strict `idle`, `committed` or `rolled_back` dispatcher status,
and successful installed-unit readiness. Missing, stale, nonterminal or unsafe
recovery state fails closed before Ansible.
See [RUNBOOK-rollback.md](RUNBOOK-rollback.md#ssh-ownership-recovery-foundation)
for the installer boundary. A successful source or check-mode preflight is not
staging, reboot, disconnect, VPN-path or production acceptance.

If `dry-run` shows changes you didn't expect, **stop**. Investigate.
`deploy` refuses a dirty checkout so the live manifest can name an immutable
source revision. The parity gate compares both that exact revision and the
deployable-path digest. Even a documentation-only commit requires a reviewed
deploy before live source parity can pass; do not rewrite manifests by hand.
Don't push. The most common cause is a forgotten edit on a different
branch, or a role that's accidentally redownloading the binary because
the version pin moved.

Both commands freeze the canonical `ansible/inventory/generated.ini` once.
An empty `ANSIBLE_LIMIT` selects every `vpn` host; exact host aliases,
canonical cohort groups such as `vpn-p1-web`, and comma unions are accepted.
Globs, intersections, exclusions, external pattern files and unknown names
are rejected. `HOSTS`, `ENV` and `PROVIDER` do not independently narrow this
inventory selection. Approved `ANSIBLE_EXTRA_VARS_FILE` inputs still require
an explicit limit and apply before readiness.

All selected keys, known-host pins and private inputs are checked before any
SSH operation. The default pin file is `~/.ssh/known_hosts`; override it with
`INSPECT_KNOWN_HOSTS`. Deployment uses strict host-key checking, no ambient SSH
config, proxies, agent or multiplexed sessions. It does not enroll keys or
migrate SSH. The separate Terraform `make wait` command retains its first-boot
policy. Bootstrap errors and session/deadline failures stop the entire selected
deployment without printing raw cloud-init output.

Both `dry-run` and `deploy` require `DEPLOY_SSH_CONTEXTS_FILE`, a same-owner
mode-`0600` JSON mapping whose keys exactly equal the selected inventory aliases.
Each value contains 2–8 distinct socket-owner contexts captured for that node:

```json
{
  "vpn-p0-node-a": [
    {"user":"deploy","host":"operator-a","addr":"198.51.100.10","laddr":"192.0.2.10","lport":2222},
    {"user":"deploy","host":"operator-a","addr":"100.64.0.10","laddr":"100.64.0.20","lport":2222}
  ]
}
```

Every context must use the effective SSH port, and its `laddr` set must equal
the node's literal public and management IP addresses exactly. A missing,
hostname-only, duplicated or unrelated management transport refuses locally;
the controller never degrades confirmation to the public path alone.

`deploy` additionally requires `DEPLOY_PROMOTION_CONFIG_FILE`, another
same-owner mode-`0600` JSON mapping with the same exact alias set. Each value is
the singular schema documented in
[PROTOCOL-LIVENESS.md](PROTOCOL-LIVENESS.md#decision-and-promotion-behavior).
The controller writes private per-node copies and validates every copy locally
before the first readiness or SSH operation; it then runs the exact-node proof
only after that node's new SSH configuration is reachable over both public and
management transports. A failed proof, stale receipt, or identity mismatch
rolls back that node and stops the fleet.

The final deploy-only input is a same-owner mode-`0600` JSON mapping with the
same exact alias set. Each value is a distinct absolute path for a new private
failure receipt beneath an owner-controlled mode-`0700` directory. The paths
must not exist before deploy, and same-directory filenames must not differ
only by case or Unicode normalization. If the controller handles an SSH baseline
failure, it creates one mode-`0600` receipt containing only a fixed categorical
reason; Ansible remains `no_log` and public output remains generic. A successful
deploy leaves the path absent. Never reuse or delete an existing receipt to
make a retry pass: configure a fresh path. If the SSH baseline task fails but
the expected receipt is absent, treat that transaction outcome as unknown and
inspect retained controller/guest state. Receipt absence says nothing about a
failure elsewhere in Ansible or deploy. The receipt is diagnostic only and is
never protocol or deployment acceptance evidence. `dry-run` neither requires
nor writes this mapping.

Do not put addresses, identities, probe receipts, or credentials on the command
line. The private mapping files are operator inputs and must remain outside the
repository. A successful local config preflight is not live VPN evidence.

### Ordinary re-deploy recipe

Use this only after the recovery/bootstrap/ownership prerequisites above are
satisfied and all three private mappings have been prepared for exactly the
selected alias. Review the promotion inputs and choose fresh failure-receipt
sink paths before starting. Replace the example alias and paths with your
reviewed inputs; do not create empty mappings to satisfy preflight. Commit the
reviewed source change first: `deploy` requires an immutable clean checkout.

```bash
deploy_alias='vpn-p0-node-a' # Replace with the exact inventory alias.
export ANSIBLE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/vpn_deploy"
export DEPLOY_SSH_CONTEXTS_FILE="$HOME/.config/vpn-provision/ssh-contexts.json"
export DEPLOY_PROMOTION_CONFIG_FILE="$HOME/.config/vpn-provision/promotion-configs.json"
export DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE="$HOME/.config/vpn-provision/ssh-baseline-failure-receipts.json"
unset TAILSCALE_AUTH_KEY

(
set -e
make decrypt           # writes the configured SECRETS_FILE, mode 0600
make validate          # gitleaks + lint must pass
make dry-run ANSIBLE_LIMIT="$deploy_alias"
)
```

Continue in the same shell only after the preflight block succeeds and you have
reviewed every changed line. Stop and investigate unexpected changes.

```bash
(
set -e
make deploy ANSIBLE_LIMIT="$deploy_alias"
make verify ANSIBLE_LIMIT="$deploy_alias"
make source-drift ANSIBLE_LIMIT="$deploy_alias" # Also run by deploy/verify.
make clean
)
```

Each subshell stops on a failed command. Do not run the deploy block after a
failed preflight.
Run `make clean` when finishing or abandoning the operation, including after
a failed preflight.
The exported mapping paths are consumed by both controller commands;
`dry-run` uses only the contexts mapping and does not write failure receipts.

Readiness, convergence and the automatic source-drift check use the same
private inventory and transport snapshots. Canonical all/vpn/cohort variables
are loaded per host before runtime metadata, secrets and approved overrides;
ambient host/group variable files, callbacks and plugin paths are excluded.
Ansible also discovers plugins beside playbooks and roles independently of
configured paths: custom discovery directories there, symlinked role paths,
and `ansible/playbooks/roles` shadow roles are unsupported and rejected before
SSH. Keep extensions in a separately reviewed source change rather than these
ambient locations. `ANSIBLE_DEBUG` is rejected; normal Ansible check/diff output
remains visible. A dirty or changed source after waiting prevents deployment.

`infra-v1.0.0` also has a known check-mode-only failure in firewall SSH-port
discovery. Do not weaken or skip the gate. Confirm the failure matches the
record in [DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md#snapshot-operator-limitations)
and fix the source before treating `make dry-run` as green.

## Re-deploy after a Terraform change (instance type, zone, firewall)

```bash
make plan              # READ THE PLAN
# If it shows "destroy and recreate" on the server, STOP — that's
# infrastructure rollback, not config rollback. See RUNBOOK-rollback.md
# § "blue-green replacement".
make apply             # only if the plan was non-destructive
make inventory
# Re-establish the current recovery/bootstrap prerequisites above if the node
# or inventory changed; do not copy management overrides from an old snapshot.
make wait
# Continue with the ordinary re-deploy recipe above, including its private inputs.
```

`prevent_destroy = true` on `upcloud_server` blocks accidental destruction
in `terraform apply`. To deliberately destroy, run `make destroy`: the
wrapper lifts that lifecycle block through a temporary override file so
the tracked source stays clean.

## Add a new client device

```bash
SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml \
./scripts/new-client.sh --emit-uri laptop

make decrypt
make rotate-credentials      # re-renders xray/hysteria/awg configs
make verify
make clean
```

Hand the AmneziaWG private key (printed by the script) to the device
through a secure channel. Wipe it from your terminal scrollback.

## Selective deploy with tags

Prepare the private inputs and review the preflight in the
[ordinary re-deploy recipe](#ordinary-re-deploy-recipe) first. In that same shell,
use the selected exact alias and exported mappings for each tagged deploy:

```bash
# Just push a config-only change to xray
make deploy ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=xray

# Just refresh nftables
make deploy ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=firewall

# Just re-render fallback transports
make deploy ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=transport
```

The `tags:` field on each role in `playbooks/site.yml` enumerates what's
selectable. `always` tags (`baseline`, `firewall`) run regardless.

## Staging first

For disposable operator staging, select a reviewed
`ENV=ci-staging-<technical-id>` with its matching private tfvars for the
provider-specific Terraform commands. Keep that environment selected for the
node lifetime; the cleanup and recovery guards require the `ci-staging-` prefix.
Then:

1. Follow the [Terraform change procedure](#re-deploy-after-a-terraform-change-instance-type-zone-firewall)
   only through the reviewed `plan` and `apply` steps, one command at a time.
   Stop on unexpected replacements or drift; do not continue to its inventory,
   recovery/bootstrap or deployment steps yet.
2. For disposable staging, create the
   [UUID-bound cleanup manifest](CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup)
   immediately after apply and before either guest installer.
3. Resume inventory generation and `wait`, then complete the
   recovery/bootstrap/ownership prerequisites above for the exact staging node.
   Prepare the staging alias, secrets and all three private mappings, then use
   the [ordinary re-deploy recipe](#ordinary-re-deploy-recipe). Review its
   successful preflight before its separate deploy block. Verify the relevant
   client paths with a real client from the intended network; local preflight
   and source/CI results do not establish that acceptance.

For production, select `ENV=prod` and repeat the applicable Terraform and
deployment prerequisites with the production alias, secrets, promotion inputs
and fresh failure-receipt sinks. Run and review a new production preflight
before its deploy block. `ENV` selects the Terraform environment; it does not
narrow Ansible inventory selection. Keep the explicit `ANSIBLE_LIMIT` and
matching private mappings from the ordinary recipe for each environment.

Staging uses a different VPS, different REALITY keypair, different SNI
target, and ideally a different operator SSH key. Don't ever test new
Xray pre-release builds against prod users.

## What "verify" actually checks

`ansible/playbooks/verify.yml` asserts:

- cloud-init bootstrap marker present
- nftables config syntactically valid
- Xray config valid (`xray run -test -config`) and service active
- TCP/443 listening
- nginx -t passes (if P1 enabled)
- Hysteria service active and UDP/443 listening (if P2 UDP enabled)
- AmneziaWG interface up (if P2 AWG enabled)
- SSH refuses passwords and root login

If any of these fail, `make verify` exits non-zero. Don't sign off on a
deploy until verify is green.
