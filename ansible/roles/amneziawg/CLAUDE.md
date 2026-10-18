# role: amneziawg — P2 device-VPN with cohort obfuscation

## Design decisions

Retirement keeps exactly the two canonical shared-unit absence claims and the membership-record absence claim. These three bounded claims let repeated disable convergence use accepted readiness and firewall checks without publishing another runtime generation. Dynamic retired configuration claims and backups still prune after commit. Recovery accepts only the exact previous all-absence cleanup journal or the new bounded cleanup journal.

The fixed `awg-quick.target` has no service `MainPID` property. Normalize only that target's absent PID to zero in retained unit state; a missing service PID still refuses activation.

Source builds acquire immutable commit-selected executable files under `/opt/amneziawg/releases/`; they do not replace the accepted `/usr` executables. The complete consumer uses the shared inode journal with an AWG-only profile to publish binaries, shared units, private configurations and membership together. It keeps the AWG firewall open until runtime acceptance records a durable decision. Refusal restores the old firewall and exact runtime inodes before prior instance activation. A failed stop acknowledgement permits compensation only after inactive/failed state, PID zero and an empty recursive cgroup prove quiescence. Unconfirmed quiescence retains the journals.

The unit consumes the exact admitted configuration directory in `up`, `down` and `strip`; directories must be canonical absolute paths without systemd or shell metacharacters. Its read-only start admission rejects an interrupted candidate without a live publisher lock. Recorded legacy binaries need matching build receipt digests before upgrade adoption. Retirement can adopt only the owned unit/configuration membership it changes; it does not claim or replace an unproved binary. Disable and re-enable retain the same complete consumer contract. After final acceptance a private cleanup journal forgets only proven-absent retired paths and their exact backups, so repeated 32-instance renames do not grow receipt or unit authority without bound.

Post-activation retirement removes recorded obsolete configuration paths but
stops only names absent from the accepted instance set. Moving a configuration
directory must not stop a newly accepted unit with the same instance name.

AWG candidate activation retains the prior complete firewall file through service
acceptance. Failure restores it atomically before prior tunnels restart, so
changed peer claims cannot strand the restored addresses. A fresh host retains
a canonical default-drop baseline with AWG forwarding disabled. Foreign nft
tables and named timed-set membership remain outside this rollback.

Device peers carry typed `allowed_ips.ipv4` /32 and `allowed_ips.ipv6` /128
identities; routed peers declare `address_kind: routed` and explicit family
prefixes. Shared normalization rejects old scalar claims and family collisions.
MTU resolves instance > technical cohort > role default > 1420, with integer
bounds 1280–1420. Server, standalone, bundle and liveness use that value.
Before mutation the exact uplink needs an IPv6 default route with a global
source; RA routes require per-interface `accept_ra=2`. The role does not adopt
provider networking authority. Configuration activation retains complete prior
private configs and active/boot state, compensates failed candidates, and
retires obsolete recorded instances only after acceptance.


`amneziawg_secrets.instances` is the only server/peer authority, including one
instance. Controller normalization shares `effective_awg_instances` with
issuance, emission and liveness; instance values override cohort and role
network defaults. Top-level shadow peers/keys and an empty instance list refuse.
Private command stdin/output and complete instance facts stay under `no_log`.

The normalization entrypoint also supplies verification and watchdog. These consumers must inspect every configured instance and must not assume an `awg0` instance exists.

**Effective inputs are admitted before build or retirement** — shared
controller semantics validate bounded ordered junk, distinct headers, 1–15
character interface names, canonical key material and noncolliding peer CIDRs.
Device peers use host prefixes; broader routing needs explicit
`address_kind: routed`, which is not an issued device identity. Root/peer key
reuse and per-device collisions fail with categorical private diagnostics.
The existing S3/S4 zero guard and ownership-aware disable behavior remain intact.


A private bounded instance record owns retirement. Convergence stops and disables
only recorded obsolete interfaces before removing their exact configuration;
unrelated WireGuard/AWG instances stay untouched. Missing historical records
do not authorize a directory scan or deletion of unrecorded private config.
The unique amneziawg_role_enabled selector dispatches disable before build or
secret guards; immutable source receipts remain retained.

**Private instance records stay out of callbacks** — normalization and every service lifecycle loop over complete instances use `no_log`, including credential rotation. Verbose callback regressions use synthetic keys and PSKs.

**Pinned userspace AWG** — The deployed configuration supports the legacy
Jc/Jmin/Jmax/S1/S2 and scalar H1..H4 parameter set. It does not emit finalmask,
I1..I5 or AWG 3.1 options. Standard kernel WireGuard does not support this
obfuscation configuration. The separate source candidate does not change the
deployment contract.

Admission follows the pinned engine: `148 + S1` and `92 + S2` must differ.
Each header must equal its standard message type (`H1=1` through `H4=4`) or
exceed four; other low values would be silently rewritten by the engine.
All four effective headers must differ, so exported fingerprints describe the
actual wire values.

**Cohort profiles are config, not code** — `vars/cohorts/<slug>.yml` is the
SOT. New cohort = new file. See `docs/AWG-COHORTS.md`. Currently shipped as
a YAML file: `narrow-junk-sequential`. The broad-rule baseline (long junks
+ non-zero S1/S2 + random per-instance H1..H4) is encoded as the role's
hard-coded defaults — no separate cohort file needed, that profile is the
safe starting point on any unmeasured network.

**New cohort recipe** — add `vars/cohorts/<technical-slug>.yml` with the
obfuscation parameters, naming the slug after the packet shape (e.g.
`narrow-junk-sequential`, `wide-junk-random-headers`), never after the
carrier, ISP, or geography where it was measured. Add its row to
`docs/AWG-COHORTS.md` (junk sizes, init/response sizes, H1..H4 strategy), and
a `group_vars` comment if operators must know something non-default before
selecting it with `vpn.awg_cohort`.

**One peer key per device, never shared** — enforced by `scripts/new-client.sh`.
Reused keys break replay protection.

**Source refs require matching immutable commits** — the secrets example and
both bootstrap generators emit each source tag with its resolved commit SHA.
Each resolved commit gets a distinct, non-updating checkout path, so concurrent
controllers with different pins cannot mutate another build's source tree. The
role verifies the checkout still resolves to that SHA before building. Build
receipts bind the installed binaries to those resolved commits, so check mode
reports only actionable binary drift and never runs a compiler.

**Molecule runs the real role** — preparation supplies local synthetic Git
repositories, not installed binaries or receipts. File-only Git transport
prevents upstream fallback; a small C fixture requires the role-installed
compiler, and no-TUN tools exercise the real systemd unit. This proves role
ownership and idempotence, not upstream builds or tunnel traffic.

**arm64 S3/S4 floor is a cross-repo policy** — `contract/amneziawg-arm64-version-floor.json` records known-broken versions, tracked upstream issue states, and candidate/verified floors. A release claim only opens a revalidation issue; the role and client remain fail-closed until physical arm64 evidence establishes a safe floor.

An existing role-local shared unit without a bounded membership record refuses
reconciliation before retirement. Its owner must explicitly adopt exact members
or retire the historical authority; the role does not scan or delete unclaimed
interfaces. Fresh absence and recorded enable/disable transitions stay idempotent.

## What's done well

- **Cohort selection is explicit** — `vpn.awg_cohort` names a file under
  `vars/cohorts/`; there's no "auto" because cohort tuning is operator
  judgment, not a default. Empty string keeps the broad-rule baseline
  encoded in the role defaults — chosen deliberately, not silently.
- **Kill-switch in the emitted client** — `scripts/check-singbox-killswitch.py`
  validates the emitted bundle before it ships.

## Pitfalls

- **Fresh-host check mode cannot start an absent instance** — require a planned shared unit installation, then defer activation and restart until the real converge.
- **Fresh-host check mode has no Git yet** — apt only plans the Git dependency, so defer source checkout and commit attestation until convergence. Receipt inspection still reports installed binary drift in check mode.
- **AWG 2.0 client app version skew** — issue #2457: clients on AmneziaWG
  client v1.0.x silently fall back to vanilla WG handshake when the server
  uses 2.0 finalmask. Pin client version in `docs/CLIENT-NOTES.md`.
- **MTU selection is explicit** — a smaller configured MTU is not automatic
  path diagnosis. Verify sustained transfers on the actual constrained path.
- **Endpoint port reuse with Hysteria** — both use UDP. See `firewall/CLAUDE.md`
  pitfall; pick distinct ports.
- **`jc` of 0 is not "off", it's "junk count 0"** — older clients interpret
  this as a malformed packet. Use the cohort's recommended floor.
- **Issue closure is not proof of an arm64 fix** — amnezia-client #2582
  reproduced S3/S4 failure after an earlier claimed fix. Never weaken the
  guard from release notes alone; follow the tracker checklist.
- **Config changes restart instances, briefly dropping tunnels** — the
  complete consumer stops and starts owned units: `awg-quick strip`
  cannot apply address/route changes and aborts on inactive instances.
  Expect a seconds-long tunnel interruption on every peer/config change;
  schedule AWG config waves accordingly.
  Verified runtime publication and shared service/target unit changes use the
  same retained activation path, so unchanged private configuration cannot retain an older
  process binary or sandbox. Daemon reload precedes instance restart.
- **The tools build output is `src/wg`, not `src/awg`** — `/usr/bin/awg` is
  created by `make install`. Using the installed name as the source artifact
  makes every check-mode run report false drift.
- **Fresh hosts need a C toolchain for tools** — `amneziawg-tools/src/Makefile`
  invokes `cc`; install `gcc` and `libc6-dev` before the source-build helper.

Before retiring the shared target, query its actual inverse PartOf membership.
An active unrecorded member prevents any retirement; stopping the target must
never propagate into a foreign service even when its unit has a different name.
Fully owned target retirement removes both active state and boot enablement.
