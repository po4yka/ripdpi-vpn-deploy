# scripts — subsystem design notes

Moved out of `scripts/CLAUDE.md` so the always-loaded folder notes stay small. Each section applies only to the scripts it names; `scripts/CLAUDE.md` still holds the conventions and pitfalls for every script.

## Task lifecycle — `tasks/taskctl.py`

**Task lifecycle history is first-parent canonical and revision-bound** —
`taskctl` resolves purged local tasks from committed terminal snapshots,
retains only validated `done` relationships in public graph output, and accepts
shared operational evidence only through reciprocal requirement/command
mappings at the recorded source revision. A completed lifecycle wholly inside
one merged lane may resolve only through one unambiguous, independently valid
lane; malformed first-parent state always wins and fails closed. Anchor merged
lanes at shared first-parent history: a newer main commit merged into a feature
branch must not hide the lifecycle preceding that update. Keep transition
scans anchored before the validation base, require the selected task to be
committed in `review` before preparing a `done` snapshot, batch history reads,
and never substitute current worktree specs or mutable archive discovery for
the immutable transfer revision. Apply the committed-review transition rule
monotonically across the terminal revision's first-parent project-config
ancestry. Permit only the legacy `doing -> done` form when the current checkout
proves the terminal commit is ancestral to its first local activation; a stale
merged lane otherwise inherits the active policy. A wholly unversioned peer
remains strict, and a descendant omission or downgrade cannot disable version 1.
Validate that monotonic policy ancestry before terminal-candidate iteration so
a policy-only commit cannot escape base-aware validation.
Evidence-transfer history starts only when a
snapshot itself requires OpenSpec; retain every later required snapshot across
task-mode or change-name transitions. Drop receipts bind the complete preserved
`DROPPED:` record set: live and historical terminal validation both reject
phantom, missing or duplicate step IDs before deletion history is accepted.

## Deploy controller and inventory — `deploy-controller.py`, `deploy-source-identity.sh`, `bootstrap_readiness.py`, `render-inventory.sh`

Fresh cloud promotion reuses recovery promotion's canonical native installer,
capability snapshots, epoch and committed-receipt retry. Its separate cloud scope
binds both canonical provider states and the sentinel's pinned live SSH identity.
It derives required profiles from the exact target cohort. It does not create
recovery journals or relax the fresh protocol gate. Disposable targets retain
their registered cleanup authority; local and CI executor contracts stay separate.

**Handoff ownership crosses the script boundary** — when changing bootstrap
output or inventory transport selection, inspect both ends of this chain:

| Contract owner | Consumer / coupling | Regression coverage |
|---|---|---|
| [bootstrap-tailnet.py](bootstrap-tailnet.py) publishes the confirmed handoff; [tailnet_management.py](tailnet_management.py) owns binding validation. | [render-inventory.sh](render-inventory.sh), `confirmed_tailnet_transport`, validates that handoff and selects `ansible_host`; Terraform still supplies `vpn_service_address`. [deploy-controller.py](deploy-controller.py) consumes the generated inventory. | [test_bootstrap_tailnet.py](../tests/unit/test_bootstrap_tailnet.py), [test_render_inventory.py](../tests/unit/test_render_inventory.py): publication, IPv6 proof, binding rejection and public service-address preservation. |

**Deploy identity follows deployable content** — `deploy-source-identity.sh`
hashes committed Git blob IDs and paths under `ansible/`, `scripts/`, and
`requirements.yml`. Do not hash `git archive` bytes: commit timestamps would
turn documentation-only commits into false live drift.

**Readiness and convergence share one inventory snapshot** — `deploy-controller.py`
resolves empty/exact/cohort/comma selections and calls `select_hosts` once.
Canonical variables load per host with real Ansible; frozen strict transport
records govern wait, site and source-drift without rereading original inputs.
`bootstrap_readiness.py` is shared with the Terraform first-boot adapter, whose
trust policy stays separate. Do not duplicate its deadlines or cancellation loop.
The public bootstrap probe reads the role's pinned Tailscale version from its
defaults before sending the read-only guest check. A failed status command is
resumable only for the dpkg-owned, exact-version CLI with no identity and an
inactive daemon; a `NeedsLogin` CLI needs the same package ownership and version.
The later Ansible prewrite guard independently checks both. The private config's
provider and environment must equal the inventory host's `provider`/`env`, so a
staging node cannot skip its cleanup manifest by claiming `prod`. Every
pre-write checkpoint reloads that manifest semantically, so a run that crosses
`expiry_at` during readiness or installation stops before the next host write.

**Vultr secondary IPv4 inventory is live-gated** — Terraform output proves allocation only. `render-inventory.sh` polls the primary SSH endpoint and publishes `honeypot_listen_addr` only after the exact IPv4 appears on a guest interface.

**Tailnet transport remains node-scoped** — after external bootstrap proof,
render inventory with private `TAILNET_HANDOFFS` aligned to `HOSTS` (`-`
retains the public SSH endpoint). The renderer derives the transport only from
the confirmed node-bound handoff after validating its binding digest and
public/Tailnet socket contexts. The Terraform public address still drives VPN
probes and the SSH transaction's distinct public path; host keys and socket
contexts stay pinned.

## Provider control plane, destroy, and staging cleanup — `destroy.sh`, `check-vultr-control-plane.py`, `ci-staging-*`

**Vultr control-plane access fails before Terraform** — state-changing and refresh-capable Vultr commands run a redacted authenticated API preflight through `check-vultr-control-plane.py`. Keep the key environment-only; classify exact-IP allowlist rejection separately from credential and network failures, and never print the rejected egress address or response body.

**Destroy is provider-aware and plan-verified** — `destroy.sh` maps each supported provider to a separate exact-resource guard; never merge their state schemas or credential paths. Operator `ci-staging-*` goals derive a no-follow mode-0600 manifest from the same state bytes, bind the authenticated account/provider/environment/workspace and provider creation time to fixed 36/44/47-hour deadlines, preserve shared inventory, and keep authorization, plan validation, pre-apply and typed absence in one journal-recoverable reserved evidence inode. UpCloud binds server/root storage/rules. Vultr binds instance, SSH key, firewall group, configured Terraform SSH port, provider-native decimal `for_each` rule IDs and an embedded instance root. The same opened, unlinked plan descriptor is inspected through the selected provider workspace and applied; post-expiry verification requires a fresh durable pre-expiry apply marker and is labeled late.

**Staging cleanup exports only the selected provider credential** — Vultr accepts one ambient `VULTR_API_KEY`; UpCloud prefers `UPCLOUD_TOKEN` and retains one complete primary or API-alias username/password pair. The Make boundary rejects command-line credentials before expansion, unexports the other provider's credentials, and keeps authorization out of tfvars and diagnostics.

**Observability cleanup has a distinct three-provider guard** —
`observability-staging-cleanup.py` is deliberately separate from the disposable
`ci-staging-*` guards. It is fixed to `ENV=staging` and consumes the exact
completed acceptance journal. `snapshot` authenticates UpCloud, Hetzner, and
Scaleway, derives the complete managed Terraform address and separately
queryable provider-identity sets from routed local state, and records a stable
delete-plan summary digest. `seal` accepts only a fresh separate approval bound
to the canonical snapshot digest, complete scope digest, source, deployable
generation, acceptance journal, expiry, and closed rollback/retention window.

`run` rebuilds all three plans and finishes every account, resource, state, and
delete-only validation before the first delete. Each plan lives in an
owner-only temporary directory, is opened no-follow, unlinked, hashed, and
applied through the same descriptor via `terraform-env.sh`. The temporary
lifecycle override exists only long enough to plan around the roots' existing
`prevent_destroy` contract. Provider absence is queried independently with
fixed provider URLs. Hetzner primary storage and firewall attachment are
implicit in their owning server/firewall lifecycle; separately addressable
resources remain separate checks. The final receipt exposes provider names and
categorical absence only. It permits a later local-retirement transaction but
does not itself delete operator-local recovery material.

A private receipt-side progress journal is published before the first apply and
advances monotonically through `pending`, `apply-started`, and `absent` for each
provider. Recovery re-authenticates the account and every provider identity. An
`apply-started` provider may be retried only when every direct resource is still
present, the complete frozen state bytes still match, the reviewed plan still
matches, and approval is still current; complete absence advances without a
second apply, while mixed provider state remains an explicit manual-inspection
refusal. Pending providers are never destroyed after approval expiry.

**Observability acceptance advances one fixed row per process** —
`observability-staging-acceptance.py` binds exact staging aliases, source
identity, private inputs and separate per-row approvals in a canonical
manifest. The private journal records the current row before mutation; a later
invocation restores an interrupted row or reconciles its already-published
receipt, then stops. Live rows use only embedded actions: fresh central metric
queries, the real one-hour critical lifecycle, fixed service/provider loss and
restore, forced primary canary, component rotation, categorical old-token
rejection, exact rollback and TSDB-preserving component removal. Terminal state
is reduced to the cleanup journal schema and still requires owner-confirmed
primary/secondary observations.

**Observability staging inputs are created before external mutation** —
`prepare-observability-staging.py` is a local-only, no-clobber preparer. It
binds the fixed controller rows from a clean protected-main source, generates
task-scoped SSH, age and short-lived PKI material, encrypts runtime and retained
CA authority documents directly with SOPS, and leaves approvals, provider
binding, old-material, rollback and role-variable inputs deliberately
non-authoritative. Existing Telegram bot/destination values enter only through
a same-owner mode-`0600` canonical file; the preparer never creates or probes
them and never prints private paths or values. Plaintext SOPS materialization is
an explicit second command into the same mode-`0700` root. Path traversal is
symlink-free and requires current-user/root ownership at every ancestor;
writable ancestors must be sticky, while direct private parents remain
current-user mode `0700`. Creation and materialization use pinned directory
descriptors and final inode-binding checks so an intervening pathname
substitution cannot receive secrets or be reported as the prepared root.

## Client emission — `emit-bundle.sh`, `emit-singbox.sh`

Xray pin parity reads exactly one repository-pin heading. Upstream Latest is
a separate release fact and never authorizes promotion or bypasses staging.

AWG delivery uses bundle version 2 and the named range/signature profile. Header values are canonical strings; signature programs retain their exact supported tags. Source admission requires the reviewed source pair for ranges or signatures. Standalone native configuration omits the JSON profile marker. Keep schema, fingerprint and paired consumer mirrors aligned; numeric legacy headers require a fresh export.

**Bundle topology is host-order independent** — `emit-bundle.sh` aggregates
split-hop ingress and realm metadata across every `HOSTS` entry. Never infer
client-facing topology from the first host; conflicting non-null realm IDs
must fail closed.

**Client formats are capability-separated** — `emit-singbox.sh` defaults to
official sing-box P0/P2 syntax and must pass the pinned upstream parser. Only
`emit-bundle.sh` selects the RIPDPI format that carries P1 XHTTP; never leak an
XHTTP outbound into the standard subscription.

Client emission excludes the neutral profile's public-site origin from its
semantic context: that placeholder does not represent the deployed private
override and is not part of a client socket contract. Controller preflight
admits the concrete served origin before host mutation. Emission still checks
the shared path grammar, selected transport relationships and actual endpoint
hostname/port policy; it never rewrites private origin inputs.

**Share emission reuses authoritative plaintext** — `emit-singbox.sh` reads
explicit `VPN_SECRETS_FILE` once through a no-follow, nonblocking descriptor
with current-owner/private-mode checks, then shares its JSON snapshot across
hosts. Invalid plaintext never falls back to SOPS; `SOPS_FILES` is ambiguous
with that shared input and is rejected. Direct script calls without plaintext
retain per-host SOPS inputs.

## Fleet inspection — `fleet-inspect.py`

**Passive inspection has no deployment prerequisites** — `fleet-inspect.py`
reads an explicit existing INI subset and sends the stdlib collector on strict
SSH stdin. Keep inventory parsing non-executable and local/remote reads bounded
and no-follow. The controller validates every output field. Do not add restic,
watchdog, readiness, Ansible or provider calls to fill absent evidence.

`fleet-status.sh` uses the same collector and provider/environment selection
mode without changing exact-name inspection. Its watchdog verdict is local and
requires a completed fresh invocation; client-path health remains unknown.
`fleet-rotate.sh` separately admits authenticated liveness for an explicit
survivor pool. Its Python controller owns strict plan parsing, immutable plan
identity and a serialized durable journal; the liveness adapter does not mutate
the standalone monitoring state or generate rotation approvals.

## Liveness sentinels, disposable staging, and retirement

**Intent preparation is an offline assembly step** —
`prepare-disposable-promotion-intent.py` reads a private predeployment JSON
configuration and invokes `disposable_promotion.validate_intent`. The isolated
Make goal accepts literal environment inputs before operator configuration is
parsed. Descriptor-based directory/file checks, exclusive publication and
private modes protect the draft and alias mapping. It opens no credential
input, creates no epoch/receipt and grants no deployment or cleanup authority.
Existing controller validation remains authoritative at deployment time.

**Sentinel formats follow required profiles** — request the canonical sing-box
emitter only for REALITY or Hysteria2 and RIPDPI only for XHTTP. AWG-only
resolves its existing AWG inputs without JSON emission. Unused documents are
absent; a required emitter failure still refuses before remote writes, with
native parsers, exact target identity and receipt reconciliation intact.

**Sentinel activation is generation-bound** — `liveness_generation.py` owns the
shared probe budget, fixed launcher, lock, rollback snapshot and committed receipt.
Onboarding publishes its local assignment only after exact receipt reconciliation;
active evaluator evidence never substitutes controller identity for server state.

**Disposable liveness execution is privately bound** — the one-shot consumer-
uplink executor uses a non-default Colima systemd profile with no mounts, address,
port forwarder, SSH config or Docker-context activation. A root UUID marker and
mode-0600 manifest bind installer/evaluator traffic to one profile and exact
report provenance. De-onboarding requires the already-bound guarded provider-
absence evidence before encrypted client removal, local assignment/config
removal and exact profile deletion; it never invokes the persistent AWG role.

**Disposable staging onboarding precedes SSH prepare** — a typed one-node
intent is validated and its explicit SOPS/age/key capabilities snapshotted by
the deploy controller before host writes. Keep the cleanup manifest at its
registered canonical path and revalidate its journal-bound inode at preparation
and finalization; a temporary copy cannot carry cleanup authority.
The baseline adapter publishes a
persistent binding epoch after data-plane roles, invokes only the canonical
installer and requires fresh evidence even for unchanged SSH policy. Exact
completed binding/receipt reuse avoids generating a conflicting executor
assignment on retry; unknown state preserves evidence and refuses.

**Unbound staging retirement is a separate encrypted transaction** — an
`issued` client whose executor never acquired binding/promotion state may be
removed only after the original disposable intent, canonical cleanup manifest,
verified provider absence and empty Terraform state agree exactly. Keep the
canonical `.new-client.lock` shared by all supported SOPS writers and the
retirement client lock across the final input check, Xray cohort-reference
cleanup, sibling SOPS edit, compare-and-replace, semantic reread and durable
receipt. Disposable onboarding retains the original SOPS path beside its
snapshot, binds its device, inode, and ciphertext digest during preparation,
then reopens and compares that exact source under the original project lock
before publishing;
duplicate YAML mappings refuse before mutation. Normal de-onboarding must not
inherit this recovery exception.
Retirement holds the registered resource journal before the nonblocking SOPS
locks and requires that manifest's reserved verified absence path. Its state
digest/inode belong to the genuinely changed empty post-destroy state and are
rechecked before publication and receipt. Prepared-executor removal then
requires the completed client journal/receipt and final ciphertext. Its global
profile lock and durable assignment/removal record serialize binding against
cleanup; verified directory identity permits interrupted stopped/absent retry
without inventing a binding or checking an expired enrollment lease.

### Probe scripts (`probe-*.sh`)

Client-side probes (`test-tls-policing.sh`, `probe-payload-throttle.sh`)
run from a filtered client path, NOT the VPS, and emit exactly one JSON
verdict object on stdout: `{"verdict":"ok|throttled|blocked|unknown|error",
"rtt_ms":<int|null>}` (+`error_kind` only on `error`). All diagnostics go
to stderr; non-zero exit reads as `error` to orchestrators. Emit `unknown`
(never `ok`) for indeterminate so unexpected-OK alerts aren't swallowed.

- **`probe-asn.sh` column order is the printf, not the header.** It prints
  5 TAB columns `IP ASN PREFIX COUNTRY ORG`; parse ASN with
  `awk -F'\t' '{print $2}'`, prefix with `$3`. Reuse it — never re-implement
  whois. Its exit 1 (Cymru unreachable) is an `error` verdict, not a crash.
- **Key verdicts by `AS<num>` + technical signature only.** The ORG/COUNTRY
  columns MUST NOT leak into slugs, filenames, state paths, or verdict
  output — no carrier/ISP/geographic brand names anywhere (root AGENTS.md).
  `probe-payload-throttle.sh` persists state at
  `${XDG_STATE_HOME:-~/.local/state}/vpn-deploy/payload-throttle/AS<num>.json`,
  written atomically (tmp+`mv`, `chmod 0600`) like `asn-drift.sh`.

**Protocol liveness is a two-part module** — `vpn-protocol-liveness.py` runs on a managed client-path sentinel and emits only redacted JSON; `protocol-liveness.py` pulls those reports over strict SSH and evaluates quorum. Only a fresh `blocked` result with a successful direct control may contribute to rotation. `unknown`, local dependency errors, authentication errors, stale output, and malformed output inhibit rotation.

**Promotion liveness is exact-node schema two** — every positive report binds
the exact inventory alias, canonical public-service-address digest, deployed
manifest digest, required profile set, source, runner and public profile. All
emitted variants for one sentinel target the same canonical server. The fixed
promotion proof accepts only exact `ok` profile evidence after the binding
epoch, including tunneled DNS and authentication plus a fresh AWG handshake;
its receipt exposes only the safe target subset and observation epoch.
For AWG, the isolated network namespace uses the canonical role DNS servers
through its private `resolv.conf`; inheriting an executor-only underlay
resolver can fail after a real authenticated handshake. The namespace resolver
is created before the probe and removed with the namespace.
The same fixed tool's `--validate-config` mode performs full local schema,
semantic and exact-node cross-link validation without probes or writes; a
multi-node controller must validate every split private config before the first
readiness or convergence call.

**Sentinel transport is separate from host identity** — an optional `ssh_transport_host` selects the directly reachable address while the required paired `ssh_host_key_alias` preserves pinned-key verification. This path disables inherited proxy and multiplexing options so a stale alias route cannot make healthy protocol evidence disappear.

**Endpoint variants are probed independently** — sentinel sing-box configs bind one loopback inbound per emitted endpoint, probe the variants concurrently within one bounded stage, preserve redacted per-variant verdicts, and collapse them into one logical profile verdict only after every variant is observed. A profile is alive when any endpoint succeeds; all variants must be blocked before the profile can contribute blocking evidence. Never put `urltest` startup selection in the measurement path.

**Scheduled protocol monitoring is stateful and standalone** — `monitor-protocol-liveness.py` persists redacted evidence and sends transition/recovery notifications without requiring a warm spare. Evaluator failures become an alerted `unknown` state, and the last successful delivery state survives quiet cycles so reminders remain daily. Notification credentials normally come from an owner-controlled `0600` materialized file; explicit environment overrides are reserved for isolated tests and operator-controlled one-shot runs. Unattended SOPS materialization goes through `decrypt-secrets.sh`, never a second decryption implementation. `install-operator-crons.sh` schedules it whenever `LIVENESS_CONFIG` is present and no warm-spare watcher owns the same probe cycle; failed alert delivery is retried rather than acknowledged.

**Managed cron preserves the validated operator toolchain path** — the generated block derives a compact `PATH` from the resolved Python, SOPS, Terraform, Ansible, and system tools so macOS cron uses the successful interactive toolchain without exceeding its line limit. Operator Python is ordered before `/usr/bin` because Apple's Python lacks the pinned modules. Explicit newline-bearing or oversized path input is rejected before touching crontab.

**Snell refinement is evidence-only** — `snell-refinement.py` runs only from an explicitly identified filtered client path, keeps all candidate proxies on localhost, interleaves exact-size direct controls, and persists schema-validated redacted reports beneath the XDG state directory. It never edits deployment, rotation, or route state; runtime, configuration, and authentication failures are `error`, not blocking evidence.

**Sentinel privilege is fixed-command only** — AmneziaWG needs a temporary network namespace, so onboarding installs one root-owned runner and one exact sudoers command. Never accept a config path or private key through the remote command line, and always delete the namespace in a `finally`/trap path.

**Real-VPS AWG evidence is executor-neutral, generation-bound, and transactional** — the local systemd timer is primary and the compatible workflow is optional. Both deploy an exact source archive, bind the v4 manifest to executor/entrypoint/invocation provenance and one signed client acceptance read through its validated file descriptor, require healthy direct TCP+UDP controls before an AWG failure is classified as product-facing, observe service/config generation changes, reject the old PSK, and commit or roll back the client/server pair. Old-key rejection passes only when both TCP and UDP fail; success of either is `OLD_KEY_STILL_ACCEPTED` and fails closed. Local installation snapshots a detached exact-SHA root-owned checkout, copies validated private hooks to immutable fixed paths, hardens the toolchain tree to root-only read/execute permissions, and shares one install/run lock. The executable validator, not the structural JSON Schema, owns correlation, timestamp and recurring-pair semantics. The locked state machine records the first valid PASS as pending and atomically publishes `latest.json` only after distinct ordered lane and client windows. Retained evidence spans two weekly intervals plus timer jitter; installing another exact source archives both prior-generation slots before starting a new pair. Fsynced state recovery cannot promote an invalid attempt. Valid failures stay versioned and malformed output is quarantined. Exit 75 means infrastructure unavailable, and only strict counters, enum verdicts, hashed identities, and digests may leave the sentinel.

## Tailnet — `tailnet-*`

**Recovery wrappers reuse shared owners** — for a staging retry or error-type
change, follow the shared implementation before adding wrapper logic:

| Contract owner | Consumer / coupling | Regression coverage |
|---|---|---|
| [bootstrap-tailnet.py](bootstrap-tailnet.py) owns input validation, installation, enrollment and pinned `_remote` / `_sftp` calls. | [staging-tailnet-recovery.py](staging-tailnet-recovery.py) loads that module and reuses its `deploy` and `tailnet` modules for the two fixed recovery scenarios. | [test_staging_tailnet_recovery.py](../tests/unit/test_staging_tailnet_recovery.py), [test_staging_tailnet_recovery_make.py](../tests/unit/test_staging_tailnet_recovery_make.py). |
| [bootstrap_readiness.py](bootstrap_readiness.py) owns bounded command/readiness execution and transport error types; [deploy-controller.py](deploy-controller.py) owns `require_recovery_foundation`. | Bootstrap and staging recovery consume both; transport failures and semantic refusals must retain their distinct types across these calls. | [test_bootstrap_readiness_io.py](../tests/unit/test_bootstrap_readiness_io.py), [test_staging_tailnet_recovery.py](../tests/unit/test_staging_tailnet_recovery.py): `_remote`, `_sftp`, foundation and reboot retry cases. |

**Recovery waits for backend initialization, not merely daemon readiness** —
the vendor service can notify readiness while its backend remains `NoState`.
Only recovery polls `NoState`/`Starting`, with one 30-second monotonic budget
shared by the initial status and the post-owned-logout status. Every query is
bounded by the remaining time, including rejection of a late terminal reply.
Malformed, unknown and authorization states still refuse immediately;
ownership validation, exact rollback and the SSH dependency remain unchanged.

**Tailnet firewall fragments have one canonical grammar** —
`tailnet-network-guest.py` validates and publishes the same schema-1 bytes as
the firewall role. The validator supplies the approved-source fragment for an
enabled first convergence; promotion owns later replacements. Empty typed sets
omit the `elements` clause because nftables does not accept an explicit empty
set expression.

**Tailnet rollback stays two-phase** — prior provider state is rolled back but
its receipt remains active until the exact guest transaction is rolled back.
Only then may the executor terminalize it. A retry observes an already-disabled
provider as idempotent and continues guest cleanup instead of replaying the
Terraform rollback.

**Staging recovery faults are two fixed deep operations** —
`staging-tailnet-recovery.py` reuses the bootstrap module's validation,
installation, durable enrollment and status implementation behind distinct
controller-loss and reboot Make verbs. A dedicated child reaches `pending` and
is killed with `SIGKILL`; a private parent-liveness pipe prevents an orphaned
paused worker after controller death. The parent has no confirmation or explicit
rollback path. Controller loss requires a fresh post-deadline recovery invocation;
reboot requires a new boot identity and current-boot success from both phases.
Both finish through pinned public SSH/SFTP and idle-state proof. The only
success artifact is atomic mode-`0600` redacted evidence at a path distinct
from the positive bootstrap handoff; a categorical `append-best-effort` audit
record follows publication. Reboot failures after observed SSH loss instead
publish a distinct atomic mode-`0600` `incomplete` diagnostic containing only
the reboot request, SSH down/up, recovery-status and unit-proof categories. It
is never success evidence and does not emit a passed audit. Do not deepen this
interface with a general fault selector or a new permanent guest capability.

## Observability — `observability-operator.py`

The monitoring role's private endpoint validator also runs before standalone
sender mutation and in the verification playbook. Both exporter scrape jobs use
its normalized endpoint. Literal loopback binds are accepted; Tailnet binds need
an exact explicit approval and local address fact. Custom ports and bracketed
IPv6 remain aligned across installation, sender configuration and verification.

**Sender and staging contracts have consumers outside their entrypoint** —
inspect these dependencies when changing a sender runtime or acceptance row.
The retained dedicated-staging harness consumes the runtime contract but does
not accept the current topology; see [current contract and task history](../docs/reference/observability-operations.md#current-contract-and-task-history).

| Contract owner | Consumer / coupling | Regression coverage |
|---|---|---|
| [observability_agent defaults](../ansible/roles/observability_agent/defaults/main.yml) and [templates](../ansible/roles/observability_agent/templates) define sender release inputs, flags, unit and queue metrics. The collector has a separate release input contract in [observability_control_plane defaults](../ansible/roles/observability_control_plane/defaults/main.yml); concrete test-only pins live in [fixture-contract.yml](../ansible/roles/observability_control_plane/molecule/enabled/tasks/fixture-contract.yml). | [observability-operator.py](observability-operator.py) consumes readiness; [observability-staging-acceptance.py](observability-staging-acceptance.py) consumes transport arguments and native queue metrics. | [test_observability_operator.py](../tests/unit/test_observability_operator.py), [test_observability_staging_acceptance.py](../tests/unit/test_observability_staging_acceptance.py), [test_observability_agent_render.py](../tests/unit/test_observability_agent_render.py), [test_render_snapshots.py](../tests/unit/test_render_snapshots.py). |
| The sender role also runs in the collector's co-hosted scenario. | [cohost-agent.yml](../ansible/roles/observability_control_plane/molecule/enabled/tasks/cohost-agent.yml) supplies its fixture inputs; [bounded-runtime.yml](../ansible/roles/observability_control_plane/molecule/enabled/tasks/bounded-runtime.yml) owns restart/backlog and resource-pressure proof. An agent-role-only run does not cover this consumer. | Control-plane enabled Molecule scenario; [test_observability_resource_bounds.py](../tests/unit/test_observability_resource_bounds.py). |
| [prepare-observability-staging.py](prepare-observability-staging.py) produces the private staging manifest; [observability-staging-acceptance.py](observability-staging-acceptance.py) owns `ACCEPTANCE_CHECKS` and terminal journal publication. | [observability-staging-cleanup.py](observability-staging-cleanup.py) validates `completed_checks` against its `COMPLETED_CHECKS`. Row changes must reach the cleanup consumer as well as the acceptance controller. | [test_observability_staging_cleanup.py](../tests/unit/test_observability_staging_cleanup.py), `test_cleanup_contract_matches_acceptance_terminal_rows`; [test_prepare_observability_staging.py](../tests/unit/test_prepare_observability_staging.py). |

**Observability lifecycle shares one exact-host controller** — its public Make
verbs remain distinct, while one bounded Python controller centralizes private
input validation, literal scope, strict SSH and one-role Ansible execution.
Initial `deploy` refuses an existing primary unit and never aliases `rotate`.
Topology schema 2 enrolls VPN capabilities plus one co-hosted collector and a
typed independent Kuma observer. Dedicated-host bootstrap is retired and
refuses before host access. `render` is strictly local Jinja rendering;
`validate` is syntax-only, and neither establishes host admission. `check`
requires explicit host-access confirmation. Runtime status includes the node
or pipeline/delivery push timers; healthy units never imply client-path proof.
The sender uses vmagent's `/ready` initialization endpoint, not Prometheus's
`/-/ready`. The retained staging queue row parses native counters without
renaming block or byte drops as sample counts and requires an outage-time
collector sample, not only a drained queue or newly advancing data.

**Private-IP PKI preparation is local and encrypted** —
`prepare-observability-pki.py` creates separate receiver and observer authorities,
verified IP-SAN leaves and distinct per-node client identities. Its no-clobber
output is a SOPS fragment plus retained revocation authority, not complete
deployment secrets. Never deploy the authority keys or infer host authorization
from successful preparation.

## Cloud-init acceptance — schema fallback and cloud-final restart harness

**Container schema checks keep inputs mount-free** — the cloud-init fallback
passes rendered YAML and the pinned public CA bundle through a private tar
stream to a digest-pinned image. APT uses HTTPS with peer/host verification and
fails on any index error; never add host mounts, plaintext mirrors, trusted
sources, or disabled TLS checks to make this CI fallback pass.

**Cloud-final restart acceptance is isolated and fail-closed** — the manual
harness builds digest-pinned Debian and Ubuntu systemd images in its own Colima
profile, exercises clean and interrupted PID1 restart cases, and deletes the
profile on every exit. A nonzero guest result never becomes acceptance; only a
bounded mode-0600 sidecar with categorical state and hashed invocation identity
may survive cleanup. This is container PID1 evidence, not a provider reboot.

## SSH recovery — `install-sshd-recovery.py` (`make install-ssh-recovery`)

**Recovery bundle ownership starts in the baseline role** — use the canonical
bundle and shared transaction controller when tracing an ownership change:

| Contract owner | Consumer / coupling | Regression coverage |
|---|---|---|
| [baseline files](../ansible/roles/baseline/files) own `sshd_migrate.py`, `sshd_transaction.py` and `sshd_ownership.py`; its [templates](../ansible/roles/baseline/templates) own the recovery units. [sshd_bundle_source.py](sshd_bundle_source.py), `bundle_manifest`, binds their immutable generation. | [install-sshd-recovery.py](install-sshd-recovery.py), [deploy-controller.py](deploy-controller.py), bootstrap and staging recovery consume that generation. | [test_sshd_bundle.py](../tests/unit/test_sshd_bundle.py), [test_install_sshd_recovery.py](../tests/unit/test_install_sshd_recovery.py). |
| [deploy-source-identity.sh](deploy-source-identity.sh) defines the source digest, exposed by [deploy-controller.py](deploy-controller.py), `source_identity`; [sshd-baseline-controller.py](sshd-baseline-controller.py) owns transaction RPC and rollback; [sshd_contexts.py](sshd_contexts.py) binds socket contexts. | [ssh-ownership.py](ssh-ownership.py) composes these owners, rechecking source before `apply` and `confirm` and proving both transports before confirmation. | [test_ssh_ownership_controller.py](../tests/unit/test_ssh_ownership_controller.py): source drift, dual-path proof and uncertain rollback; [test_sshd_baseline_controller.py](../tests/unit/test_sshd_baseline_controller.py). |

**SSH recovery installation has an early privacy guard** — the dedicated
controller rejects enabled Ansible debug before inventory processing, forwards
`ANSIBLE_DEBUG=false` to override config defaults, and validates exact aliases
and clean source before Ansible. It isolates the selected alias from external
host/group vars, allows only tool/home/locale environment inheritance, and uses
portable strict SSH options for transfers. Caller fields remain literal data
through Make and argv; no general site/backup task runs during installation.

**Fresh-node ownership is a separate operator transaction** —
`ssh-ownership.py` requires the installed exact bundle generation, a clean
source for mutation, one pinned inventory alias, and real public plus Tailnet
contexts. It previews the policy-preserving ownership plan or applies it with
fresh strict SSH/SFTP proof on both paths before confirmation. A failed proof
requests rollback; an uncertain rollback remains an explicit refusal.

## Probe matrix — `probe-matrix-driver.py`

**Probe-matrix drivers keep secrets file-bound** — `probe-matrix-driver.py` reads an owner-controlled `0600` target profile, writes Xray configs only inside `0700` temporary directories, and sends MTProxy requests to the pinned Go helper on stdin. Keep credentials out of argv, environment variables, diagnostics, and reports; only same-tick failures with a healthy direct control can become `blocked`.

### Selected Naive export

`naive-client.py readout` requires `--output`; `make naive-readout` requires
`OUTPUT` and preserves its literal argv value. Selected credentials stay in a
new owner-only artifact rather than terminal output. Validate private destination
authority before encrypted reads, reject existing entries, verify pinned identity
after writing, and remove only the created inode on failure. No mutation operation
accepts a readout output flag.

## Private client delivery identity

The renderer is `client_payload.py`; `emit-singbox.sh` and `emit-bundle.sh`
dispatch without staging plaintext. Issuance hashes the same canonical JSON it
publishes. HMAC-SHA256 is domain-separated by version, device, format, recorded
options and exact AWG bindings, including the full enrolled peer public key
even when export uses a device-private-key placeholder. The 256-bit key and 128-bit key-bound generation
live in `client_delivery_identity` inside SOPS; neither the key nor keyed digest
is printed. Only issuance creates missing authority. Explicitly rotating both
key and generation invalidates prior comparisons until redelivery; inspection
with unavailable, malformed or replaced authority reports unknown unchanged.
A delivery records expiry, format, hosts, cohorts, AWG host, UTLS override and
private source selectors. Changes to consumed values are stale; unrelated
metadata, another device's values and SOPS re-encryption remain current.
The old source/output identity is no longer accepted; redeliver to migrate.

Publication callbacks receive a marker for the first external mutation attempt.
SSH acknowledgement loss, a later write failure or failed local replacement
retains an explicit uncertain-publication result requiring reconciliation.
Local commit/durability uncertainty remains a separate category; both outcomes
keep private error details out of diagnostics, including during interruption.

## Operator boundaries — cross-cutting decisions

Taskctl validates the exact OpenSpec tool version and reviewed generated-skill hashes together. Dependency security updates change the version pin without overwriting repository-customized workflow skills or their generation provenance.

Executable recovery admits one exact UpCloud replacement with a surviving
separate publisher. Private durable intent precedes external operations; resume
reconciles account, unique resource, state and exact saved-plan postconditions.
Provider credentials reach only provider operations. Frozen private inputs bind
canonical management and deployment, and a real post-data-plane sentinel receipt
creates the promotion epoch. Never invent applied_at, auto-import an ambiguous
resource, replay an uncertain apply blindly or claim device readiness from
publication alone. The Make recovery entry point preserves literal inputs and
runs before operator configuration is parsed.

Device lifecycle admits the complete inventory and every configured or retained
publisher. Overlapping fleets lock every authority in sorted order, regardless
of journal host. Revocation binds immutable encrypted intent to the canonical
runtime forward-only barrier through a private typed override; progress updates
cannot change that digest. Native-only delivery exports official AWG/Naive
configuration without a published token.
Its encrypted intent freezes generated credentials, grant CAS bytes, source
identity and recipient output before mutation. Canonical role rotation and
private native probes must succeed for each affected node. Naive revocation
witnesses require a mapping of actual HTTP servers even after the last user
retires. Publisher revocation requires an owned TLS canary accepted before authority replacement and rejected
after it; snapshot flags alone are insufficient. Never recreate credentials on
resume or treat status as fresh runtime verification.
Retired Hysteria keeps its lazy client SOCKS listener while the absent UDP peer
consumes the request deadline. A full-duration curl timeout qualifies as denial
only with unchanged before/after authority, confirmed inactive runtime and
absent identity, successful controls, setup and cleanup. Active or unproven
timeouts remain unknown.
An owned AWG TUN can exist before its userspace control API. Probe startup waits
for a successful bounded listen-port read before the single configuration write;
the fresh daemon may already hold an ephemeral UDP port. Setup failures expose
only fixed phase categories, never native output or private configuration.

Device migration uses separate source/target SOPS authorities and an encrypted
intent before cross-document writes. Exact inventory, host pins, alternate
sources and endpoint fingerprints fence resume. Publisher IO owns initialization
of the complete plan, hosts, commands and admission callback; subclasses admit
local values before the single base initialization. Publisher CAS
preserves every active URL and expiry; registry identity includes the exact migration metadata.
Preparation precedes target convergence. Publication and readiness re-run
target verification and an expiring credential-free TLS route canary, then
re-read authority before accepting delivery. Old credentials remain until a
separate retirement action. Origin and route probes explicitly require TLS 1.2
or newer while retaining certificate and hostname verification. Keep published,
received and fresh path-tested
states distinct; official-client attestations are explicit operator evidence.
Blue-green retains the target environment selector after handover because
delivered bindings now refer to it. Never rename target tfvars into the source
selector or recommend unconditional target destruction after publication.
Pair inventory rendering uses an owned temporary output and retains unrelated
publisher/alternate rows and memberships after strict admission. A changed
global SSH authority or concurrent inventory edit refuses replacement. A
topology-wide observability generation must be rendered by its complete owner;
the pair wrapper refuses it before provisioning. Standalone migration consumes
the complete reviewed inventory without re-rendering it.

TCP destination failover uses one immutable admitted DNS snapshot, interleaves
address families and races at most two gateway controls across eight candidates.
One connect deadline covers authentication and every attempt; per-attempt expiry
prevents two stalled controls from hiding later addresses. Only the winner enters
the relay, after loser sockets close. Never retry after application transfer.
UDP retains one pinned literal and one send per datagram.

Payload probing requires exact canonical bytes and bounded curl output through
`payload_probe_content.py`. Explicit SOCKS ignores ambient proxies and never
falls back to direct. Successful-transfer slowdown compares time per byte
within each direction so ordinary body-size growth is not throttling.
Classify every direction before combining evidence: any proven cliff wins
over an underconstrained direction, using the smallest proven threshold.
HTTP/2 framing and stream failures are network evidence; certificate and
content failures retain error priority.
The loopback canary applies a total request deadline and four bounded workers;
HEAD reports exact canonical length without a body. Canonical objects are at
most 1 MiB. Recipient policy version 2 optionally admits bounded quality
measurements; pass/window reservations include each body plus one overflow
byte. Quality absence retains health-only behavior; version 1 is rejected.
Recipient failover uses `payload_failover_policy.py` for strict two-origin HTTPS
policy admission; all contributing hosts must agree before extended emission.
Control URLs reject fragment delimiters even when the fragment is empty, matching
the recipient parser; percent-encoded path characters remain valid.
Plain sing-box exports retain their RTT-only urltest contract.

Fleet status resolves provider/environment selections through strict inventory
inspection, preserving Tailnet transport, public host identity and custom ports.
Its local watchdog verdict requires a recent completed result; neither a timer
nor a listening socket proves client-path connectivity. Rotation uses canonical
authenticated liveness for distinct survivors outside the current/completed
original targets. The versioned plan owns the survivor mapping. Private locked
journals bind the entire plan, synchronize in-flight before external execution,
and never automatically replay an uncertain outcome. Dry-run has no state writes.

The offline AWG sentinel installer binds the same correction into its existing
toolchain inputs and returns those public inputs to its provenance caller.
Liveness and real-VPS lane readers require that complete identity from the
fixed trusted installed helper. Old five-field manifests refuse qualification;
retain their directories for rollback rather than rewriting their receipts.
The verified vendor archive is extracted only in the private build workspace
and removed there before strict postimage verification.

Native AWG builders share the role's exact source correction and one native
build receipt helper. Source qualification, compiled binary digest and the
relative canonical alias must agree. All three builders execute real checksum
unit cases with a temporary Go overlay before building; the overlay adds no
untracked source input to the admitted tree.

Checkout discovery passes Git metadata input through a private temporary file.
Large NUL-delimited path lists can otherwise block both stdin and captured
output before the query timeout applies. Preserve UTF-8 surrogateescape bytes,
the empty-input EOF, the deadline and all active-content-filter refusals.

Strict full-device kill-switch certification refuses partial TUN capture
selectors, including route sets, interfaces, users, packages, namespaces and
MPTCP exclusions. Parser validity alone does not prove device traffic capture.
SOCKS Unicode names require a lossless codec round-trip; deviation forms refuse
and require an explicit ASCII A-label. Do not use casefold for this identity
check. Cascade TCP directions drain independently after FIN with bounded
buffers and idle time, while empty UDP payloads retain ordinary association
admission and tuple quarantine.

Certificate preflight verifies enabled profile authorities against the operator
trust store and server-auth purpose. Canonical per-host inputs retain Ansible
replacement order; standalone default-profile checks are labeled accordingly.
Supplied certificate chains provide intermediates, never trusted roots.

Hysteria export retains metadata for each endpoint. Official-client bandwidth
hints use the shared exact-rate conversion with reversed client directions and
positive whole-Mbps rounding; liveness requires the same hints and includes
them in the public generation digest. These are negotiated per-connection
values. RIPDPI does not currently apply them, so no server-wide cap is claimed.

The audited Bearer clients share authenticated_http.py and refuse every redirect.
Protocol notifications require an HTTPS origin without userinfo, path, query or
fragment. Local HTTP tests inject transport after origin admission; production
has no plaintext bypass. State backups expose final names only after completed
age encryption and uses no-replace publication to preserve timestamp collisions.
Hardware enrollment binds explicit serial/slot selectors through literal Make
inputs. Resume retains its identity, migration preserves each file's recipients,
and staged ciphertext shares the existing per-document writer lock. Grouped
policies require separate quorum-aware migration. Generation diagnostics stay
on the operator's private controlling terminal. Subscription issuance requires
the installed publisher-v1 readiness protocol before external publication. One
service-owned atomic envelope binds exact payload bytes and expiry under the
existing lock; a lost acknowledgement remains an uncertain external outcome.

Inventory publication removes CR and LF from wrapped base64 before it constructs
INI fields. Strict host selection still rejects split records. Renderer tests
cover both line endings and verify typed listener and observability data through
the strict parser.

Blue-green treats each Make phase as a separate ordered command with inherited
Make controls removed. Dry-run accepts only 0 or 1 and resolves before private
inputs. CI commands use the retained bootstrap session supervisor; keep private
stderr capture separate from machine-readable stdout and reclaim descendants
before teardown even when the command leader has already exited.

Terraform environment admission reserves `default` for the legacy `prod` mapping.
Blue-green admits both names before private inputs; distinct admitted names have
distinct state paths. Cohort creation and state backup/restore reject the alias too.

State encryption writes an owner-only pending file and publishes a complete
backup with an exclusive hard link. Timestamp collisions wait at most ten retries;
retention never sees an incomplete ciphertext. File sync precedes publication;
directory sync follows removal of the private staging name. A sync failure refuses
success and retention, while a complete published backup remains recoverable.
Cleanup registers before allocation and removes only this invocation's pending file.
`restore-tf-state.sh` selects the
exact environment, decrypts into a private sibling, validates Terraform v4 state
structure and replaces accepted state atomically. Failure removes only its own
candidate; stop concurrent Terraform operations before recovery.

Recovery dry-run output and both runbook paths require authenticated host pins,
installed recovery generation, Tailnet handoff, SSH ownership and all three private
deployment mappings before convergence. A restored root snapshot is not fresh
SSH or promotion proof. Keep dependent Make goals in separate invocations.

Canonical client payload materialization preserves Hysteria hopping for the
qualified RIPDPI client. Shared transport semantics validate the port range and
fixed interval (5 seconds through 9223372036854 milliseconds) before output.
Standard fields and extras carry the same policy. Official sing-box behavior
and other engine guards remain intact; XHTTP-only selection ignores Hysteria.
Full bundle validation matches hopping extras to one Hysteria outbound by tag.
When both policies exist, compare normalized port unions and exact durations;
equivalent units and a maximum equal to the minimum remain fixed policies.
Standalone extensions and either single policy form remain valid.

State backup retention and recovery match the complete UTC timestamp suffix
after the exact provider/environment prefix. A broad prefix glob also selects
hyphenated sibling environments and can delete or restore their state.

P0 recipient admission distinguishes sing-mux from Xray Mux.Cool; a valid JSON
document does not establish wire compatibility. REALITY shortIds compare as
decoded, zero-padded wire values, and mtg accepts only structured FakeTLS secrets.
Field-level refusals must keep private input out of diagnostics.

VLESS UUID uniqueness follows the pinned engine's parsed authentication bytes,
including its reserved routing bytes. Different strings cannot share that
identity. AWG reserves every instance server host address against all device
and routed peer prefixes before binding, export, enrollment or publication.

Certificate preflight requires DNS SAN authority and complete wildcard labels
before native hostname matching. Do not restore domain-name regular expressions,
CN fallback or partial wildcards. Use `verify -verify_hostname`: OpenSSL 3.0
`x509 -checkhost` can exit zero on mismatch. Keep expiry and public-key checks separate.

RIPDPI Hysteria hopping release admission requires positive native-client
traffic across scheduled destination-port changes. Per-host Hysteria extension
entries follow every emitted tag, not only the first host. A scalar server port
outside the hopping range must not widen the client destination set.

The REALITY monitor supervisor handles INT, TERM, HUP and QUIT before launching any decrypting child. The shell creates its work directory using an explicit parent path; BSD mktemp -t can ignore TMPDIR. Parent-owned temporary authority is removed after session cleanup on cancellation. Bounded child stderr is forwarded separately from the JSON stdout protocol. The monitor requests SOPS JSON directly into its private owned file; the general decrypt cache retains its YAML contract.

Federation preserves dependency edges between receipt-validated cancelled records. A cancelled prerequisite still refuses every non-cancelled dependent and never makes a task ready.

Taskctl archive maintenance relocates only owned inline task links. Dropped records retain immutable close receipts: readers verify the exact link projection from the archive’s reachable terminal source, rejecting every other byte change, including newline conversion. Repeated archival preserves timestamps/spec state; partial document-write failures restore the original record.

A successful alternate retains usable transport delivery, while any non-ok endpoint variant makes the operator decision degraded; exact primary/alternate observations remain separate and do not create a rotation candidate by themselves.

Task-history merge lanes retain the shared first-parent boundary, including
closure commits made before a branch updates from main.

XHTTP delivery resolves both configured direct endpoints through
`transport_semantics.py`, retaining each hostname and port. Native Xray output
is P1-only: each loopback SOCKS inbound routes to one exact endpoint, and the
unmatched default is blackhole. Typed bounded-pool controls require v26.3.27;
RIPDPI export refuses tuning its importer drops. The explicit monitoring
intermediate can carry the native fields, and liveness retains variant-to-endpoint
identity plus exact mode/tuning in its public profile map.

The AWG source-candidate runner admits only a local Unix-socket Docker daemon,
copies an explicit public-file build context and removes only its own
container ID. After an uncertain startup it polls the preallocated name for
30 seconds, removes it once observed, and fails with an explicit unconfirmed
cleanup diagnostic if the daemon outcome remains unknown. It binds
BuildKit and runtime calls to the admitted local engine context. Public sources
arrive as exact-commit Git bundles fetched over GitHub SSH port 22; credentials
and the agent stay on the workstation. Every invocation revalidates current
lightweight/peeled annotated upstream refs before accepting cached bundles.
Runtime execution has no external network
or published ports; compilation belongs under the machine-wide build gate.

ECH and BBR recipient fields are materialized in the shared Python payload path used by both delivery and drift inspection. The internal XHTTP-only selection retains semantic admission and is refused by bundle export.

Bootstrap registers plaintext cleanup before creating an exclusive private temporary document; ECH refusal, encryption failure and signal exits remove only that invocation's staging file. Existing operator plaintext remains intact. RIPDPI bundle export rejects the internal `--xhttp-only` monitoring flag before invoking any producer or reading secrets.

ECH recipients and liveness derive their default TLS identity from the declared inner name, independently of the nginx frontend hostname. An explicit Hysteria server_name must agree through semantic admission.

BBR resource profiles, like ECH, target the qualified official sing-box recipient. Unqualified RIPDPI export refuses before output; paired XHTTP monitoring requests only its explicit Xray intermediate.

Release eligibility evaluates high/critical advisories against the exact selected version and repository-owned module ranges. Historical fixed ranges may clear; unknown modules, missing ranges or unsupported syntax keep promotion blocked.

Bound bandwidth scalar length before integer conversion, so oversized numeric inputs refuse categorically within the supported 1 Gbps policy.

Hysteria release acquisition and ECH generation share scripts/hysteria-runtimes.json. These deployment-only pins are outside the client-mirrored contract directory.

Generator acquisition rejects nonregular sources through a bounded nonblocking descriptor before bytes are trusted. ECH issuance uses the exact checksum-verified Hysteria generator and encrypted_client_document publication lock. Only public generation identity reaches stdout. The supported ECH recipient is official sing-box 1.14.3; RIPDPI bundle export refuses the profile until its real consumer is qualified. Liveness retains exact public ECH material and refuses a different or stripped generation.

Federation reads the peer's own committed `taskctl export --json` contract;
it never parses another project's portfolio through this project's schema.
The shared graph validator checks exact identity, revision, contract hash,
relations, progress and terminal provenance. Purged references are resolved
by the owning exporter's `--resolve-task` with native receipt/history checks.
An unassessed peer risk remains null; no task records or receipts are rewritten.
Peer failure diagnostics stay categorical and bounded.

AWG peer `allowed_ips` is a typed IPv4/IPv6 mapping. Issuance allocates both
host identities before publishing ciphertext; exhaustion in either pool leaves
the prior generation intact. Address allocation jumps claimed intervals, so an
IPv6 /64 is bounded by peer count. Standalone and bundle emission share instance
MTU resolution with liveness; runner settings carry `addresses` and `mtu` and
install both default routes in the owned namespace. Public uplink admission is
read-only, requires the selected IPv6 default route, and refuses RA ownership
that would expire after forwarding enables.

AWG device issuance, revocation, export and recovery bind provider/environment,
instance and device through `awg_device_binding.py`. Only the nonempty instance
list owns peers and server keys. `awg_client.py` allocates from the selected
subnet and shares the private stable `.new-client.lock` with Naive/retirement.
`encrypted_client_document.py` stages ciphertext, verifies the entire decrypted
result in memory and atomically publishes only after original authority checks.
AWG revocation clears only the selected peer and its AWG recovery fields.
Preflight and credential mutations share registry validation in
`awg_device_binding.py`, checking both registry-to-peer and device-peer-to-registry authority;
routed peers are exempt from the device registry. Existing-device resolution
always requires the persisted registry binding;
device names are unique across all instances, including explicit selection.
AWG-only reissuance accepts a valid null binding with empty recovery fields and
preserves non-AWG metadata; globally revoked entries and all-profile reissuance refuse.
AWG Make targets apply normal host defaults and unexport original inputs after
literal capture, preventing Make function expansion during environment export.
Host environments follow the lowercase, alphanumeric-leading registry grammar.
Make AWG operations append best-effort encrypted audit records only after a
successful transaction; audit status stays on stderr so stdout remains JSON.
Encrypted source, lock and candidate opens are
nonblocking before regular-file validation, so a FIFO cannot hold the writer lock.
Subscription delivery records `awg_delivery_host` independently of device
authority; refresh restores this selector, including automatic selection,
instead of inheriting ambient host overrides. Missing delivery state refuses
refresh and requires reissuance. De-onboarding deletion paths require the
verified cleanup provider/environment and exact persisted instance; rebinding
a client to another host cannot authorize deletion through the old receipt.
First-time subscription registry entries initialize a null AWG binding and
empty recovery fields; existing AWG authority survives delivery metadata updates.
Bundle multi-host selection requires `AWG_HOST` when more than one enabled host
can bind; `AWG_INSTANCE` selects within that host. Missing enabled bindings
refuse without emitting a partial payload. The bundle retains the address array and fingerprint algorithm;
its admitted device address pair and MTU bounds are stricter. RIPDPI bundles support AWG-only profiles through
the direct carrier document; the official sing-box format still requires a
supported proxy outbound. Private recipient output uses no-clobber `OUTPUT`
publication in an owner-only directory. URI issuance also requires a private
new output reserved before source mutation; transaction failure removes only
that owned artifact. Credential-bearing URIs never enter metadata stdout. URI QR generation reserves
its own private recipient file, reads the VLESS URI from that file, and retains
it if QR rendering fails after enrollment. AWG CLI callers put the device name
after `--`, so dash-prefixed identifiers cannot become options or audit-only
successes. A null AWG registry binding also requires absence of that device
from every instance peer collection.

CI selects both native integration and complete transport acceptance together.
Each has its own disposable runner; the consumer lab never adopts or removes
another fixture's runtime authority. The required job graph checks both results.

The canonical render fixture supplies watchdog AWG interface names from synthetic
instances. Snapshot rendering uses the same pure effective-instance resolver
and never loads real credentials. Unsupported I1-I5 policy fields and nonzero
S3/S4 role defaults refuse before normalization rather than being discarded.
The secrets coverage checker declares this names-only role fact explicitly;
the complete AWG secret instance objects remain outside the environment file.

Passive command collection retries transient nonblocking pipe backpressure
within its original deadline and input/output budgets. Readiness is not a promise
that the next read or write can complete; broken input pipes still refuse.

The disposable cloud-init schema client uses one deadline for nonblocking tar
delivery and child completion. Partial writes retain their offset. Timeout
cleanup attempts to stop and reap the owned client before container removal.
Confirmed cleanup requires successful client shutdown and removal. Uncertain
shutdown still permits a bounded removal attempt for the owned name, but always
returns status `125`. An earlier daemon request may still be in flight: failed
removal remains uncertain even when inspection reports absence.

Subscription refresh binds the requested client name to the unique token-prefix
registry match before credential emission or remote publication. Prefix-only
registry compatibility remains unchanged; an ambiguous match refuses.

Secret rotation and warm-spare approval writers retain a private descriptor lock
in their parent shell. `private-operator-lock.py` validates its owner, inode,
single-link file and directory authority before locking and hardening old owned
locks to `0600`. Watcher publication and promotion consumption share one stable
`promotion.lock`, held through orchestration; neither process deletes the lock.

Verification admission passes the exact limit to Ansible inventory resolution.
`require-vpn-selection.py` then requires a VPN member, including child groups,
so a known observer-only limit cannot produce an empty successful play.

`rotate-credentials`, `rollback-xray` and `rollback-config` are exact-node verbs:
Make captures `ANSIBLE_LIMIT` as literal data into the `EXACT_NODE_ALIAS`
environment variable, `require-exact-node` checks it against the play's alias
pattern, and `ANSIBLE_LIMIT` then expands to the shell reference
`$EXACT_NODE_ALIAS`, so no recipe, including the shared `require-inventory`,
interpolates the alias into shell code (`ENV`, `PROVIDER`, `SECRETS_FILE`,
`ROLLBACK_XRAY_VERSION`, `SKIP_PRECHECK` and `ANSIBLE_DIR` are still expanded as
Make and shell syntax; SCR-1792057680449496 tracks them). That reference is not
an alias: the verbs refuse to share an invocation with any other goal, run one
after another (`.NOTPARALLEL`) when they share one, and `ANSIBLE_LIMIT` is
unexported so no recipe receives it. They start `ansible-playbook` without inherited
`ANSIBLE_SKIP_TAGS` or `ANSIBLE_RUN_TAGS`, which could skip the `always`-tagged
guard. The play asserts the one selected alias through
`ansible/playbooks/tasks/exact-node.yml`; that binding, not the `ENV` check, is
why each run acts on one node, so revoking a client is complete only after one run
per node. Rotation separately refuses a host whose inventory `env` differs from
`ENV`. `docs/how-to/rotate.md` and `docs/how-to/deploy.md` print the revocation
sequence as a subshell that names the environment once (`e=prod`), installs a
`make clean` EXIT trap before `make decrypt` and turns INT, QUIT, TERM and HUP
into exits: the per-node rotate and verify loop runs only after a successful
`make decrypt`, because a failed decrypt leaves an older plaintext file in place
that the loop would then deploy, and `make clean` runs on every exit path a shell
can catch (success, failure or interruption, but not SIGKILL or power loss, after
which the operator runs it by hand). The EXIT trap ignores those four signals
while `make clean` runs, so a second one cannot cut the shred short. The subshell
exits with the failing step's status, which the cleanup does not mask, and with 1
when only `make clean` fails, as the cleanup blocks in `docs/tutorials/quickstart.md` leave
the block unsuccessful. The REALITY keypair and restic password sections of
`docs/how-to/rotate.md` print the same guard around their `decrypt`, `deploy` and
`verify` calls; `test_operator_verb_scope.py` runs all four blocks, including
interruption. The ordinary re-deploy recipe in `docs/how-to/deploy.md` splits
preflight and deploy around the operator's review: a failed or interrupted
preflight cleans up, a successful one keeps the plaintext for the deploy block,
and the deploy and journal-recovery blocks clean on every exit; the same test
file runs those three blocks.

The release installer verifies the exact repository and fully qualified signer
workflow before installation. Cloud-init acceptance checks the actual loopback
SSH banner before it accepts the configured listener.

Explicit diagnostic addresses scope burn, probing and ASN checks to the selected
host. ASN state is separate for each address, so an override cannot compare or
replace another host's previous observation.

Disposable CI generates distinct internal normalizer/gateway credentials for every enabled guarded path, validates them through effective profile admission and keeps them out of process diagnostics.

CI credential generation uses the served `SERVER_NAME` HTTPS origin for Hysteria masquerade. The watchdog keeps its separate exact canary endpoint, including its path; a probe URL is not a masquerade origin.

XHTTP path and HTTPS origin admission live in `transport_semantics.py`, shared
by controller preflight, secret validation, emission and liveness. Canonical
origins include nondefault ports and omit 443; bootstrap exposes `--xhttp-port`
and CI generation uses `XHTTP_PUBLIC_PORT`. Make captures the port literally
and passes it through a quoted environment field before validation, never as
interpolated shell syntax. The only evaluated profile expression
is the exact repository-owned served-origin expression; arbitrary Jinja and
private operator origins are never rewritten or normalized.

- `transport_private_authority.py` reads bounded private configuration and the observed systemd credential ACL contract. Its credential exception is restricted to the exact private per-unit directory on a read-only mount, with effective read authority only for root and the service UID; ordinary files remain owner-only. Install that companion beside normalizer and classifier consumers.

**Recipient metadata has a fixed exit authority** — `transport_egress_config.py` constructs private fixed listeners and literal-only native gateways from admitted credentials and actual service UIDs. `transport_egress_host_context.py` reads kernel addresses and effective SSH/recovery ownership; `transport_egress_kernel.py` owns an atomic nft table and private receipt. The final output guard runs after earlier ACCEPT and destination rewrites. Unknown late hooks, packet duplication, TC/XDP and flow offload refuse admission. Resolver inputs remain numeric and sealed; no recipient domain is forwarded to a gateway.

Private-port admission distinguishes retired kernel TCP records from live socket authority: only `TIME-WAIT` with an explicit zero inode, zero or absent UID and no process owners can pass without the expected service UID. Live TCP, every UDP socket, nonzero inodes, missing inode metadata and foreign UIDs still refuse. This permits guarded recovery after active controls close without granting a live socket to another actor.

Normalizer refusal replies are best-effort only after admission has already failed. A client disconnect while receiving the refusal does not suppress resource cleanup: the connection, backend control, concurrency slot and worker record are released in the same finalizer.

Normalizer TCP listeners enable `SO_REUSEADDR` before binding so a new guarded process can recover while prior accepted TCP controls remain in TIME_WAIT after a crash. This does not share an active listener: `SO_REUSEPORT` stays disabled. UDP sockets, exclusive tuple pools, continuous-quiet quarantine and paired gateway reset retain their existing behavior.

**Transport relationships share one validator** — `transport_semantics.py`
validates globally unique client names and explicit cohort membership, effective
AWG headers/bounds/interface,
canonical 32-byte keys and noncolliding device or explicitly routed prefixes,
and owned HTTPS proxy masquerade. CLI requests use bounded JSON on stdin;
diagnostics contain fixed field paths and categories, never values. Enrollment
checks before generation and before encrypted publication; emitters and liveness
use the same rules. Disabled transports are excluded by resolved profile intent.
A broad prefix requires `address_kind: routed` and cannot be emitted as a device.
Named cohorts load only through validated repository-owned technical slugs.

**Native semantic fixtures use pinned real inputs** —
`build-native-transport-semantics.sh` provisions exact-commit AWG source outputs
and checksum-verified Hysteria only in the isolated Linux amd64 fixture cache.
It uses repository-pinned Go with two jobs; native builder version guards must
match `mise.toml` and the role archive pins. It rejects tracked source drift and
never installs onto a live service path. The native lane verifies source commits,
compiled ELF outputs, actual parser/startup behavior and owned cleanup; fixtures and missing
prerequisites cannot become a native pass.

**Naive devices have independent encrypted identities** — `naive-client.py`
centralizes the three explicit Make verbs for issuance, revocation, and selected
credential readout. Selected readout requires an explicit new `0600` output in a
private `0700` directory, outside tracked source or under ignored `secrets/local/`.
Its stdout carries only metadata; linked/existing/shared output authority refuses.
It shares `.new-client.lock`, uses encrypted sibling publication,
refuses unsafe source authority, and preserves unrelated fields. Once ciphertext
replacement commits, a sync or descriptor-close failure reports
`committed-durability-uncertain` with exit 3 and retains the recipient artifact;
inspect the enrolled state before retrying. `new-client.sh`
includes optional Naive issuance inside its existing all-profile transaction.
No scalar credential compatibility path or plaintext staging is supported.

**Bootstrap issuance follows intrinsic retention** — the subscription resolver
uses role defaults, group/profile policy and encrypted overrides to create versioned
epoch-bound grants. Optional expiry only shortens the deadline, and its bounded
metadata is installed before the payload. No old-format bootstrap URLs are issued.

- SNI secrets are parsed structurally through PyYAML; only `xray.server_names` becomes probe targets, and malformed private input produces categorical diagnostics.

- Disposable CI creates its no-clobber public result directory before validating
  configuration. Invalid JSON, template selection and absent credentials produce
  categorical results without private inputs or starting provider operations.
- Disposable CI uses one private controller run per guest. A provider-imported,
  digest-bound SSH seed establishes first-contact trust; its private image and
  provider upload diagnostics never enter plaintext artifacts. Exact cleanup
  includes the seed, and seed-only cleanup never proves whole-provider absence.
- CI Tailnet policy is derived only from a confirmed handoff matching source,
  node, host-key pin and observed contexts in a typed CI cohort. Promotion uses
  the ordinary pinned Linux SSH sentinel at `ci-liveness` with actual activation
  metadata; the existing Colima executor retains its separate bound contract.
  Stop owned loopback/Tailnet units in every exit path on the ephemeral runner.
- The CI SSH sentinel creates OpenSSH's privilege-separation runtime before
  validation and retains PAM account/session checks with public-key-only
  authentication. Tighten an owned `.ssh` directory before publishing config;
  reject writable or foreign directories and report categorical stage errors.

**Blue-green stops for review** — apply follows the green plan and deploy
follows the green dry-run only after a typed `yes`. `promote-spare` reaches
the same prompts; its OTP authorizes the swap, not an unreviewed plan.
The blue-green, promote-spare and watch-spare recipes pass `BLUE_ENV` when it
is set, else `ENV`, and refuse an explicit `ENV` that names another environment.

**Blue-green authenticates before first contact** — verify the green public key through an authenticated channel and confirm its standard known_hosts entry before inventory rendering. Vultr secondary-IP discovery uses strict host-key checking; it never enrolls a new key. Wait for cloud-init through the pinned public path before presenting recovery-installation steps. Then establish Tailnet/recovery ownership, render the confirmed handoff, and let the canonical controller perform pinned readiness. Blue and green aliases must be exact VPN inventory members before verification or deployment.

**One secrets file, one environment** — the deploy controller refuses a
selection when `ENV` is empty or any selected host's inventory `env` differs
from it. The check runs before the decrypted secrets read, SSH and Ansible, so
an inventory with several environments never receives another one's secrets.

**Audit operator boundaries** — saved Terraform plans pass `check-tf-plan.sh` across all required policy namespaces; `policy-plan.sh` snapshots once, checks and applies that exact private file. Never replace it with a second plan. Reconverge, replacement and drift check-mode call the Make deployment controller. `diff-secrets.sh` uses the inventory transport and read-only Ansible comparison against the canonical Xray template; it never prints remote configuration or treats rendering failure as clean drift.

**Checkout discovery precedes operator configuration** — `make workspace-status`
reports local Git metadata without parsing `.fleet.mk` or reading runtime inputs.
`scripts/workspace-status.py` describes the caller's checkout, including detached
HEAD, dirty counts and the known local `origin/main`; it never fetches or refreshes
the index. Git queries disable fsmonitor to prevent configured hooks or monitor
startup. Active content filters and tracked submodules are rejected before
status, because dirty detection can execute external commands there; disabling
filters would invent differences against normalized index blobs. Configured but
unused filters remain supported. Optional `--task` pointers come from the canonical
`taskctl show` API; explicitly empty selections fail. Task queries have a bounded
five-minute deadline for committed closure-history audits; ordinary Git metadata
calls retain their independent 30-second deadline. Failures expose only the
categorical discovery diagnostic, never captured task output.
The documented entry clears inherited Make inputs before Make starts; Git status
uses explicit unlimited rename detection and lossless path decoding; lazy object
fetching is disabled, so missing required blobs fail locally. Text paths are
JSON-quoted to preserve field boundaries.
Discovery accepts no Make command-line assignments. It identifies variables by
origin and rejects them without expanding values, including recipe controls such
as `SHELL` and `.SHELLFLAGS` that Make itself consumes.

**One file per operator verb** — `bootstrap-secrets.sh`, `rotate-secrets.sh`,
`fleet-rotate.sh`. The Makefile wraps these with `make <target>` shorthand.
`observability-operator.py` now selects co-hosted VPN capabilities and the
independent typed Kuma observer; dedicated-host `bootstrap` refuses before
host access. Local `render` and syntax `validate` do not admit a host; `check`
requires explicit host-access confirmation. Private-IP PKI preparation produces
an encrypted fragment without contacting a host or issuing Telegram credentials.
The shared PKI helpers explicitly emit CA/leaf subject-key identifiers and leaf
authority-key identifiers; strict verification must not rely on OpenSSL's
implicit extension defaults.
`observability-staging-acceptance.py` retains the historical dedicated-host
staging contract, not acceptance for the current co-hosted topology: one
invocation advances one repository-defined live row from a private canonical
manifest, approval and journal. Keep the critical reminder at the real one-hour
interval, require separate human-observation booleans, restore interrupted rows
before later work, and emit only categorical private receipts. Never add a
caller-supplied command, unit, endpoint, environment or arbitrary fault.
The fixed sequence includes negative ingestion, bounded persistent-queue recovery,
missing/stale evidence, grouping/inhibition, finite-silence, sender and
Telegram old-material rejection, invalid-candidate refusal, valid activation,
and exact control-plane rollback rows. Old sender proof uses the retained
private generation only for a rejected TLS handshake; candidate generation and
TSDB identities remain private controller evidence and never enter receipts.
The retained `agent-wal` row identifier now exercises the current vmagent sender.
Read transport from the fixed service's stable MainPID and bounded argv, not
removed Prometheus remote-write YAML fields. Queue bytes, sent blocks and HTTP
or persistent-queue drops have distinct units; no counter substitutes for a
collector query proving the exact node's historical sample inside the outage.
Keep the staleness mutation journaled on the canary and held until the control
plane independently observes the firing alert; every exit restores the exact
producer timestamp and prior watchdog-timer state before later checks. Finite
silences use an approval-derived reason and the gateway's private authoritative
journal so normal and interrupted restore delete every silence created under
that exact owner, node, and approval authority. Transport/TLS failure is valid
rejection evidence only for the plaintext and missing-identity TLS probes;
authenticated path, method, query, and admin probes require an explicit
non-2xx HTTP response, and the authenticated positive write remains strict.
The invalid-candidate row first render-checks the complete candidate, then
accepts only the operator's exact pre-mutation control-plane role-guard refusal
for a full configuration with only `prometheus_listen` changed. Real and
interruption rollback always pass the digest-bound retained last-known-good
vars and secrets, never the active candidate inputs. Capture typed role-guard
output incrementally under the fixed 64 KiB cap and deadline; overflow or
timeout must kill the owned process group and expose only the categorical
failure.
`prepare-observability-staging.py` is the local-only authority and input
preparer for that fixed run. It requires a clean protected-main source and
private canonical configuration plus already-issued Telegram values, creates a
new task-private root without clobbering, retains SSH and age identities only
there, and encrypts generated PKI/runtime authorities directly to SOPS. It must
not contact provider or Telegram APIs, create bot/provider credentials, print
private paths or values, infer approval, or turn null binding/rollback drafts
into executable authority. Materialization is a separate explicit verb and
publishes only a same-owner mode-`0600` file under that root.
Every input/root ancestor is opened component-by-component without following
symlinks and must be owned by the current user or root; writable ancestors are
accepted only when sticky. Keep root, subdirectory, secret creation, and
materialized replacement bound to directory descriptors and verify the
canonical inode bindings before success. Do not regress this to path-based
check-then-open operations.
Telegram `topic_id` is `0` for direct/non-forum chats so runtime senders omit
`message_thread_id`; positive values are reserved for real forum topics.
`ssh-ownership.py` is the explicit fresh-node SSH ownership verb between
dual-path Tailnet bootstrap and ordinary deployment. Its private configuration
binds the exact source, one inventory alias and an explicit `vpn` or
`observability-kuma` section in schema 2; check mode only previews.
Tailnet bootstrap schema 3 selects an absolute fenced inventory and either
`vpn` or `observability-kuma`. SSH recovery requires the same explicit section.
Both installers use a private one-node Ansible adapter; this does not add the
independent observer to the persistent VPN fleet. Old bootstrap schemas refuse.
`staging-tailnet-recovery.py` is the disposable-only acceptance verb behind two
fixed Make targets. It deliberately kills the enrollment worker or reboots the
node after durable pending state; it never exposes a general fault selector or
adds a guest RPC. Reboot failures after observed SSH loss publish a separate
redacted private `incomplete` diagnostic; that artifact is never success
evidence and never emits the success audit record. Once SSH loss is observed,
its already validated path and parent inode stay frozen so a later wrapper
change cannot suppress the failure receipt. Wrapper schema 2 requires that
fresh diagnostic path; obsolete schema 1 refuses before SSH.

**Runtime bundle validation is a narrow SOPS exception** — a client-side
materialized bundle is not an Ansible secrets document. The explicit
`validate-bundle.py --runtime-materialized` mode may read it only as a
same-owner `0600` regular file through a symlink-free, owner-controlled path,
redacts the key in memory, and never rewrites or logs the artifact.

**Provider roots share one inventory schema** — UpCloud, Hetzner, Vultr, and Scaleway export the same canonical outputs, so `render-inventory.sh` stays provider-neutral. Add provider-specific inventory code only when a control-plane address needs extra guest convergence proof, as Vultr's secondary IPv4 does.

**Inventory inputs fail before publication** — nonempty cohort slugs must name an existing `group_vars/vpn-*.yml` profile, and host aliases must be unique across provider/environment pairs. Reject malformed profiles before Terraform calls and preserve the last valid inventory on either failure.
Base64 listener and topology values remove both CR and LF wrapping before INI
publication; encoders on supported operator hosts can emit either line ending.
Observability enablement comes from the tracked `enabled_environments` list and
the selected provider/environment pairs, not ambient `ENV`. Reject mixed
enabled/disabled scope before Terraform. Strict secret validation requires
explicit `--environment` arguments; host controllers derive them from immutable
inventory metadata. The old global boolean is not accepted.

**Tailnet inventory transport is confirmed** — `TAILNET_HANDOFFS` accepts one
private mode-0600 bootstrap handoff path or `-` per selected Terraform host.
The renderer validates the complete path list before Terraform calls, then
binds each handoff to the Terraform alias, public address, SSH port,
confirmation digest and actually proven Tailnet address family before changing
only `ansible_host`; the
Terraform public service address and listener contract remain authoritative.
The public-listener verifier reads the complete nftables `inet filter` table:
Tailnet SSH source matches refer to named sets, so their live members and
address-family types must be checked alongside the input-chain rules. ICMP
accepts require an explicit type match; a protocol-only accept is broad.
`fleet_inspection.select_hosts` uses `vpn_service_address` as the public
identity and `ansible_host` as the transport; a distinct Tailnet transport
must retain the public host-key alias for dual-path SSH proof.

**Liveness formats are selected by required profiles** — standalone XHTTP uses
RIPDPI emission and Xray; REALITY and Hysteria2 use sing-box emission. See the
liveness section of [DESIGN-NOTES.md](DESIGN-NOTES.md#liveness-sentinels-disposable-staging-and-retirement).

**AWG liveness DNS follows the role profile** — the private sentinel runtime
includes the role's validated IPv4 DNS servers. The runner writes a private
`/etc/netns/<generated-name>/resolv.conf` before the real hostname probe and
removes it with the namespace. Never use a fixed `curl --resolve` address as
proof of tunneled DNS.

**Promotion proof snapshots use canonical temporary paths** — macOS may give
`TemporaryDirectory` a path beneath symlinked `/var`. Resolve the controller's
new private directory before passing its executor snapshots to the evaluator;
the evaluator still rejects symlinked private input paths.

**SSH baseline failures have private categorical receipts** — deploy requires
an exact-alias mode-`0600` mapping to fresh absent outputs in owner-controlled
mode-`0700` directories. The deploy controller validates and freezes those
paths and parent device/inode before readiness, rechecks every selected sink
in one all-host preflight before the first SSH, and passes it to the baseline
controller for another identity check before publication. Unencodable surrogate
pathnames refuse before SSH.
Same-directory output names are case-folded and
Unicode-normalized so case-only and canonically equivalent variants refuse on
every operator filesystem. The baseline controller validates the sink before
the rest of the deploy request without coupling that authority check to
unrelated request fields. A malformed prepare receipt attempts bounded
rollback when its generation and nonce remain usable; otherwise it publishes
the categorically uncertain result. A deploy prepare RPC that returns no
receipt is also categorically uncertain because durable guest state may already
be armed; it cannot attempt rollback without the capability. Check-mode preview
retains its non-mutating RPC category. Publication occurs only after that
rollback or a handled interrupt has rolled back. Its CLI preserves a
nonzero interrupt status but emits only the generic public error. It publishes
only its allowlisted failure category with no-follow, no-clobber and fsync.
Keep the Ansible task
`no_log`; success and check mode leave the output absent. A missing receipt
after abnormal controller death or publication failure is an unknown outcome,
not success, and receipts never satisfy promotion or protocol proof.
Disposable liveness de-onboarding after provider firewall promotion supplies
both the original binding manifest and its reissued cleanup manifest. Their
private hashes, immutable resource identity, account, deadline and state path
must match the verified provider absence receipt before local removal.

**Provider promotion snapshots only Terraform inputs** — pin the two referenced
`terraform/shared` files explicitly. A recursive shared-directory copy would
include the `AGENTS.md` instruction symlink and generated Python cache, causing
promotion to refuse before planning. Required input files still fail closed if
missing, symlinked, or unsafe. Pre-create the selected non-default workspace
directories inside the private snapshot so Terraform cannot add `0755`
directories during its first command.

**Disposable de-onboarding consumes current guarded UpCloud absence** — its
provider receipt is schema 3; keep the provider and version check aligned
before removing encrypted client state or the executor profile.
The sentinel registry uses the installer's sorted JSON serialization, which
the de-onboarding reader must preserve exactly during removal.
Unbound recovery also requires the registered manifest inode and reserved
verified-absence path; pre-destroy and genuinely empty post-destroy state
hashes differ. Freeze the latter digest/inode throughout client retirement.
The separate prepared-executor verb requires the completed client receipt and
unchanged final ciphertext, serializes profile ownership against binding, and
retains removal intent for stopped/absent retry. Never fabricate a binding to
remove a prepared VM or reuse a retired one-shot profile name.
Snell is optional in issuance and unbound retirement. An absent section has no
client edges; configured variants must still contain exactly one issued client.

**Xray migrations are changelog-driven** — `docs/reference/xray-release-line.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Observability staging cleanup is an aggregate all-provider transaction** —
`observability-staging-cleanup.py` is fixed to the exact `staging` UpCloud,
Hetzner, and Scaleway tuple. Its snapshot derives identities from routed local
Terraform state, `seal` binds the separately supplied destructive-data
approval, and `run` validates every account, state, resource and reviewed
delete-only plan before the first apply. It emits a redacted receipt only after
provider-authenticated absence; never turn it into a generic provider,
environment, URL, address, or command runner.

**Python CLI delivery is verified before publication** — build-vpnd-package.py
copies reviewed tracked Python sources and Markdown, rejects source symlinks,
and generates canonical parser-derived manuals. check-vpnd-package.py compares
reproducible artifacts and checks isolated offline installation, packaged assets
and upgrade recovery. install-vpnd.py validates the native bundle, exact locked
wheel closure and private publication transaction before changing the launcher.
Dependency policy verifies pinned wheel hashes, reviewed SPDX license text and
non-yanked official registry metadata; it complements the vulnerability audit.
The parity gate reads the permanent `vpnd/test-inventory.md` baseline, so
archiving a planning change never removes its test obligations.
