## Context

The current controller binds public and management socket contexts before
readiness and runs readiness through management. Tailnet enrollment is inside
the later site playbook. `install-ssh-recovery` establishes only SSH rollback
code. The existing Tailnet domain controller confirms immediately after local
postconditions; its timer logs out armed enrollment after controller death.
External SSH confirmation must become part of that transaction, not a second
receipt attached after local commit. See proposal.md for the staging manifest
ordering conflict.

## Goals / Non-Goals

- Goal: a fresh supported cloud image can establish real restricted Tailnet
  SSH via an explicit public-path transaction and then run ordinary deploy.
- Goal: preserve public recovery throughout installation, enrollment, loss of
  controller connectivity, reboot, and failed external confirmation.
- Non-goal: change provider firewall policy, Tailnet ACLs, host keys, sshd
  ownership, VPN profiles, credentials at rest, or deployment acceptance.
- Non-goal: automatically repair unknown firewall or Tailnet state, bootstrap
  an entire fleet, or retain a legacy login path inside ordinary deploy.

## Decisions

### Explicit public-path composition root

Add `make bootstrap-tailnet ANSIBLE_LIMIT=<exact-alias>` with a private
`TAILNET_BOOTSTRAP_CONFIG` file and environment-only `TAILSCALE_AUTH_KEY`.
Reuse the strict literal Make boundary, inventory selector, clean-source
identity, known-host freezing, bounded subprocesses, and recovery-readiness
checks from the existing installers. The config binds source revision and
deployable digest, alias, public address, existing key pin, effective port,
approved controller addresses, cleanup manifest for disposable staging, and a
new private output path. Unknown fields and ambiguous overrides refuse.

First authenticate the public endpoint and inspect actual cloud-init, sshd,
firewall, and Tailnet state. Check all inputs before packages or guest writes.
Use a dedicated fixed Ansible bootstrap playbook; do not add a bypass flag to
site.yml or invoke it with selected tags. Bootstrap does not require ordinary
deploy's protocol promotion configuration and cannot publish its source
manifest. After installation, verify the exact installed recovery generation
again before arming the access transaction.

### One durable access transaction

Extend `tailnet_management.py` to expose prepare/enroll/status/confirm/rollback
operations using its existing safe file, snapshot, lock, auth-file, and
recovery primitives. Update all callers; remove immediate local confirmation
from first enrollment. Retain a single state machine, not two independently
committing enrollment controllers. The transaction is armed before firewall
publication or login and binds target, bundle generation, nonce, baseline
digests, and a fixed 300-second enrollment/proof deadline. Installation may
take longer but occurs before arming and must leave components inert.

The timer must preserve a live unexpired transaction while short RPCs release
the lock; after expiry it recovers autonomously. Boot recovery uses two ordered phases of the same transaction. An early
worker, with default dependencies disabled, durably enters rollback before
restoring firewall files and effective policy ahead of nftables and
network-pre.target. It must not call tailscaled or synchronously start/stop
services whose jobs depend on the early worker. The late worker runs after
tailscaled and completes owned-identity logout and service-state reconciliation
before `ssh.service` can serve/authenticate ordinary SSH. The early worker
also gates `ssh.socket`; the late worker must not depend on or precede that
socket, because its `sockets.target` ordering precedes tailscaled through
`basic.target`. The socket may listen after early recovery, but cannot activate
sshd until late recovery succeeds. Both workers share the same lock, nonce, snapshot,
and rollback state; neither may confirm or mint another transaction. Once
rollback starts, confirmation refuses even if the original lease remains valid.
An interrupted early restore is replayable; a durable firewall-restored state
still requires late reconciliation. Confirmed records are never rolled back. Reboot and wall
clock rollback cannot extend a lease: bind boot identity and use a monotonic
deadline within that boot. A successful external proof authorizes a durable
confirmed transition; a lost reply after that commit is reconciled by status,
never by blindly logging out. Package rollback is not promised: pinned inert
packages may remain, but access-changing runtime state is restored.

### Firewall foundation is part of recovery

Reuse the firewall role's exact-source fragment and interface-separated SSH
grammar. A preflight classifies only two supported starting states: the clean
image's empty unmanaged ruleset, or a validated canonical repository-owned
nftables configuration. The approved empty baseline also permits exactly four
empty daemon tables (ip/filter, ip/nat, ip6/filter, ip6/nat), with no chains,
rules, sets, maps or extra attributes. They remain in the durable snapshot and
candidate/readback and are restored exactly; no general foreign-table adoption
is allowed. Preinstall, snapshot and recovery share this classifier. Active
ufw, foreign chains, unsafe includes, unknown
ownership, or pending network transactions refuse without disabling anything.

On the empty-image path, publish a minimal owned ruleset preserving the
approved public SSH policy and allowing only exact Tailnet sources on the
existing SSH port, with all other tailscale0 SSH denied. Do not open VPN ports
or claim their listener contract is installed. On an existing canonical path,
change only the approved fragment. Validate the whole candidate with `nft -c`
before applying. Snapshot exact file presence, ownership, modes, service
activation, and effective policy before publication. Recovery uses a validated
atomic full candidate, not a sequence of ad hoc rule insertions. Verify restored
policy and public SSH. Later ordinary firewall convergence replaces the
minimal foundation through its existing ownership contract.

Use one documented lock order for access, Tailnet, and firewall recovery; no
nested helper may acquire the same lock twice. Do not reuse the existing
network-promotion helper on a fresh image until its required main-file and
include grammar exist. Share parsing and safe-write primitives without
weakening its mature-node preconditions.

### External proof and safe handoff

After local enrollment succeeds, obtain both real Tailnet addresses over the
pinned public connection. Select the reachable approved family by actual
connection, never by generating an address. Use the existing strict fresh SSH
and SFTP primitives for public and management with the same original key pin.
Capture socket tuples on each connection and bind source and destination
addresses to the approved controller and selected node. A successful
`tailscale status` alone cannot confirm.

Before confirmation recheck generation, deadline, target, sshd policy, DNS,
default routes, and absence of Tailscale-owned netfilter chains. Write the
private handoff atomically at a new no-follow mode-0600 path: target/source
binding, observed addresses and socket contexts, and confirmation identity.
It contains no enrollment key or VPN credential. On a lost output write after
guest commit, rerun read-only proofs to regenerate the missing handoff; refuse
mismatched existing files. Never log out an already-confirmed identity.

### Manifest ordering without weaker cleanup

Create the initial manifest through the existing provider guard immediately
after state ownership is hardened. The current guard already accepts the
disabled provider firewall. After promotion or rollback, use a new path and
the same exact provider resource identities to bind refreshed state. Keep
creation-derived deadlines, previous artifacts, and every stale-state refusal.
Add regression coverage for disabled-firewall creation, post-transition
reissue, changed identity, unchanged deadlines, and pending destruction.
Do not manually edit manifests or permit a general state-digest exception.

Both provider guards use one private resource journal under the trusted
controller user's `~/.local/state/vpn-deploy/staging-cleanup/`. The key binds
provider, authenticated account and server UUID, independent of checkout,
state, manifest and evidence paths. One no-follow, inode-checked `flock`
serializes publication and every cleanup receipt operation. The durable
reservation remains exclusive between commands, including during Terraform.
An alternate path cannot establish a second manifest or reservation.
These operations have one controller owner; independent homes/controllers
must not operate on the same node without a shared authoritative journal.

Initial creation registers one manifest generation. Explicit
`staging-cleanup-reissue` requires the registered previous manifest, changed
state at the same path, unchanged resource identities and creation-derived
deadlines, and no outstanding reservation. A write-ahead publication intent
allows only the exact interrupted request to resume. Published manifests and
released receipts remain retained. Reservation/release recovery reconciles
the recorded evidence path; it never treats an unrelated missing path as
proof of release or retries a started Terraform apply.

This breaks the UpCloud and Vultr manifest versions and the reissue operator
contract. Update all callers; do not accept unregistered legacy artifacts or
add a compatibility bypass. Tests exercise two processes, alternate paths,
publication interruption, reservation loss and release interruption before
the exact-source local/hosted and authorized staging gates.

## Contracts and ownership

- Primary owns all changes serially in this dedicated worktree. Shared writes
  to Makefile, task metadata, and board generation are serialized.
- Controller: `scripts/bootstrap-tailnet.py` and a bounded domain helper only
  if needed; reuse `fleet_inspection.py`, `bootstrap_readiness.py`, and source
  identity checks rather than duplicating transport logic.
- Guest: `scripts/tailnet_management.py`, its configure/check/recover entry
  points, recovery units, `ansible/roles/tailnet-management/`, and a dedicated
  `ansible/playbooks/bootstrap-tailnet.yml`.
- Firewall: `ansible/roles/firewall/` owns candidate rendering and known
  layouts; shared guest recovery primitives remain narrow and testable.
- Deploy: remove enrollment forwarding from `scripts/deploy-controller.py`
  and make the role verification-only during ordinary site convergence.
- Cleanup: existing UpCloud/Vultr Make guard dispatch remains authoritative;
  change `scripts/staging-cleanup-guard.py` only if regression evidence proves
  a missing enforcement rule. No Terraform resource schema change is planned.
- Tests: extend existing Tailnet, deploy, firewall, cleanup, and recovery test
  modules/scenarios; add a controller test module only for the new boundary.
- Docs: update `docs/TAILNET-MANAGEMENT.md`, `docs/RUNBOOK-deploy.md`,
  `docs/QUICKSTART.md`, `docs/CI-REAL-DEPLOY.md`, and affected CLAUDE.md files.
- No vpnd, SOPS schema, third-party dependency, or production ACL changes.

## Risks / Trade-offs

- Firewall enrollment ordering can strand access: own both changes in one
  armed transaction and exercise native systemd/nftables recovery before VPS use.
- An early boot unit can deadlock startup: verify dependency ordering and real
  reboot recovery; unit text and mocked systemctl output are insufficient.
- Refusing foreign firewalls limits supported inputs: prove the real selected
  clean images work; refusal-only behavior never closes this feature.
- Separating bootstrap from deploy breaks credential forwarding: migrate every
  call site explicitly and test refusal of old inputs before external actions.
- A failed provider update may still refresh Terraform state: inspect and bind
  actual current state before guarded cleanup; never replay a stale manifest.

## Migration Plan

1. Add regression tests demonstrating the fresh-node dependency and preserve
   ordinary deploy's missing-management refusal. Implement each slice with its
   failure paths before broad validation.
2. Install pinned task tools; run targeted modules, affected Molecule scenarios,
   native Linux recovery tests, `build-gate -- make ci-fast`, and
   `build-gate -- make validate`. Observe exact-revision hosted CI before staging.
3. Revalidate action-time provider credentials, limits, image identity, SSH pin
   acquisition, Tailnet key, approved sources, and required reviewer gate. Use
   the existing authorized disposable budget and deadlines; no automatic refill.
4. Provision one isolated node, create cleanup manifest, install SSH recovery,
   bootstrap Tailnet, and verify both paths. Exercise controller loss and reboot
   with unconfirmed enrollment, verify restored public access, then repeat the
   positive bootstrap. Never simulate provider or live success with fixtures.
5. Use the handoff with ordinary dual-path deploy and exact-node VPN proof.
   Promote the provider firewall only after required guest probes, reissue the
   manifest, repeat acceptance, then guarded-delete and verify provider absence.
6. Proceed serially to the agreed live checks only after staging success and
   action-time confirmation of the applicable window. Retain public recovery.
   Bootstrap evidence alone cannot close the broader infrastructure objective.
