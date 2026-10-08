# Runbook — deploy

Fresh or recreated nodes need provisioning and first enrollment before deployment;
start with `QUICKSTART.md` or the [disposable staging recipe](#staging-first).
An already managed node uses the [ordinary re-deploy recipe](#ordinary-re-deploy-recipe).

Run commands from the repository root in the pinned Bash session from the
[canonical workstation setup](../CONTRIBUTING.md#first-time-setup).

For the last verified release snapshot, provider-to-role mapping, recorded gate
results, and unresolved operator limitations, start with
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md).

## Acceptance scope and completion

Agree the exact nodes, changed layer, required protocols and resource/cost limits
before a live run. Existing authorization covers the named steps and bounded
retries and replacement nodes within those limits; obtain a new decision only
when the target, policy, cost or destructive scope exceeds the approved bounds.
Each attempt still revalidates its current source, exact resource identity,
host-key pins and private authority inputs.

- A documentation-only change uses local documentation/contract checks and its
  selected hosted CI checks;
  it does not require deploying unchanged runtime merely to advance a source SHA.
- An authorized runtime rollout requires the affected local gates and live evidence
  at the changed layer. Report the tested source revision and deployable digest
  separately from reused runtime evidence; unchanged digest does not make an old receipt current.
  Exact source parity remains a separate gate with its existing strict contract.
- Full P0/P1/P2 acceptance requires REALITY, XHTTP, Hysteria2 and AmneziaWG all
  returning `ok` against their assigned deployed nodes, with authenticated traffic
  and tunnel DNS; AWG also needs a fresh handshake. An all-four-profile disposable
  staging result proves that staging target, not the production fleet.
  Service/listener checks or `throttled` alone do not complete it.
- For a fresh Tailnet-managed node, complete the recovery foundation, positive Tailnet
  bootstrap, ownership migration and fresh dual-path SSH checks before ordinary
  deploy. Existing nodes reuse valid installed state; they do not reenroll per run.
- Recovery fault injection, quorum/OTP exercises, physical-device tests, every
  personal client and backup/restore drills gate a change only when that capability
  or acceptance scope requires them. State untested environments explicitly.
- If one account, network or runtime is unavailable, keep results from the other
  available validation lanes and identify the blocked claim. A failed full gate or
  required live check remains incomplete; another lane does not turn it into a pass.
- Keep per-device credentials private. Finish the applicable rollback and exact
  resource cleanup, retaining truthful evidence and naming any residual resources
  or credentials. A failed acceptance can finish cleanup without being called passed.

## Re-deploy after a config or secrets edit

When you've edited a role template, group_vars, or the secrets file, and
want to push the change to an existing VPS, prepare the selected node's inputs
before using the [ordinary re-deploy recipe](#ordinary-re-deploy-recipe).
The file paths in that recipe refer to prepared private files, not files the
controller creates for you.

For this existing-node workflow, select and export its reviewed private key
before any installer or inventory generation. For staging, use that workflow's
key selection below instead; reusable blocks preserve the selected key.

```bash
export ANSIBLE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/vpn_deploy" # Replace with this node's reviewed key.
```

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
The [autonomous recovery exercises](TAILNET-MANAGEMENT.md#disposable-staging-recovery-exercises)
are separate fault-injection tests when recovery behavior is in scope, rather
than prerequisites for every disposable acceptance run. When selected, use
separate one-use keys before positive bootstrap and retain their evidence.
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
deployable-path digest. A documentation-only commit can leave exact live source
parity stale even when runtime bytes are unchanged; report that separately from
[documentation acceptance](#acceptance-scope-and-completion). Do not redeploy merely
to close documentation work or rewrite manifests by hand.
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
: "${ANSIBLE_SSH_PRIVATE_KEY_FILE:?Select and export the reviewed key for this node first}"
export DEPLOY_SSH_CONTEXTS_FILE="$HOME/.config/vpn-provision/ssh-contexts.json"
export DEPLOY_PROMOTION_CONFIG_FILE="$HOME/.config/vpn-provision/promotion-configs.json"
export DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE="$HOME/.config/vpn-provision/ssh-baseline-failure-receipts.json"
unset TAILSCALE_AUTH_KEY

(
set -e
make decrypt           # writes the configured SECRETS_FILE, mode 0600
make validate          # gitleaks + lint must pass
make dry-run ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=
)
```

Continue in the same shell only after the preflight block succeeds and you have
reviewed every changed line. Stop and investigate unexpected changes.

```bash
(
set -e
make deploy ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=
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
The empty command-line `ANSIBLE_TAGS=` forces the full graph even if the shell
or `.fleet.mk` selects tags; preserve it on both commands.

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
: "${ANSIBLE_SSH_PRIVATE_KEY_FILE:?Select and export the reviewed key for this node first}"
make init              # initialize/select the chosen PROVIDER + ENV workspace
make plan              # READ THE PLAN
# If it shows "destroy and recreate" on the server, STOP — that's
# infrastructure rollback, not config rollback. See RUNBOOK-rollback.md
# § "blue-green replacement".
make apply             # only if the plan was non-destructive
make inventory
make wait              # cloud-init must finish before either guest installer
# Re-establish the current recovery/bootstrap prerequisites above if the node
# or inventory changed; do not copy management overrides from an old snapshot.
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

The controller currently forwards `ANSIBLE_TAGS` only for `deploy`; `dry-run`
checks the full site playbook even when that variable is supplied. It cannot
provide a matching tagged preflight. Use the
[ordinary full re-deploy recipe](#ordinary-re-deploy-recipe) for the reviewed
workflow, preserving its explicit empty `ANSIBLE_TAGS=` overrides. A filtered
check-mode capability needs a separate controller change before this runbook
can offer selective recipes.
The role tags remain defined in `ansible/playbooks/site.yml`; baseline and
firewall carry `always` tags and also run during a tagged deploy.

## Staging first

This disposable recipe uses **UpCloud only**: the linked UUID-bound cleanup
instructions describe its exact resource set and initial manifest inputs.
Read the [provider credentials and inputs](../terraform/providers/upcloud/README.md),
the [staging tfvars example](../terraform/providers/upcloud/environments/staging.tfvars.example)
and the [cleanup prerequisites](CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup)
before planning. Record the run's owner, maximum concurrent VPS/executors,
reviewed provider plan/storage, monetary ceiling, retry count and cleanup deadline
before creation. Stop at the first owner limit and allow time for guarded cleanup
before capability expiry; expiry does not cancel provider billing.
Prepare private `terraform/providers/upcloud/environments/<ENV>.tfvars`
for the selected environment, with the reviewed SSH public key and narrow
allowlist. Its `server_name` must match the exact hostname used by cleanup.
Explicitly set `enable_backups=false`, `additional_public_ip=false`
and initial `enable_provider_firewall=false`; the cleanup contract rejects
resources outside its owned set. Provider credentials stay in environment
variables, never tfvars.

Export the selections in the shell used for all commands below. Replace the
technical suffix and private-key path before running Make:

```bash
export PROVIDER='upcloud'
export ENV='ci-staging-<technical-id>' # Replace the technical suffix.
export ANSIBLE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/vpn_deploy_staging" # Reviewed key for this node.
```

Keep this environment selected for the node lifetime; the cleanup and recovery
guards require the `ci-staging-` prefix. An unexported shell assignment does not
reach Make, which otherwise defaults to production.
Then:

1. Follow the [Terraform change procedure](#re-deploy-after-a-terraform-change-instance-type-zone-firewall)
   from `make init` to create/select the new staging workspace, then only through
   the reviewed `plan` and `apply` steps, one command at a time.
   Keep the staging key exported above; its reusable steps preserve that selection.
   Stop on unexpected replacements or drift; do not continue to its inventory,
   recovery/bootstrap or deployment steps yet.
2. For disposable staging, create the
   [UUID-bound cleanup manifest](CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup)
   immediately after apply and before either guest installer.
3. Resume inventory generation and `wait`, then complete the
   recovery/bootstrap/ownership prerequisites above for the exact staging node.
   Prepare the staging alias, dedicated secrets and all three private mappings.
   For the first data-plane deployment, use the supported
   [disposable staging intent](PROTOCOL-LIVENESS.md#first-onboarding-during-a-disposable-staging-deployment)
   in the promotion mapping; prepare its executor with `make prepare-disposable-liveness`.
   It produces the sentinel binding and promotion config during `make deploy`.
   Then use the [ordinary recipe's](#ordinary-re-deploy-recipe) preflight and deploy
   blocks. For subsequent deploys, prepare promotion inputs for the current
   target/source identity from the produced config and use fresh failure-receipt
   sinks. Complete [four-protocol acceptance](#acceptance-scope-and-completion)
   and guarded cleanup; report the actual client vantage and any untested environment.

For production, explicitly export the reviewed production selections in the
shell that will run the new preflight:

```bash
export PROVIDER='upcloud' # Replace with the reviewed production provider.
export ENV='prod'
export ANSIBLE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/vpn_deploy" # Reviewed production key.
```

Repeat the applicable Terraform and deployment prerequisites with the
production alias, secrets, promotion inputs
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
