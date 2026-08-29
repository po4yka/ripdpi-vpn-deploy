## Context

The approved scope is restricted ordinary SSH over Tailnet and safe network rollout. The last coordinated assessment retained direct public access but did not prove working restricted Tailnet management; fresh live assessment is required before rollout. SSH source commit 91106e453c1b51301c85e6957e688d51e8bfd9ad validates only the 10/20 relationship; it neither migrates legacy fragments nor detects the 50-file duplicate. UpCloud activation and DNS rules are owned by the separate SEC-1787843484501357 change.

## Goals / Non-Goals

- Goal: add an independently verified management path, preserve working emergency access and make interrupted SSH/firewall changes recover automatically.
- Non-goal: replace SSH keys/authentication, rotate credentials, change SSH port, tune VPN transports, install an exit node, delete existing machines, or consolidate unrelated High work.

## Decisions

- Use ordinary OpenSSH over Tailscale. Preserve existing keys and strict public HostKeyAlias identity. Do not enable Tailscale SSH or agent forwarding.
- Install the pinned stable package from its signed distribution repository, without remote shell installers. Enrollment uses a bounded interactive registration flow; ephemeral credentials never enter argv logs, source, inventory or artifacts.
- Set accept-dns=false, accept-routes=false, ssh=false, netfilter-mode=off and no exit-node/advertised routes. Owned nftables rules explicitly scope tailscale0 SSH to approved controller addresses. Do not broadly accept the overlay interface or alter AWG forwarding/NAT.
- Tailnet policy is inspected before changes. ACL/grant permissions are additive, so an existing allow-all requires explicit narrowing for protected destinations, not simply another narrow rule. Preserve unrelated access and require policy tests for allowed controller and denied unapproved sources.
- Migration is a dedicated entrypoint, not a full baseline/site deploy. Stage the complete include graph; remove only confirmed duplicate managed scalar directives in 10/20/50. Refuse unknown layouts or unsafe paths. The initial migration accepts only the canonical top-level absolute drop-in Include and no Match or nested Include; safe unrelated fragments remain byte-identical. Compare sshd -t and full sshd -T results, including explicit -C contexts for direct and Tailnet connections, before and after activation. Snapshot every read configuration file and the complete fragment membership, not just the three mutated files, and reject intervening drift. Keep algorithm changes separate.
- Use a root-only transaction helper with prepare/apply/confirm/rollback/status, fixed owned paths, no arbitrary shell commands, short flock sections, fsync and generation/nonce checks. Snapshot bytes, mode/uid/gid and old/new digests. Require backups and the recovery timer before any config write.
- Recovery uses installed persistent units and boot reconciliation before ssh/nftables service acceptance, not a transient monotonic timer alone. Restore partial transactions idempotently; validate before reload. Durable committed state precedes timer cancellation. Corrupt receipts/backups or unexpected third-party bytes fail visibly and retain recovery evidence.
- Guest firewall replacement/rollback affects only owned inet filter/nat tables and preserves foreign tables. UpCloud cloud-rule activation uses an external controller with prior-rule snapshot, narrow allowed plan actions and independent reachability checks. Other provider firewall changes are refused until an equivalent adapter is tested; enrollment itself requires no newly exposed public port.
- Temporary staging cleanup uses a separate stdlib guard rather than weakening generic destroy. It creates a canonical mode-0600 schema-two manifest directly from exact private Terraform state bytes, binds the authenticated UpCloud API username, exact workspace/state digest, hostname, server UUID and computed root-storage UUID, and derives fixed target/escalation/hard deadlines at 36/44/47 hours. It accepts only a delete-only plan for the server, its server-bound firewall rules and Terraform's local SSH-port identity. Dedicated literal-safe Make goals create the manifest and destroy staging without accepting free-form destroy arguments. The command requires the manifest environment to match the exact destroy target and reserves the evidence inode before any Terraform action. Every private path is traversed component-by-component through held directory descriptors without following symlinks; release and rewrite recheck the exact opened inode. The private binary plan is opened once, unlinked, inspected and applied through the same inherited descriptor. After apply the guard verifies the exact API username before any resource GET, records categorical server/storage absence in the reserved inode and only then emits a redacted audit event; cumulative billing history is not misreported as an immediate invoice reversal. Guarded staging preserves the shared generated inventory. The guard never creates resources, changes provider policy, retries destructive actions or enables the blocked provider firewall.
- Strict connection proof disables multiplexing and agent forwarding, uses BatchMode/IdentitiesOnly/StrictHostKeyChecking/UpdateHostKeys=no and existing pins, and verifies remote transaction nonce and candidate digest. DNS and authenticated VPN probes must pass before confirmation and before moving to the next node.

## Contracts and ownership

- Ansible management role: package/configuration/enrollment and unit installation; baseline owns desired SSH hardening; firewall owns packet rules. Shared site and renderer edits remain serialized by primary.
- Controller script/Make entrypoint: exact host selection, policy verification, provider snapshot/rollback, fresh SSH proof and sequential promotion. No vpnd changes are required.
- Cloud-init: retain ssh_pwauth=false; normalize the known generated 50-file duplicate after bootstrap without deleting unknown settings or weakening first-boot auth.
- Existing public service address remains independent from the chosen management transport. Inventory generation preserves public listener and direct CIDR contracts; Tailnet overrides carry a verified public HostKeyAlias.
- No new long-lived secret is required for interactive enrollment. Any future unattended credential requires a separate SOPS schema change and scope review.

## Risks / Trade-offs

- Missing TUN/kernel support or overlay reachability: preflight and stage first; refuse promotion without a working second path.
- DNS or firewall takeover: explicit disabled Tailscale management flags plus before/after resolver, routing and owned-table checks.
- SSH race or reboot: durable state machine, timer/confirm locking and boot recovery; fault-injection tests cover every write boundary.
- Restricted ACLs could affect other devices: inspect full policy, preserve unrelated grants and test both positive/negative cases before registration.
- New dependency, policy authority and staging cost: explicit user-approved scope; authenticated Tailnet administration, verified actual staging cost/credit, an available approved executor and timely exact-resource deletion remain prerequisites. No top-up exceeding the approved total is permitted.

## Migration Plan

1. Complete and review source/tests locally; reuse canonical SSH task and UpCloud commit without importing unrelated branch history.
2. Obtain authenticated Tailnet administration and an authorized isolated staging target. Record its identity with the UUID-bound private cleanup manifest; no existing production node substitutes for destructive rehearsal.
3. Rehearse legacy migration and network rollback on staging using actual TCP SSH as deploy, custom-port coverage, controller disconnect, reboot, stale confirmation, corrupted backup refusal and repeated rollback.
4. Verify provider rollback independently from guest recovery. Validate plans reject replacements and loss of existing management/public listeners.
5. Enroll production nodes serially with direct access preserved. Verify strict SSH through both paths and actual VPN probes. Only then perform ownership migration, one node at a time.
6. Keep old public allowlists and host keys unchanged. Remove only the explicitly authorized temporary staging server after evidence and recovery cleanup; never label pending production checks complete.


## Source delivery slices

1. **SSH ownership planner:** a stdlib module in the baseline files directory reads the full safe configuration graph, identifies only the recognized packaged-main plus 10/20/50 ownership overlap, validates every ordered publication prefix with bounded OpenSSH subprocesses, and returns a bounded schema-two plan with old/new bytes, metadata and digests. It never changes live files, runs a service action, or changes algorithms. The positive known-layout path is mandatory; refusal cases alone are incomplete.
2. **Durable SSH activation:** a separate fixed-path root helper consumes its own locally generated schema-two plan, persists schema-two state under `/var/lib/vpn-sshd-transaction`, and publishes the exact operation-owned paths (`main+10+20+50` for ownership, `main+20` for baseline). It requires installed persistent recovery before apply. Wall-clock and per-boot CLOCK_BOOTTIME deadlines bound the same lease; clock backsteps cannot extend it. A boot identity binds unconfirmed state; reboot reconciliation precedes SSH service/socket acceptance. Restoration compares old/candidate digests and never overwrites a third-party generation. All snapshots and plan hashes are validated before any rollback write. State changes use atomic replace, file and directory fsync, and a single root-owned lock. Corrupt state is an explicit recovery failure, not an implicit success or deletion.
3. **Controller and installation:** a dedicated playbook installs the helper/units without importing baseline or site. The controller targets exactly one explicit inventory alias, reuses pinned host identity, refuses multiplexed connection proof, verifies direct and Tailnet access plus required DNS/VPN probes, then confirms the exact generation. No automatic provider mutation is hidden in this SSH entrypoint.
4. **Management and network rollout:** opt-in Tailscale configuration, reviewed full ACL policy, owned guest nftables transaction and separately tested provider rollback follow the SSH safety foundation. These are separate execution steps of the same feature and remain incomplete until implemented and observed. SSH-only rollback must never be described as complete network rollback.
5. **Acceptance:** local filesystem/OpenSSH tests and CI establish source behavior; actual two-image staging with strict TCP login, disconnect and reboot establishes recovery. Production is serial, only after those gates. Source success cannot close this feature.

## Shared file coordination

The coordinator owns inventory guards, the five existing `site.yml` pre-task `always` tags and the backup configuration entrypoint. This change uses its own playbook and does not edit those files. Makefile additions and integration to shared main are serialized. The original SSH policy task retains algorithm pinning and policy acceptance; its old normal-converge/git-revert migration assumption must be replaced by this explicit transaction before fleet use.


## SSH planner interface

`sshd_ownership.build_plan(config_dir, contexts=...)` returns a private schema-two `sshd-ownership` plan with `changed`, `read_set`, `include_inventory`, `files`, `effective` and `snapshot_digest`. The production caller fixes `config_dir` to `/etc/ssh`; only unit tests use another directory. `assert_snapshot(plan, config_dir)` rechecks bytes, metadata, membership and absence immediately before apply. `assert_effective(plan, config_dir, phase=...)` checks the installed full effective output against the explicit before/after phase using the same contexts. Errors are categorical `OwnershipError` values and never echo file contents.

The read set covers main plus every fragment using bounded no-follow reads; ownership has four ordered mutable records (`main`, `10`, `20`, `50`) and baseline has two (`main`, `20`). Each record carries existence, base64 bytes, SHA256, mode, uid and gid. Source inode/device metadata detects replacement before apply. Contexts are structured user/host/addr/laddr/lport records, never arbitrary argv. Full global output is always compared in addition to explicit contexts. Validation has time and output limits.

Bootstrap owns Port and four authentication primitives. The managed 20-file owns X11 and its existing hardening directives. Remove the four matching auth copies from 20, and remove X11 from 10 only after preserving its identical value in 20. A 50-file is absent or contains only comments/blank lines and a matching PasswordAuthentication no; remove that directive, not the file. Algorithms already in 20 remain byte-identical. Unknown managed-file directives, repeated values within one file, owned directives elsewhere, unsafe paths, active Match or noncanonical Include fail before live writes. The existing unmodified source templates are not claimed convergent with the migrated layout until their separately reviewed integration step is delivered.

The only recognized packaged-main ownership defaults are exact active `KbdInteractiveAuthentication no` and `X11Forwarding yes`, plus the packaged SFTP subsystem. Normalize those two shadowed defaults only when global and explicit connection policy is identical after every `main→10→20→50` publication prefix; reverse rollback traverses the same states. Preserve packaged SFTP, every unrelated byte and all existing metadata. Unknown, duplicate or unshadowed main ownership refuses before a plan is returned.

Boot recovery and the periodic timer worker are separate services. Boot recovery performs no service reload while ordered before SSH; a failed or missing initialized state blocks SSH service/socket startup and requires the already preserved provider console/rescue path. An empty first installation is the only idle case. Periodic recovery validates and reloads before a durable rolled-back receipt; it never uses RemainAfterExit.


## Atomic recovery installation

The recovery implementation is itself a recoverable boundary. Install three modules and three systemd units into an immutable, root-owned `generations/<sha256>` directory under `/usr/local/lib/vpn-sshd`. A fixed stdlib dispatcher/publisher selects `current` once, verifies the bounded generation and executes its immutable absolute module path with isolated Python. Merely executing through a mutable current path would still permit mixed imports. A shared bundle lock remains held across execution; publication takes its exclusive side and then the transaction lock, refusing any pending migration or candidate unable to read the existing terminal state.

Systemd unit links point through the controlled current generation; arbitrary symlinks, runtime overrides and unapproved drop-ins are rejected. All candidate files and hashes are checked and fsynced before one atomic current-pointer replacement. A durable install journal covers the interval through daemon-reload, persistent boot enable, timer start and actual readiness. New prepare/apply/confirm requests are refused until that journal is completed; recovery/status only use a previously validated terminal/empty state. Same-generation retry finishes interrupted installation, and old generations are retained. This installer never changes SSH configuration, listeners or keys.

A separate publisher lock serializes the whole installation. After durable
journal/current publication, release bundle and transaction locks before
activating recovery; otherwise the installer would make its own first timer
tick fail on contention. Within the journaled idle/terminal boundary, stop our
timer and then its periodic worker with separate bounded commands. Enable and
start the timer, whose Requires/After dependency starts the boot worker before
any overdue tick and retains its execution state against systemd collection.
Explicitly start the periodic worker and wait for completion. Neither boot nor
SSH is stopped or restarted, including generation upgrades. Require successful
completed executions, loaded pinned units and the active persistent timer, then
reacquire locks and revalidate generation, journal and terminal state before
finalization. An inactive never-executed service is not readiness evidence.
Only periodic lock contention returns a categorical deferred result with exit
75 for its next tick. The periodic unit accepts 75 without marking itself
failed, but readiness still requires exit 0 from a completed execution.
Boot contention remains a failure that blocks SSH listeners.

### Activation readiness without self-contention

An observed native transaction-lock contention made the periodic worker exit
75 and a later apply refuse before writing configuration. Reading the worker's
last result while holding that same lock makes normal activation invalidate its
own readiness condition. Keep the strict completed-execution requirement, but
separate fresh execution proof from the final capability check.

Apply first validates its identity, prepared state and deadline under the
transaction lock, then releases that lock while retaining the bundle shared
lock. Before starting any root service, validate the immutable generation,
loaded pinned units, absence of overrides and pending daemon reload, persistent
timer and strict boot recovery; this structural preflight must not reject the
previous coherent periodic busy result before it can obtain fresh proof. Only
valid completed exit 0 or known exit 75 permits a new execution; a real failure,
unknown state or future completion must refuse before start rather than be
erased by the next successful execution. Start the
periodic worker exactly once, with one aggregate monotonic deadline covering
validation, execution and the final fence; there is no retry loop. Read related
properties in one show per unit and require a fresh completed exit-0 execution
for this apply call. Unchanged cached execution metrics after a no-op start do
not establish fresh proof.
Keep its generation, boot identity and execution identity only in memory.

After reacquiring the transaction lock, revalidate the exact prepared state,
lease, full configuration snapshot and pinned recovery capability before the
first write. A worker that recovered an expired transaction between phases,
state replacement or any drift invalidates the proof. A later periodic busy
result or in-flight invocation is not itself proof: it may only be attributed
to this lock interval when the earlier fresh exit-0 proof remains valid and
the execution ordering is unambiguous. Compare systemd timestamps using
CLOCK_MONOTONIC, taking this lock's marker only after successful flock and
rejecting executions that started before it or have future timestamps. Keep
CLOCK_BOOTTIME solely for the existing lease semantics.
Unknown ordering, failed or never-executed boot recovery, real worker failure,
disabled timers or changed units always refuse activation. Standalone
installation readiness still rejects 75. No durable success cache, new
dispatcher action or change to public transaction receipts is introduced.

Recovery units create the standard privsep directory and a separate runtime validation scratch directory before OpenSSH checks. The scratch parent is root-owned and not group/other writable; every temporary child is 0700 and its config file 0600. Actual home and temporary paths remain readable for existing HostKey references. OpenSSH checks have a shared 30-second budget per full effective validation, within the recovery unit's 90-second total timeout. Local filesystem and mocked service tests do not constitute cold-boot or real SSH acceptance.


The fixed dispatcher is the installation trust root: ordinary bundle updates
require its bytes to match the reviewed bootstrap exactly and never replace it
under a running transaction. Engine, planner, adapter and units can upgrade
through the positive generation-publication path. A future bootstrap protocol
change requires its own explicit safe replacement design, not a compatibility
shim or a silent overwrite. The controller computes the six-file manifest from
fixed source paths, passes canonical bytes and the manifest digest, and rejects
enabled Ansible debug before any Ansible process. Child debug is explicitly
false even when the config file enables it.

The installation controller reads the operator inventory only through the
canonical non-executable selector, then gives Ansible a private single-alias
inventory. Host/group vars discovery is disabled for this standalone playbook;
its complete connection and manifest inputs are explicit. Child environment
inheritance is restricted to tool paths, home and locale so ambient tag filters,
Git routing, plugins or provider credentials cannot change installation. Shared
SSH arguments use portable `-o` options with OpenSSH path quoting, since Ansible
also passes them to scp and sftp. This does not change ordinary deployment or
backup group-variable loading.

### Baseline convergence through the existing transaction

The ordinary baseline must not recreate ownership overlap or publish SSH files
outside recovery. New plans and transaction state use schema two while the
generation packaging paths and fixed dispatcher remain unchanged; the planner,
transaction core and migration adapter are upgraded together. Add an explicit `sshd-baseline` plan intent;
`sshd-ownership` remains the separate policy-preserving legacy operation.
Prepare callers must name their intent; baseline never silently runs migration.
The existing 16-KiB request frame remains bounded. Baseline carries canonical
base64 desired hardening, decoded to at most 8192 bytes; ownership accepts no
candidate payload. Neither request may supply paths, owners or shell commands.

Baseline may publish only `sshd_config` and the managed 20-file. It requires
single-owner bootstrap authentication/Port in 10 and no active directives in 50.
Validate the complete graph before constructing a candidate. Main changes are
limited to commenting one recognized packaged SFTP subsystem when the candidate
provides the sole internal-sftp subsystem; otherwise preserve the existing SFTP
owner. Existing file metadata is preserved. A missing 20-file may be created
with mode 0644 and root ownership, but absence alone is not a first-boot signal.
Fresh bootstrap seeds X11Forwarding no in 20 and normalizes only the known
generated 50-file after cloud-init SSH processing, preserving first-boot policy.

Use the existing before/after policy digests with explicit validation phases:
apply/confirm validate after, rollback validates before. Membership checks admit
only the exact before/after/mixed graph of this intent. Rollback may remove a
new 20-file only after validating the entire mixed graph and its exact candidate
bytes and metadata; foreign changes remain a visible recovery failure.
Baseline policy changes do not weaken the equality rule for ownership plans.
The effective cipher, MAC and KEX algorithm sets must also remain unchanged in
baseline intent. Removing existing pins or introducing new ones refuses rather
than silently preserving custom values or applying algorithm policy; those
changes require their separately reviewed transaction.

Before generation activation, both current and candidate parsers must read the
unchanged terminal receipt. Test actual frozen/current parsers, not fake status.
Only after successful publication may a baseline transaction be prepared.
Downgrade to an engine that cannot read a terminal baseline plan must refuse
before changing current, journal or state, including after rollback.

Historical schema one is a read-only terminal boundary, not a compatibility
runtime. Accept only the exact canonical original three-fragment ownership plan
in `committed` or `rolled_back` state. `status` and recovery return the receipt
without changing its bytes; a later prepare first archives those exact bytes and
creates a new schema-two generation. Pending, applied, unknown or noncanonical
schema-one state refuses. Apply, confirm and rollback never mutate schema one,
and no path rewrites, defaults, converts or deletes it. The frozen old parser
must likewise refuse terminal schema-two ownership or baseline state before any
pointer, journal or activation change.

The role entrypoint delegates the exact-node operation to a controller that uses
fresh non-multiplexed SSH/SFTP and required DNS/VPN proof before remote
confirmation. Ordinary deploy first requires the exact installed recovery
generation, safe state and lock, strict `idle`, `committed` or `rolled_back`
status, and installed-unit readiness; it never auto-installs that capability.
The controller covers direct site-playbook callers, stops serial rollout on
failure, and avoids durable prepare in check mode. Source integration and tests
still do not authorize migration on real nodes without staged disconnect,
reboot, rollback and connection proof.
