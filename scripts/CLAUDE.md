# scripts — operator entry points

## Design decisions

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + pinned `PyYAML`, `Jinja2`, or
`certifi` from `requirements.txt`.

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
binds the exact source and one inventory alias; check mode only previews.
`staging-tailnet-recovery.py` is the disposable-only acceptance verb behind two
fixed Make targets. It deliberately kills the enrollment worker or reboots the
node after durable pending state; it never exposes a general fault selector or
adds a guest RPC. Reboot failures after observed SSH loss publish a separate
redacted private `incomplete` diagnostic; that artifact is never success
evidence and never emits the success audit record. Once SSH loss is observed,
its already validated path and parent inode stay frozen so a later wrapper
change cannot suppress the failure receipt. Wrapper schema 2 requires that
fresh diagnostic path; obsolete schema 1 refuses before SSH.

**SOPS gate everywhere** — anything that reads decrypted secrets refuses
without `VPN_SECRETS_FILE` or the Make-resolved `SECRETS_FILE` produced by
`make decrypt`. Never assume `/tmp`, and never re-implement decryption.

**Runtime bundle validation is a narrow SOPS exception** — a client-side
materialized bundle is not an Ansible secrets document. The explicit
`validate-bundle.py --runtime-materialized` mode may read it only as a
same-owner `0600` regular file through a symlink-free, owner-controlled path,
redacts the key in memory, and never rewrites or logs the artifact.

**Destructive scripts always audit** — they append to
`audit-log.sh append-best-effort` after a successful run; there is no
opt-out flag.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; new environments must be initialized through `make ... init`.

**Provider roots share one inventory schema** — UpCloud, Hetzner, Vultr, and Scaleway export the same canonical outputs, so `render-inventory.sh` stays provider-neutral. Add provider-specific inventory code only when a control-plane address needs extra guest convergence proof, as Vultr's secondary IPv4 does.

**Inventory inputs fail before publication** — nonempty cohort slugs must name an existing `group_vars/vpn-*.yml` profile, and host aliases must be unique across provider/environment pairs. Reject malformed profiles before Terraform calls and preserve the last valid inventory on either failure.
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

**Xray migrations are changelog-driven** — `docs/XRAY-RELEASE-LINE.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Subsystem notes live in `scripts/DESIGN-NOTES.md`** — read the matching
section before changing: `tasks/taskctl.py`; the deploy controller and inventory
rendering; `destroy.sh` and staging cleanup; `emit-*.sh`; `fleet-inspect.py`;
liveness sentinels and probes (`*liveness*`, `probe-*`, `snell-refinement.py`,
real-VPS AWG evidence); `tailnet-*`; `observability-operator.py`; cloud-init
acceptance harnesses; SSH recovery installation.

**Observability staging cleanup is an aggregate all-provider transaction** —
`observability-staging-cleanup.py` is fixed to the exact `staging` UpCloud,
Hetzner, and Scaleway tuple. Its snapshot derives identities from routed local
Terraform state, `seal` binds the separately supplied destructive-data
approval, and `run` validates every account, state, resource and reviewed
delete-only plan before the first apply. It emits a redacted receipt only after
provider-authenticated absence; never turn it into a generic provider,
environment, URL, address, or command runner.

## What's done well

Staging cleanup has one private controller journal per provider/account/server
UUID. Keep publication/reissue and receipt operations under its shared lock;
`destroy.sh` inherits that lock through Terraform. Alternative artifact paths
must never create a second reservation or recover an active controller. Reissue
binds the previous generation, original state path and unchanged deadlines.
An exact retry of a committed publication is acknowledged only when the journal's
prior generation matches the retried request.
Independent controller homes are not a supported shared-ownership mechanism.

- **`set -euo pipefail` everywhere** — fail-loud is the default.
- **`shellcheck` in CI** — the `ci.yml` workflow runs shellcheck on every
  `.sh` file; warnings break the build.
- **Idempotent where it matters** — `validate-target`, `check-certs`,
  `audit-permissions` can run repeatedly with no side effects.
- **One script = one job** — no flag-driven multi-mode scripts. `new-client.sh`
  and `new-cohort.sh` are separate even though they share boilerplate.
- **RealiTLScanner cache is launch-validated** — macOS builds use an isolated
  `GOBIN`, verify `-h`, and atomically replace the pinned cache only after a
  successful build. An executable bit alone does not prove the cached binary
  matches the host architecture or is complete.

## Pitfalls

- **Bootstrap transport is node-scoped, never global extra vars.** Ansible
  extra vars override `delegate_to: localhost` too, redirecting controller
  validation to the VPS. Keep pinned connection settings in the private
  one-node inventory group and exercise real Ansible delegation in tests.

- **Normal bootstrap cancellation is not controller-loss evidence.** Its
  exception path requests rollback. Recovery acceptance must use the fixed
  staging-only harness, keep its child bound to parent liveness, observe exact
  worker `SIGKILL`, and accept only fresh timer or current-boot recovery unit
  results plus public SSH/SFTP and idle state. Recovery evidence must not reuse
  the positive handoff path, and a successful run must append its categorical
  best-effort audit record. Never add a caller-selected fault mode to the
  production bootstrap. After the destructive fault, retry only bounded,
  explicitly typed `SshTransportError` failures with fresh frozen inputs;
  cloud-init, semantic remote/recovery, source, unit and state refusals remain
  immediate failures. Reboot readiness
  belongs inside that post-fault retry boundary and must never issue a second
  reboot. Exhausting those transport retries publishes no success evidence.

- **Mutation builds require sibling inputs** — `test-vpnd-mutants.sh` copies
  tracked working-tree files before using cargo-mutants in-place in that owned
  temporary tree. Never mutate the operator checkout or suppress its exit code.

- **SOPS snapshot filenames preserve YAML format** — disposable onboarding
  copies encrypted YAML to a `.yaml` snapshot because the canonical decrypt
  command infers its store from the filename. Keep the real SOPS round-trip
  regression; a mocked decrypt cannot detect this boundary.

- **Plugin path environment variables are not a complete isolation boundary** —
  Ansible also auto-discovers plugin subdirectories at playbook and role bases.
  Reject unsupported discovery/shadow-role paths before SSH; private cwd and
  disabled host_group_vars alone do not prevent a legacy vars plugin executing.

- **SSH connection timeout is not a session deadline** — bootstrap waits bound
  each SSH process group locally and each remote status query with GNU timeout.
  Remote deadline retries are distinct from an unresponsive SSH session; cloud-init
  exit codes 1 and 2 both refuse readiness even when the marker already exists.
  Keep raw cloud-init output suppressed and reclaim the owned SSH group on interruption.
- **First-boot SSH uses only its selected key** — the wait adapter must ignore
  operator SSH config with `-F /dev/null`, disable the agent with
  `IdentityAgent=none`, and pass `IdentitiesOnly=yes` with its `-i` key.
  Otherwise unrelated configured or agent keys may exhaust server auth attempts.
- **Staging observability leaf certificates carry their CA key ID** — OpenSSL 4
  strict verification rejects a CA-issued client certificate without an
  Authority Key Identifier. Keep it in the generated leaf extension file.
- **Rollback state must be readable before mutation** — enforce the same byte
  limit on serialized pending writes and reads, including base64 snapshots.
  SSH/job/monitor deadlines must leave room around the shared probe budget.
- **Tailnet boot recovery cannot depend on sshd runtime** — `ssh.service`
  creates `/run/sshd` after recovery. Inspect the complete effective policy
  with syntax-validating `sshd -G`; `-T` also tests daemon runtime and can
  refuse a valid configuration before SSH starts. Keep full policy comparison.
- **tailscaled readiness precedes backend readiness** — recovery alone waits
  for `NoState`/`Starting` within one 30-second monotonic budget shared with
  the post-logout status check. Bound each query by the remaining budget;
  malformed, unknown and authorization states refuse immediately. Never relax
  identity ownership or the SSH recovery dependency to repair a cold boot.
- **Shell-injection on operator-supplied input** — any script taking a host
  name, client name, or path uses `"$1"` quoting and `printf '%q'` when
  forwarding to nested shells. Never `eval`.
- **Encrypted retirement receipts are phase-bound** — a terminal receipt beside
  a prepared or candidate journal is foreign state and must refuse before the
  SOPS candidate is created or published. Reject orphan candidate siblings;
  do not infer recovery from ciphertext content without the exact journaled
  inode and before/after digests.
- **`mktemp` differs on macOS vs Linux** — operator workstations are both.
  When a controller owns cleanup, use an explicit template under its `TMPDIR`:
  macOS `mktemp -t` prefers the Darwin user temp directory over `TMPDIR`.
  Private precheck copies must remain inside controller cleanup even when a
  timeout or cancellation kills a child before its shell EXIT trap can run.
- **`age` keyring location** — `~/.config/sops/age/keys.txt` on Linux,
  `~/Library/Application Support/sops/age/keys.txt` on macOS. The wrapper
  scripts pick correctly via `${SOPS_AGE_KEY_FILE:-…}`; don't hard-code.
- **`audit-log.sh` failures must not break the parent script** — use
  `append-best-effort` (logs the error, exits 0) rather than `append`.
- **Python scripts must run under the venv-less system python3** — operator
  workstations don't all have uv/poetry. Use stdlib + the pinned deps in
  `requirements.in`. Don't import `requests` (use `urllib.request`).
- **Never run raw Terraform from an operator script** — it silently uses the active workspace. Set `PROVIDER` and `ENV` on `terraform-env.sh` instead.
- **Galaxy drift lookups read only their temp install** — `ansible-galaxy collection list --collections-path <tmp>` also reports the configured default paths such as `~/.ansible/collections`, listed first. `check-ansible-galaxy-updates.py` must select the entry keyed by the resolved temp `ansible_collections` dir (macOS `/tmp` is a symlink); taking the first match reports an operator's stale local copy as latest and passes outdated pins. CI runners have no default collections, so only the manual review on operator machines exposes a regression.
- **Active REALITY target monitoring is filtered-vantage only.** `monitor-reality-target.sh` rejects an absent or `unfiltered` vantage, resolves the active target through the canonical secrets gate, and persists only a target fingerprint plus technical IP/ASN/prefix observations. It requires two consecutive unhealthy runs before notifying and never edits SOPS or invokes deployment actions.
- **Burn-check textfile state is fail-loud** — `burn-check.sh` rewrites its
  Prometheus textfile from an EXIT trap. An external API failure removes stale
  reachability series and raises API-error plus incomplete-run gauges; a
  completed reachability failure keeps those gauges clear because it is a
  valid burn verdict, not a probe execution error.
