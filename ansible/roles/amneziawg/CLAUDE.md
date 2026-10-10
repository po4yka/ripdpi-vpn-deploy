# role: amneziawg — P2 device-VPN with cohort obfuscation

## Design decisions

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

**Private instance records stay out of callbacks** — normalization and every service/handler loop over complete instances use `no_log`, including credential rotation. Verbose callback regressions use synthetic keys and PSKs.

**Userspace AWG, not kernel WireGuard** — AmneziaWG 2.0 in userspace is the
only path that supports the cohort obfuscation params (jc/jmin/jmax/s1/s2 and
2.0 finalmask/headers). Kernel WG doesn't.

**Cohort profiles are config, not code** — `vars/cohorts/<slug>.yml` is the
SOT. New cohort = new file. See `docs/AWG-COHORTS.md`. Currently shipped as
a YAML file: `narrow-junk-sequential`. The broad-rule baseline (long junks
+ non-zero S1/S2 + random per-peer H1..H4) is encoded as the role's
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
- **Client MTU is fixed, not per cohort** — `scripts/emit-awg.sh` and
  `scripts/liveness_profiles.py` write `MTU = 1420`; cohort files carry no MTU
  knob. A path that needs a smaller MTU needs a new, explicit emitter input.
- **Endpoint port reuse with Hysteria** — both use UDP. See `firewall/CLAUDE.md`
  pitfall; pick distinct ports.
- **`jc` of 0 is not "off", it's "junk count 0"** — older clients interpret
  this as a malformed packet. Use the cohort's recommended floor.
- **Issue closure is not proof of an arm64 fix** — amnezia-client #2582
  reproduced S3/S4 failure after an earlier claimed fix. Never weaken the
  guard from release notes alone; follow the tracker checklist.
- **Config changes restart instances, briefly dropping tunnels** — the
  handler uses a full `systemd` restart (not reload): `awg-quick strip`
  cannot apply address/route changes and aborts on inactive instances.
  Expect a seconds-long tunnel interruption on every peer/config change;
  schedule AWG config waves accordingly.
  Verified runtime publication and shared service/target unit changes use the
  same restart path, so unchanged private configuration cannot retain an older
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
