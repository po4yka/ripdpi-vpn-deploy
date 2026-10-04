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
before `ssh.service` can serve/authenticate ordinary SSH. Late recovery
must not treat tailscaled service readiness as backend initialization. It
recovery polls only `NoState` and `Starting` within one fixed 30-second
monotonic budget shared with its post-logout status check. Each query uses
the remaining budget and late replies refuse. Unknown, malformed and
authorization states refuse immediately; owned-identity verification remains
mandatory before logout; its status observation uses the same polling helper.
Normal enrollment/status callers do not poll.
The early worker also gates `ssh.socket`; the late worker must not depend on or precede that
socket, because its `sockets.target` ordering precedes tailscaled through
`basic.target`. The socket may listen after early recovery, but cannot activate
sshd until late recovery succeeds. Both workers share the same lock, nonce, snapshot,
and rollback state; neither may confirm or mint another transaction. Once
rollback starts, confirmation refuses even if the original lease remains valid.
Effective OpenSSH policy inspection uses syntax-validating `sshd -G` and
compares the complete dump. It must not depend on `/run/sshd`, which belongs
to the later `ssh.service`; `-T` adds daemon runtime tests and can fail during
recovery before SSH starts. Native regression checks compare cold `-G` with
warm `-T` policy in an isolated mount namespace without changing service state.
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

The subsequent inventory render takes one explicit private bootstrap handoff
path per host. It validates the path-list shape before Terraform calls, reads
each same-owner mode-0600 handoff without following its final path, and binds
the confirmation digest, alias, public address, SSH port and public/Tailnet
socket contexts to the selected Terraform node. Only the node address whose
IPv4 or IPv6 path was actually confirmed may become `ansible_host`; the
provider's public service address remains
unchanged. A raw Tailnet address is not an accepted interface. This lets
ordinary Ansible restore a public SSH source after controller egress changes
without bypassing its one-node dual-path transaction.

The ordinary protocol-proof gate also needs two staging-discovered runtime
preconditions in this change. The AWG sentinel copies the validated DNS server
list from the deployed role profile into a private per-run network-namespace
resolver and removes that resolver state on every exit, including partial
creation. Provider example listener contracts include nginx's TCP/80 redirect
listener so a deployment generated from the examples does not fail listener
parity before protocol proof.

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

Unbound retirement consumes the registered completed destruction, not an
unchanged pre-destroy state. Hold the resource-journal lock before the existing
nonblocking SOPS locks; require the registered manifest path/inode and its
reserved verified-absence path. The retained manifest still binds pre-apply
state. Freeze the current private empty state digest for the entire retirement
transaction and revalidate all inputs under the SOPS locks. Copied authority,
nonempty state, any onboarding output or another client generation refuses.
Prepared-executor retirement is a separate explicit operation after that
client receipt. It must verify the exact prepared manifest, VM marker,
configuration and unchanged Docker context, reject onboarding assignments,
serialize with binding, retain durable removal intent for interrupted retry,
and verify absence before publishing a private categorical receipt. It may
retire an expired prepared lease; it must never fabricate a binding.

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

- SSH recovery readiness observes an executing periodic worker within its
  existing 30-second budget and requires completed success from that exact
  invocation. Invocation, generation, boot, or boot-worker changes refuse;
  waiting never starts a worker or substitutes a cached result.
  Apply activation uses the same observation before requesting its one fresh
  execution. Completed success or known exit-75 contention permits that
  request; any other result refuses. Observation and fresh exit-zero proof
  share one 30-second deadline, followed by the existing lock fence.
- Primary owns all changes serially in this dedicated worktree. Shared writes
  to Makefile, task metadata, and board generation are serialized.
- Controller: `scripts/bootstrap-tailnet.py` and a bounded domain helper only
  if needed; reuse `fleet_inspection.py`, `bootstrap_readiness.py`, and source
  identity checks rather than duplicating transport logic.
- Recovery acceptance: one staging-only controller behind two fixed Make verbs
  reuses bootstrap validation, installation, enrollment and status. A dedicated
  child owns the pending enrollment and is killed with `SIGKILL`; the parent
  holds a private liveness pipe so an unexpected parent exit also terminates the
  child. The parent never receives a general fault selector and never calls
  confirm or rollback.
  Controller-loss waits through the durable lease and requires a new successful
  recovery invocation. Reboot requires a changed boot identity plus current-
  boot success from both recovery units. The harness adds no guest RPC or
  persistent privilege. Its evidence path must differ from the positive
  bootstrap handoff. A separate diagnostic path must differ from both. Atomic
  mode-`0600` success evidence contains hashes and categorical verdicts only,
  never addresses, raw nonce/capability material, keys, provider state, or
  remote output; successful publication is followed by a categorical canonical
  best-effort audit record. A reboot failure after observed SSH loss may instead
  publish a redacted `incomplete` diagnostic with only reboot-request, SSH
  down/up, recovery-status and unit-proof categories. It is not success evidence
  and never emits a passed audit record.
  The wrapper contract advances to schema 2 and requires both absent output
  paths. Schema 1 refuses before SSH; operators replace it by adding a fresh
  diagnostic path rather than relying on a compatibility mode.
- Guest: `scripts/tailnet_management.py`, its configure/check/recover entry
  points, recovery units, `ansible/roles/tailnet-management/`, and a dedicated
  `ansible/playbooks/bootstrap-tailnet.yml`.
- Firewall: `ansible/roles/firewall/` owns candidate rendering and known
  layouts; shared guest recovery primitives remain narrow and testable.
- Deploy: remove enrollment forwarding from `scripts/deploy-controller.py`
  and make the role verification-only during ordinary site convergence.
  Deploy mode also consumes a same-owner mode-`0600` exact-alias mapping to
  fresh private SSH baseline failure-receipt paths. The deploy controller
  freezes and validates every path plus its parent device/inode before
  readiness, rejects unencodable surrogate pathnames and same-directory
  case-only or canonically equivalent Unicode filename variants, rechecks every
  selected authority in a separate all-host pass before the first SSH,
  passes the selected
  path and frozen parent identity through the private per-host transaction
  variables, and keeps the Ansible task `no_log`. The baseline controller
  requires that same parent identity before accepting the no-follow output
  sink, validates it before the rest of the deploy request, and on handled
  failure or a successfully rolled-back interrupt publishes only an allowlisted final
  category with mode `0600`, no-clobber linking and data/directory fsync.
  Malformed prepare receipts enter rollback protection immediately: a valid
  generation and nonce drive bounded rollback, while an unusable capability or
  failed rollback becomes `rollback-uncertain-recovery-armed` before publication.
  A deploy prepare RPC that returns no receipt is likewise uncertain and cannot
  attempt rollback without a capability; check-mode preview remains non-mutating.
  Success writes nothing; an absent receipt after abnormal controller death or
  publication failure remains an unknown outcome. The receipt is diagnostic
  state only and never participates in confirmation or protocol proof.
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
   exercise the fixed controller-loss and reboot recovery verbs with a fresh
   one-use enrollment key for each, and require their redacted private evidence.
   Bootstrap Tailnet with another fresh key and verify both paths. Preview and confirm the separate
   SSH ownership transaction for recognized fresh Debian main-file directives
   before ordinary dry-run; retain full effective-policy parity and dual-path
   SSH/SFTP proof. Never simulate provider or live success with fixtures.
5. Use the handoff with ordinary dual-path deploy and exact-node VPN proof.
   Promote the provider firewall only after required guest probes, reissue the
   manifest, repeat acceptance, then guarded-delete and verify provider absence.
6. Proceed serially to the agreed live checks only after staging success and
   action-time confirmation of the applicable window. Retain public recovery.
   Bootstrap evidence alone cannot close the broader infrastructure objective.
