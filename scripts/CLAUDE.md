# scripts — operator entry points

## Design decisions

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + pinned `PyYAML`, `Jinja2`, or
`certifi` from `requirements.txt`.

**One file per operator verb** — `bootstrap-secrets.sh`, `rotate-secrets.sh`,
`fleet-rotate.sh`. The Makefile wraps these with `make <target>` shorthand.

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

**SOPS gate everywhere** — anything that reads decrypted secrets refuses
without `VPN_SECRETS_FILE` or the Make-resolved `SECRETS_FILE` produced by
`make decrypt`. Never assume `/tmp`, and never re-implement decryption.

**Runtime bundle validation is a narrow SOPS exception** — a client-side
materialized bundle is not an Ansible secrets document. The explicit
`validate-bundle.py --runtime-materialized` mode may read it only as a
same-owner `0600` regular file through a symlink-free, owner-controlled path,
redacts the key in memory, and never rewrites or logs the artifact.

**Audit-log is opt-out, not opt-in** — destructive scripts append to
`audit-log.sh append-best-effort` after a successful run. The `--no-audit`
flag exists for testing but is undocumented.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; new environments must be initialized through `make ... init`.

**Vultr control-plane access fails before Terraform** — state-changing and refresh-capable Vultr commands run a redacted authenticated API preflight through `check-vultr-control-plane.py`. Keep the key environment-only; classify exact-IP allowlist rejection separately from credential and network failures, and never print the rejected egress address or response body.

**Provider roots share one inventory schema** — UpCloud, Hetzner, Vultr, and Scaleway export the same canonical outputs, so `render-inventory.sh` stays provider-neutral. Add provider-specific inventory code only when a control-plane address needs extra guest convergence proof, as Vultr's secondary IPv4 does.

**Inventory inputs fail before publication** — nonempty cohort slugs must name an existing `group_vars/vpn-*.yml` profile, and host aliases must be unique across provider/environment pairs. Reject malformed profiles before Terraform calls and preserve the last valid inventory on either failure.

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

**Bundle topology is host-order independent** — `emit-bundle.sh` aggregates
split-hop ingress and realm metadata across every `HOSTS` entry. Never infer
client-facing topology from the first host; conflicting non-null realm IDs
must fail closed.

**Client formats are capability-separated** — `emit-singbox.sh` defaults to
official sing-box P0/P2 syntax and must pass the pinned upstream parser. Only
`emit-bundle.sh` selects the RIPDPI format that carries P1 XHTTP; never leak an
XHTTP outbound into the standard subscription.

**Share emission reuses authoritative plaintext** — `emit-singbox.sh` reads
explicit `VPN_SECRETS_FILE` once through a no-follow, nonblocking descriptor
with current-owner/private-mode checks, then shares its JSON snapshot across
hosts. Invalid plaintext never falls back to SOPS; `SOPS_FILES` is ambiguous
with that shared input and is rejected. Direct script calls without plaintext
retain per-host SOPS inputs.

**Vultr secondary IPv4 inventory is live-gated** — Terraform output proves allocation only. `render-inventory.sh` polls the primary SSH endpoint and publishes `honeypot_listen_addr` only after the exact IPv4 appears on a guest interface.

**Destroy is provider-aware and plan-verified** — `destroy.sh` maps each supported provider to its canonical server resource and checks that the destroy plan contains a delete action for that exact address before apply. Unknown providers fail before an override file is written. Operator `ci-staging-*` environments use dedicated literal-safe Make goals and the component-wise no-follow mode-0600 manifest from `staging-cleanup-guard.py`; it derives IDs and digest from the same state bytes, binds the exact API username/provider/environment/workspace and provider-reported creation time to a fixed 36/44/47-hour schedule, preserves shared inventory, binds authorization/plan/pre-apply to one evidence inode, rejects every non-delete or foreign plan action, and audits only after exact-account typed provider absence in that same inode. Post-expiry absence finalization requires a durable pre-expiry apply marker and is labeled late.

**Staging cleanup accepts one ambient UpCloud auth mode** — prefer `UPCLOUD_TOKEN`; one complete primary or API-alias username/password pair remains supported. The Make boundary rejects command-line credentials before expansion, exports only the canonical selected mode, and keeps authorization out of tfvars and diagnostics.

**Xray migrations are changelog-driven** — `docs/XRAY-RELEASE-LINE.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Probe-matrix drivers keep secrets file-bound** — `probe-matrix-driver.py` reads an owner-controlled `0600` target profile, writes Xray configs only inside `0700` temporary directories, and sends MTProxy requests to the pinned Go helper on stdin. Keep credentials out of argv, environment variables, diagnostics, and reports; only same-tick failures with a healthy direct control can become `blocked`.

**Passive inspection has no deployment prerequisites** — `fleet-inspect.py`
reads an explicit existing INI subset and sends the stdlib collector on strict
SSH stdin. Keep inventory parsing non-executable and local/remote reads bounded
and no-follow. The controller validates every output field. Do not add restic,
watchdog, readiness, Ansible or provider calls to fill absent evidence.

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

**SSH recovery installation has an early privacy guard** — the dedicated
controller rejects enabled Ansible debug before inventory processing, forwards
`ANSIBLE_DEBUG=false` to override config defaults, and validates exact aliases
and clean source before Ansible. It isolates the selected alias from external
host/group vars, allows only tool/home/locale environment inheritance, and uses
portable strict SSH options for transfers. Caller fields remain literal data
through Make and argv; no general site/backup task runs during installation.

## What's done well

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

- **Plugin path environment variables are not a complete isolation boundary** —
  Ansible also auto-discovers plugin subdirectories at playbook and role bases.
  Reject unsupported discovery/shadow-role paths before SSH; private cwd and
  disabled host_group_vars alone do not prevent a legacy vars plugin executing.

- **SSH connection timeout is not a session deadline** — bootstrap waits bound
  each SSH process group locally and each remote status query with GNU timeout.
  Remote deadline retries are distinct from an unresponsive SSH session; cloud-init
  exit codes 1 and 2 both refuse readiness even when the marker already exists.
  Keep raw cloud-init output suppressed and reclaim the owned SSH group on interruption.
- **Rollback state must be readable before mutation** — enforce the same byte
  limit on serialized pending writes and reads, including base64 snapshots.
  SSH/job/monitor deadlines must leave room around the shared probe budget.
- **Shell-injection on operator-supplied input** — any script taking a host
  name, client name, or path uses `"$1"` quoting and `printf '%q'` when
  forwarding to nested shells. Never `eval`.
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
- **Active REALITY target monitoring is filtered-vantage only.** `monitor-reality-target.sh` rejects an absent or `unfiltered` vantage, resolves the active target through the canonical secrets gate, and persists only a target fingerprint plus technical IP/ASN/prefix observations. It requires two consecutive unhealthy runs before notifying and never edits SOPS or invokes deployment actions.
- **Burn-check textfile state is fail-loud** — `burn-check.sh` rewrites its
  Prometheus textfile from an EXIT trap. An external API failure removes stale
  reachability series and raises API-error plus incomplete-run gauges; a
  completed reachability failure keeps those gauges clear because it is a
  valid burn verdict, not a probe execution error.

## Probe scripts (`probe-*.sh`)

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
  output — no carrier/ISP/geographic brand names anywhere (root CLAUDE.md).
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

**Real-VPS AWG evidence is executor-neutral, generation-bound, and transactional** — the local systemd timer is primary and the compatible workflow is optional. Both deploy an exact source archive, bind the manifest to executor/entrypoint/invocation provenance, require healthy direct TCP+UDP controls before an AWG failure is classified as product-facing, observe service/config generation changes, reject the old PSK, and commit or roll back the client/server pair. Old-key rejection passes only when both TCP and UDP fail; success of either is `OLD_KEY_STILL_ACCEPTED` and fails closed. Local installation snapshots a detached exact-SHA root-owned checkout, copies validated private hooks to immutable fixed paths, hardens the toolchain tree to root-only read/execute permissions, and shares one install/run lock. `latest.json` exists only after a strict PASS; valid failures stay versioned and malformed output is quarantined. Exit 75 means infrastructure unavailable, and only strict counters, enum verdicts, hashed identities, and digests may leave the sentinel.
