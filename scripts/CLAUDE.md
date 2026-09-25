# scripts — operator entry points

## Design decisions

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + pinned `PyYAML`, `Jinja2`, or
`certifi` from `requirements.txt`.

**One file per operator verb** — `bootstrap-secrets.sh`, `rotate-secrets.sh`,
`fleet-rotate.sh`. The Makefile wraps these with `make <target>` shorthand.

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

**Xray migrations are changelog-driven** — `docs/XRAY-RELEASE-LINE.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Subsystem notes live in `scripts/DESIGN-NOTES.md`** — read the matching
section before changing: `tasks/taskctl.py`; the deploy controller and inventory
rendering; `destroy.sh` and staging cleanup; `emit-*.sh`; `fleet-inspect.py`;
liveness sentinels and probes (`*liveness*`, `probe-*`, `snell-refinement.py`,
real-VPS AWG evidence); `tailnet-*`; `observability-operator.py`; cloud-init
acceptance harnesses; SSH recovery installation.

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
- **Rollback state must be readable before mutation** — enforce the same byte
  limit on serialized pending writes and reads, including base64 snapshots.
  SSH/job/monitor deadlines must leave room around the shared probe budget.
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
- **Active REALITY target monitoring is filtered-vantage only.** `monitor-reality-target.sh` rejects an absent or `unfiltered` vantage, resolves the active target through the canonical secrets gate, and persists only a target fingerprint plus technical IP/ASN/prefix observations. It requires two consecutive unhealthy runs before notifying and never edits SOPS or invokes deployment actions.
- **Burn-check textfile state is fail-loud** — `burn-check.sh` rewrites its
  Prometheus textfile from an EXIT trap. An external API failure removes stale
  reachability series and raises API-error plus incomplete-run gauges; a
  completed reachability failure keeps those gauges clear because it is a
  valid burn verdict, not a probe execution error.
