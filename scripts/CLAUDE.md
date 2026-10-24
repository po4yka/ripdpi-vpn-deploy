# scripts — operator entry points

## Design decisions

**Subsystem ownership and design notes live in [DESIGN-NOTES.md](DESIGN-NOTES.md)** — before
changing a listed subsystem, read its matching section:

| Before changing | Read |
|---|---|
| Task lifecycle (`tasks/taskctl.py`) | [Task lifecycle](DESIGN-NOTES.md#task-lifecycle--taskstaskctlpy) |
| Deploy controller and inventory rendering | [Deploy and inventory](DESIGN-NOTES.md#deploy-controller-and-inventory--deploy-controllerpy-deploy-source-identitysh-bootstrap_readinesspy-render-inventorysh) |
| Provider checks, `destroy.sh` and staging cleanup | [Provider lifecycle](DESIGN-NOTES.md#provider-control-plane-destroy-and-staging-cleanup--destroysh-check-vultr-control-planepy-ci-staging-) |
| Client emission (`emit-*.sh`) | [Client emission](DESIGN-NOTES.md#client-emission--emit-bundlesh-emit-singboxsh) |
| Passive inspection (`fleet-inspect.py`) | [Fleet inspection](DESIGN-NOTES.md#fleet-inspection--fleet-inspectpy) |
| Liveness sentinels, Snell refinement and real-VPS AWG evidence | [Liveness and retirement](DESIGN-NOTES.md#liveness-sentinels-disposable-staging-and-retirement) |
| Probe scripts (`probe-*.sh`) | [Probe scripts](DESIGN-NOTES.md#probe-scripts-probe-sh) |
| Probe matrix (`probe-matrix-driver.py`) | [Probe matrix](DESIGN-NOTES.md#probe-matrix--probe-matrix-driverpy) |
| Tailnet (`tailnet-*`) | [Tailnet](DESIGN-NOTES.md#tailnet--tailnet-) |
| Observability (`observability-operator.py`) | [Observability](DESIGN-NOTES.md#observability--observability-operatorpy) |
| Cloud-init acceptance harnesses | [Cloud-init acceptance](DESIGN-NOTES.md#cloud-init-acceptance--schema-fallback-and-cloud-final-restart-harness) |
| SSH recovery installation | [SSH recovery](DESIGN-NOTES.md#ssh-recovery--install-sshd-recoverypy-make-install-ssh-recovery) |
| Any other script (operator boundaries, verbs, blue-green, recovery, delivery) | [Operator boundaries](DESIGN-NOTES.md#operator-boundaries--cross-cutting-decisions); search it for the script name instead of reading it whole |

**Generated documentation mirrors its source** — `docs-reference.py` parses the
Makefile `help` recipe as text, builds the vpnd argparse tree without running a
command, and calls the `ai-docs` emitter into a temporary directory to produce
`docs/reference/make-targets.md`, `docs/reference/vpnd-commands.md` and
`docs/llms.txt`. `--check` compares and exits 1 on drift; `make docs-check`
runs it, and `make test-unit` covers it through `test_docs_reference.py`. It reads no credentials, inventory or secrets.
Change the help text or the parser and run `make docs-reference`; never edit
the generated pages.

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + pinned `PyYAML`, `Jinja2`, or
`certifi` from `requirements.txt`.

**SOPS gate everywhere** — anything that reads decrypted secrets refuses
without `VPN_SECRETS_FILE` or the Make-resolved `SECRETS_FILE` produced by
`make decrypt`. Never assume `/tmp`, and never re-implement decryption.

**Destroy confirms a parsed hostname** — `destroy.sh` reads only a quoted
`server_name` from the tfvars file and refuses before Terraform when there is
none. Its EXIT trap removes the ordinary saved destroy plan on every exit.

**Destructive scripts always audit** — they append to
`audit-log.sh append-best-effort` after a successful run; there is no
opt-out flag.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; the environment alias `default` is refused. New environments must be initialized through `make ... init`.

## What's done well

- **Promotion-intent preparation is local** — `prepare-disposable-promotion-intent.py` consumes literal environment inputs through an isolated Make target, reads one private JSON configuration and uses the existing disposable validator. It publishes a no-clobber private intent plus exact-alias mapping, keeps credentials unopened and reports no remote success. Retained partial output is not a completed mapping; runtime readiness and authority remain controller checks.

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

- Ubuntu Molecule consumers use one immutable digest from the repository-owned,
  security-gated publication. Refresh every consumer and pin regression together;
  never waive fixable HIGH or CRITICAL image findings.

- **Cloud-init CI bindings are fixed** — render-cloud-init-ci.py encodes the
  shared template's scalar expressions for synthetic fixtures and refuses unknown
  expressions. Real Terraform serialization tests prove parsed parity; keep both
  renderers aligned when changing template expressions.

- **Saved-plan policy precedes operator apply** — `policy-plan.sh`
  privately copies the regular environment plan, uses the canonical workspace
  router for show/apply, and evaluates that same copy through
  `check-tf-plan.sh` and its single `terraform-plan-policy.py` evaluator. Temporary binary/JSON files are private and cleaned
  on exit. Evaluator failures, malformed results and zero policy checks refuse
  apply; diagnostics identify policy namespaces without printing plan content.

- Bootstrap lifecycle is bound to both the routed workspace and the canonical
  `vpn_build_environment`, then checked against the root-owned cloud-init
  marker. Named production workspaces retain their identity; disposable
  workspaces always require cleanup authority even with a production label.
  The renderer emits that label as a shell-quoted JSON string for Ansible's
  typed INI parser. `fleet_inspection` preserves the JSON text; bootstrap must
  decode it once before comparison, rather than comparing its literal quotes.

- **Bootstrap installer failures retain bounded Ansible diagnostics.** The
  sanitized child receives no enrollment key and retains no_log on sensitive
  status tasks. Capture at most 1 MiB and publish failed-play context only on
  stderr; keep structured controller stdout unchanged.

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
  tracked working-tree files before running Python mutmut in that owned
  temporary tree. Never mutate the operator checkout or suppress its exit code.
  Completed killed and timeout outcomes are detected mutations; survivors
  remain exit 2. Empty, partial, unexecuted or technically failed runs stay red.

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
  A private session supervisor reports command status without exiting. Keep it
  unreaped until group cleanup, so the group identity cannot be recycled. Command
  descendants inherit neither control nor status descriptors. Signal refusal
  remains categorical failure; control-channel EOF and unexpected status-channel
  errors independently reclaim the group. Bounded fallback wait or signal failure
  must retain the categorical cleanup error without exposing supervisor argv.
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
  the identity query and post-logout status check. Poll every recovery status
  observation and bound each query by the remaining budget;
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
  Match captured TLS markers in the shell: an early pipeline reader can SIGPIPE
  a still-writing producer under `pipefail`, falsely reporting a healthy path as blocked.
- **Burn-check textfile state is fail-loud** — `burn-check.sh` rewrites its
  Prometheus textfile from an EXIT trap. An external API failure removes stale
  reachability series and raises API-error plus incomplete-run gauges; a
  completed reachability failure keeps those gauges clear because it is a
  valid burn verdict, not a probe execution error.

- Existing-node bootstrap has three operator verbs: console rendering, read-only
  policy inspection, and enrollment. The RAM revoker and firewall replacement
  share a coordination lock; durable rollback always uses bridge-free policy.
  A reviewed legacy digest is not permission to adopt unexplained runtime drift.

- Tailnet firewall foundations flush rules atomically while preserving dynamic
  timed enforcement sets. Only the two exact static SSH source sets are replaced
  before the transaction-owned include, so removed approvals cannot survive.

`build-native-naive-test.sh` supplies the exact composite used by native tests,
with repository-pinned Go and a separate scoped GOBIN/GOPATH/cache. It never
substitutes stock Caddy. Local compilation uses the machine build gate; CI
keeps compilation at two workers and passes the verified output explicitly.

Operator alert drills bind the verified controller source and a unique technical policy nonce. They wait for an authenticated relay API receipt for that exact nonce and start time before resolution; submission and receiver selection alone cannot prove delivery. Human receipt remains separate.

Client delivery/drift changes must preserve the in-memory renderer and private
HMAC authority lifecycle described in [Private client delivery identity](DESIGN-NOTES.md#private-client-delivery-identity).
Issuance verifies staged ciphertext before remote publication under the shared
lock. Local SOPS and remote delivery are separate systems: after interruption
or a post-publication failure, reconcile the delivered artifact before retrying.
The callback marks external publication before the first mutating SSH attempt,
since a failed reply can follow a completed write. Subsequent failures or
interruptions return a reconciliation warning, including failed local replacement.
Validation-only callbacks leave that marker unset.

The encrypted client transaction runs its verified publication callback under
the stable lock even when plaintext registry state is unchanged. Same-second
refresh must redeliver without manufacturing an encrypted state change.

Profile and subscription dispatchers put the selected device after `--` while
retaining the client-first shell interface. Leading-dash device names stay
literal data through Python argument parsing; Make drift uses the same delimiter.

Enabled transport authority must contain nonempty typed credentials and SNI
before publication. Malformed consumed authority returns a categorical refusal;
missing optional QR tooling retains the committed delivery and machine-token
mode keeps its early exit without QR side effects.

The private identity binds the full enrolled AWG peer public key as well as its
instance. A coherent peer/recovery-key rotation can leave placeholder-based
exported JSON unchanged; it must still report stale without publishing key metadata.
Both typed device addresses and the resolved MTU are consumed payload inputs.
The coordinated dual-stack contract, exporter and runtime forwarding must land
together; the shared renderer must not keep a single-address or fixed-MTU path.

An explicit per-host cohort bypasses inventory hostname lookup: endpoint-only
AWG callers do not consume a hostname and must retain their export path.

Native acceptance fixtures cross unit and integration directories. Keep the
selector's native group closed over every consuming job, including changes
under `tests/native/`; a Python-only selection can omit real-engine acceptance. The portable-test exception uses a broad textual reachability closure, so a false positive only selects more CI.

REALITY validation shares `reality_target_validation.py` across point-in-time and
recurring callers. It normalizes comma/whitespace names once, verifies each SNI
through a trusted TLS 1.3 handshake with SAN-only hostname matching and H2 ALPN,
and forces HTTP to the same resolved address. Blocking DNS, TLS, HTTP, metadata,
and secret acquisition use the retained-session supervisor in
`bootstrap_readiness.py`; per-stage and aggregate budgets include all pairs.
Reports contain categories and counts, never target names or tool diagnostics.
Owned self-steal probes require an explicit service endpoint and exact owned SNI;
remote probes reject loopback endpoints. Ordinary HTTP is hygiene only. Optional
curl-impersonate 0.6.1 Chrome116 compatibility requires exact binary and profile
hashes and an actual handshake; it never establishes filtered survival or grants
promotion authority. No validator installs a client, edits secrets or deploys.

Task deletion audits compare against the explicit trusted base while retaining
feature first-parent lifecycle history. Importing a purge already in that base
is not a new deletion when no issue, execution or receipt changed outside it.
Earlier active-state imports must match the unique latest common ancestor with
that base exactly, including imports carried by another feature parent that
contains that ancestor and preserves its projection. Scan every introduced
commit across the full DAG, including each carrier's own history.
Stale ancestor imports after a newer base state, independent
lifecycle edits and merge-only resurrection retain the full audit.

The monitor wraps the canonical REALITY collector in one owned process session and parent-owned temporary directory. Invalid explicit target, name, mode and owned-public prerequisites refuse before missing private defaults are loaded.

Device revocation also admits exact published grants after source credentials were
already removed. Reconcile every declared runtime and report the retained native
profile count; absent preimages never imply that an old-key probe was executed.
