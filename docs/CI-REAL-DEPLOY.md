# Disposable real-VPS CI deployment

`real-vps-deploy` provisions one fresh UpCloud node per selected distribution,
executes the canonical recovery, Tailnet bootstrap, SSH ownership and deployment
controllers, verifies real protocol promotion, and destroys its owned resources.
`transport-reachability-matrix` runs the same lifecycle on a separate fresh node
for each selected profile. Both call `ci-disposable-deploy.yml`; its job uses the
protected `ci-real-deploy` environment with a required reviewer.

The default deployment profile is `p0p1p2` (REALITY, direct XHTTP and Hysteria2).
AmneziaWG, persistent backups and monitoring are outside this disposable profile.
A passed run establishes the selected profile's checks, not full production
or filtered-path acceptance. The direct runner baseline in matrix reports is
separate from the authenticated protocol probes used by promotion.

## Triggers and approval

- Manual `workflow_dispatch` selects the zone; matrix dispatch also selects a
  comma-separated profile list: `p0`, `p0p1`, `p0p1p2`, `p0p4`, `p0p5`.
- The `ci-real-deploy` PR label requests both workflows. Fork PRs are rejected
  before credentials or provisioning, including in the shared workflow.
- Real-VPS deployment also runs weekly. Missing configuration fails before
  provisioning; a selected profile never becomes a successful skipped job.
- Debian 13 is mandatory. Repository variable `CI_REAL_DEPLOY_UBUNTU24=true`
  adds a separate Ubuntu 24.04 deployment. Every selected template is required.

`make check-ci-deploy-gate` verifies the hosted environment still has a required
reviewer. No helper changes environment protections or Tailnet ACLs. Profile jobs
are serialized within the matrix; runs targeting the same profile/distribution
share a concurrency group. A workflow can run for up to 120 minutes because it
executes two destructive recovery exercises before the positive deployment.

## Protected environment configuration

Store these four secrets on the `ci-real-deploy` environment, not at repository
scope. GitHub Actions cannot read back their values after setup.

| Secret | Purpose |
|---|---|
| `UPCLOUD_TOKEN` | Dedicated account token authorized for disposable servers, encrypted storage import and exact cleanup |
| `CI_TAILSCALE_OAUTH_CLIENT_ID` | Scoped CI enrollment OAuth client |
| `CI_TAILSCALE_OAUTH_CLIENT_SECRET` | Its client secret; requires auth-key create/revoke capability for the configured tag |
| `CI_DEPLOY_CONFIG` | JSON configuration described below |

`CI_DEPLOY_CONFIG` has exactly these fields:

```json
{
  "tailnet": "example.test",
  "tag": "tag:ci-deploy",
  "templates": {
    "debian13": "00112233-4455-4677-8899-aabbccddeeff",
    "ubuntu2404": "00112233-4455-4677-8899-aabbccddee00"
  },
  "reality_target": "target.example.test:443",
  "reality_server_name": "target.example.test",
  "probe_url": "https://probe.example.test/204",
  "recovery_age_recipient": "<operator-age-public-recipient>",
  "research": {}
}
```

Use real minimal cloud templates, an owned REALITY endpoint that accepts the
configured TLS name, and an owned HTTPS probe returning status 204. The recovery
recipient is an operator-held age public key; its private key never enters CI.
The Tailnet policy must already allow ordinary OpenSSH from the CI controller's
tag to the guest's tag. The OAuth client's tag ownership must permit issuing
that tag and preauthorizing ephemeral devices. Neither CI nor the bootstrap
controller edits ACLs, approves arbitrary devices or uses Tailscale SSH.

P4 requires `research.dns_morph_bridge` with a real HTTPS `binary_url` and its
reviewed `binary_sha256`; there is no public upstream daemon release. P5 requires
`research.hysteria_realm` with reviewed `linux_amd64_sha256` and
`linux_arm64_sha256` for the role's pinned release. These prerequisites are
checked before provision. Both still prove P0 through the canonical sentinel;
their additional service checks are not P4/P5 client-path acceptance.

The old template, SSH-key and age-key workflow secrets are no longer consumed.
Each job generates its own admin SSH key, age key and per-device transport
credentials. It encrypts the CI secrets for canonical sentinel onboarding and
adds only that run's generated TLS certificate to the disposable runner's
trust store. TLS verification remains enabled for XHTTP and Hysteria clients.

## Authenticated first contact and deployment

1. Generate a unique SSH host key and private ext4 seed image. The pinned
   provider imports that image over authenticated HTTPS into encrypted storage
   and attaches it before guest startup. Terraform records only the local path,
   image digest and public identity metadata; no private key or signed upload
   URL is supplied through Terraform variables or cloud-init.
2. Cloud-init mounts the exact seed read-only, checks the host-key digest and
   installs the key before completing SSH bootstrap. The controller trusts
   that generated key before the first public SSH session. Provider console
   trust-on-first-use is not involved.
3. Record exact cleanup ownership, install recovery, and execute controller-loss
   and reboot recovery exercises with separate single-use enrollment keys.
4. Complete positive Tailnet enrollment and collect observed public/Tailnet SSH
   contexts. The deployment controller accepts dynamic approved sources only
   from the matching confirmed handoff, current source identity, exact node,
   pinned host key and typed CI cohort.
5. Migrate SSH ownership, run canonical check mode, then deploy. A dedicated
   loopback SSH sentinel on the runner uses the real pinned sing-box/Xray
   clients and observed activation metadata. Empty promotion mappings and
   invented success receipts cannot satisfy deployment.
6. Run verify and smoke checks. Matrix mode additionally records its direct
   runner and SNI baseline. Destroy the server, root and seed disks through
   the exact-state staging cleanup guard, and stop owned local services and
   revoke this run's enrollment keys.

Provider firewall activation remains a separate controlled lifecycle. CI starts
it disabled, then exercises the guest firewall; its Terraform listener contract
still must match every enabled runtime listener. The initial SSH CIDR is the
controller's observed public address, never a world-open management allowlist.

## Failure recovery and evidence

Only the categorical result, explicit matrix reports and an encrypted failure
archive are uploaded. Raw Terraform, Ansible, private keys, state, enrollment
material and subprocess logs are never uploaded in plaintext. Tool output is
captured locally with restrictive permissions, and Terraform debugging is not
inherited.

A normal cleanup must prove server, root storage and seed storage absent. A
partial apply with only a state-recorded detached seed can delete exactly that
seed; this does not prove that an unrecorded provider operation left no resource.
Ambiguous provisioning or failed cleanup remains a failed run with retained
recovery evidence. Cleanup defers repeated soft termination signals; a hard
runner termination can still interrupt cleanup and requires provider inspection. It never falls back to an unbounded destroy or removes state
on the assumption that deletion succeeded.

Decrypt `recovery.tar.gz.age` locally with the operator's age key, inspect the
private result/state and use the canonical cleanup guard. Keep decrypted material
outside Git. A workflow success requires deployment and cleanup; source tests,
mock-provider tests and native loopback/mount tests do not establish a live
provider deployment. Hosted credential setup and a protected live run are
separate acceptance evidence.

## Operator staging and cleanup

Use [acceptance scope and completion](RUNBOOK-deploy.md#acceptance-scope-and-completion)
to select the required deployment evidence and owner limits. The recurring CI
recovery exercises are not prerequisites for every ordinary deployment.

### UUID-bound operator staging cleanup

Authorized operator staging and the recurring CI workflow use the same
`ci-staging-*` exact-resource cleanup guard. Use a dedicated worktree so its local
Terraform workspace state is isolated. Keep the state file mode `0600` under a
same-owner directory that is not group/other writable. Keep the cleanup
manifest and post-destroy evidence in one operator-owned `0700` directory;
each file is a regular `0600` file. Do not put that private directory in the
repository. After the server exists, create the manifest through the canonical
Make goal directly from the exact local state before any guest installation,
bootstrap, deployment or destructive command. The goal authenticates `/1.3/account`, stores the exact API username
only in private artifacts, reads the exact state-bound server through
`/1.3/server`, and derives creation, target, escalation and hard deadlines from
the provider's integer `server.created` value at 36, 44 and 47 hours. Provider
credentials remain one ambient `UPCLOUD_TOKEN` (preferred) or one complete
`UPCLOUD_USERNAME`/`UPCLOUD_PASSWORD` or
`UPCLOUD_API_USERNAME`/`UPCLOUD_API_PASSWORD` pair; do not pass them as Make
variables or store them in tfvars. The guard canonicalizes exactly one mode and
never emits the authorization value. This binds the
exact API principal used for creation and deletion, not a parent billing
account, and does not claim that provider usernames are immutable identifiers.

Recovery fault-injection is a separate scope from ordinary four-protocol
acceptance. When testing recovery behavior, use the fixed exercises in
[TAILNET-MANAGEMENT.md](TAILNET-MANAGEMENT.md#disposable-staging-recovery-exercises)
with separate one-use keys before positive bootstrap; retain their private
artifacts. Bootstrap does not consume these artifacts or enforce their order.
An ordinary cancellation requests rollback and does not prove controller loss.

Set per-run owner limits for resource count, provider cost, retries and completion
and cleanup times before creation. The staging example selects 1 CPU/1 GiB RAM
and 20 GiB storage; verify the actual private tfvars and pricing for this run.
The local executor uses 2 CPUs/2 GiB RAM/10 GiB disk with a six-hour capability.
Provider 36/44/47-hour deadlines are cleanup authority boundaries, not a scheduler
or a billing cap. Begin guarded destruction before expiry; an expired manifest
cannot authorize a new destruction. Escalate unresolved cleanup before the owner
limit or guard deadline, rather than extending it by reissuing artifacts.

After creating the initial manifest, promote the UpCloud provider firewall in
two phases. The private tfvars starts with `enable_provider_firewall=false`; apply,
create the cleanup manifest, wait for cloud-init, install SSH recovery,
bootstrap Tailnet and migrate SSH ownership, then deploy the
guest stateful firewall and verify strict SSH,
DNS, outbound TCP/UDP and every required public listener. Confirm the live
kernel ephemeral range equals `provider_return_ephemeral_ports` (the repository
default is `32768..60999`). Then set `enable_provider_firewall=true`, inspect a
plan that updates only the same server's firewall flag, apply it, and repeat the
same acceptance. A server/storage/network replacement or any failed probe is a
stop condition. Roll back by setting the flag false on that exact node and
rechecking strict SSH; guarded cleanup is still required. After each authorized
same-node firewall update or rollback, explicitly reissue the cleanup manifest at a new
private path from the refreshed exact state before further guest writes or
destruction. Keep earlier manifests and evidence. Resource identities and
provider-creation-derived deadlines must remain unchanged; stale manifests
still refuse. Never reissue while a destruction reservation or apply is pending.

Both provider guards share the private resource journal under the trusted
controller user's `~/.local/state/vpn-deploy/staging-cleanup/`. Its identity is
provider/account/server UUID, not a checkout or artifact path. Use one controller
home for the complete node lifetime; do not copy artifacts to an independent
controller or select another home to recover an operation. The registry is part
of the private recovery data and must be retained with manifests and evidence.
Changing `HOME` as a Make command field is refused.

After the authorized Terraform state transition, use the explicit reissue verb:

```bash
PROVIDER=upcloud ENV="$ENV" \
STAGING_CLEANUP_PREVIOUS_MANIFEST=/absolute/private/path/cleanup-manifest.json \
STAGING_CLEANUP_MANIFEST=/absolute/private/path/cleanup-manifest-refreshed.json \
STAGING_CLEANUP_STATE="$STATE_PATH" \
STAGING_CLEANUP_HOSTNAME=vpn-ci-staging-<run> \
make staging-cleanup-reissue
```

The previous generation must be the registered current manifest, at its original
inode, and the refreshed state must remain at its original path. Initial
`staging-cleanup-manifest` refuses a previously registered node. Repeating an
interrupted publication must use the exact same request and output path; a
different path cannot bypass its intent. The new UpCloud v3 and Vultr v2
manifests require this journal; legacy manifests are not accepted or migrated
implicitly. Preserve legacy artifacts and resolve their existing lifecycle
before starting a node under the new contract.

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
`upcloud_firewall_rules.vpn` resource, `terraform_data.ssh_port`, and optionally
the single `upcloud_storage.ci_ssh_seed[0]` resource. A seed must match its
filesystem UUID and image digest. The guard extracts the owned UUIDs and calculates the state digest from those same state
bytes; an operator does not type either UUID or account identity into the
manifest. Every path ancestor is opened without following symlinks, and final
files are accessed relative to a held parent directory descriptor.

Destroy the staging environment through the guarded path. A verified inherited
lock descriptor holds the resource lock across the entire shell and Terraform
operation, so a second controller process cannot recover a still-running
reservation. Do not set `VPN_STAGING_LOCK_FD` manually. On retry after process
loss, recovery uses only the journaled evidence path; a started apply resumes
absence observation and never starts Terraform again. A released reservation's
receipt remains archived in the journal.

One authorization
step validates the same manifest/state inodes and bytes, rechecks its
authenticated account username, and reserves evidence before creating the
lifecycle override or allowing Terraform to refresh provider state. Plan
validation requires that exact reservation. Immediately before apply, the
controller rechecks the account, reservation, state and exclusive hard
deadline, then durably changes the same evidence inode to `apply_started`.
Only exact deletes of the manifest-bound
server, root storage, optional seed storage, server firewall resource and local SSH-port identity are
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
Success requires the exact server, root storage and optional seed storage to return their typed
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
credentials through their scoped cleanup path. Existing authorization for this
run's exact cleanup covers those steps; new authority is needed only when the
resource, credential or destructive scope extends beyond it.
