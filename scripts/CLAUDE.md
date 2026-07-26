# scripts — operator entry points

## Design decisions

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + `PyYAML` / `Jinja2`.

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

**Audit-log is opt-out, not opt-in** — destructive scripts append to
`audit-log.sh append-best-effort` after a successful run. The `--no-audit`
flag exists for testing but is undocumented.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; new environments must be initialized through `make ... init`.

**Provider roots share one inventory schema** — UpCloud, Hetzner, Vultr, and Scaleway export the same canonical outputs, so `render-inventory.sh` stays provider-neutral. Add provider-specific inventory code only when a control-plane address needs extra guest convergence proof, as Vultr's secondary IPv4 does.

**Bundle topology is host-order independent** — `emit-bundle.sh` aggregates
split-hop ingress and realm metadata across every `HOSTS` entry. Never infer
client-facing topology from the first host; conflicting non-null realm IDs
must fail closed.

**Vultr secondary IPv4 inventory is live-gated** — Terraform output proves allocation only. `render-inventory.sh` polls the primary SSH endpoint and publishes `honeypot_listen_addr` only after the exact IPv4 appears on a guest interface.

**Destroy is provider-aware and plan-verified** — `destroy.sh` maps each supported provider to its canonical server resource and checks that the destroy plan contains a delete action for that exact address before apply. Unknown providers fail before an override file is written.

**Xray migrations are changelog-driven** — `docs/XRAY-RELEASE-LINE.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Probe-matrix drivers keep secrets file-bound** — `probe-matrix-driver.py` reads an owner-controlled `0600` target profile, writes Xray configs only inside `0700` temporary directories, and sends MTProxy requests to the pinned Go helper on stdin. Keep credentials out of argv, environment variables, diagnostics, and reports; only same-tick failures with a healthy direct control can become `blocked`.

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

- **Shell-injection on operator-supplied input** — any script taking a host
  name, client name, or path uses `"$1"` quoting and `printf '%q'` when
  forwarding to nested shells. Never `eval`.
- **`mktemp` differs on macOS vs Linux** — operator workstations are both.
  Use `mktemp -t prefix.XXXXXX` (works on both) rather than the bare form.
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

**Snell refinement is evidence-only** — `snell-refinement.py` runs only from an explicitly identified filtered client path, keeps all candidate proxies on localhost, interleaves exact-size direct controls, and persists schema-validated redacted reports beneath the XDG state directory. It never edits deployment, rotation, or route state; runtime, configuration, and authentication failures are `error`, not blocking evidence.

**Sentinel privilege is fixed-command only** — AmneziaWG needs a temporary network namespace, so onboarding installs one root-owned runner and one exact sudoers command. Never accept a config path or private key through the remote command line, and always delete the namespace in a `finally`/trap path.

**Real-VPS AWG evidence is executor-neutral, generation-bound, and transactional** — the local systemd timer is primary and the compatible workflow is optional. Both deploy an exact source archive, bind the manifest to executor/entrypoint/invocation provenance, require healthy direct TCP+UDP controls before an AWG failure is classified as product-facing, observe service/config generation changes, reject the old PSK, and commit or roll back the client/server pair. Old-key rejection passes only when both TCP and UDP fail; success of either is `OLD_KEY_STILL_ACCEPTED` and fails closed. Local installation snapshots a detached exact-SHA root-owned checkout, copies validated private hooks to immutable fixed paths, hardens the toolchain tree to root-only read/execute permissions, and shares one install/run lock. `latest.json` exists only after a strict PASS; valid failures stay versioned and malformed output is quarantined. Exit 75 means infrastructure unavailable, and only strict counters, enum verdicts, hashed identities, and digests may leave the sentinel.
