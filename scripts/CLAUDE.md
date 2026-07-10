# scripts — operator entry points

## Design decisions

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + `PyYAML` / `Jinja2`.

**One file per operator verb** — `bootstrap-secrets.sh`, `rotate-secrets.sh`,
`fleet-rotate.sh`. The Makefile wraps these with `make <target>` shorthand.

**SOPS gate everywhere** — anything that reads decrypted secrets refuses
without `VPN_SECRETS_FILE` env or a freshly decrypted `/tmp/vpn-<env>.secrets.yaml`.
Never re-implement decryption.

**Audit-log is opt-out, not opt-in** — destructive scripts append to
`audit-log.sh append-best-effort` after a successful run. The `--no-audit`
flag exists for testing but is undocumented.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; new environments must be initialized through `make ... init`.

**Destroy is provider-aware and plan-verified** — `destroy.sh` maps each supported provider to its canonical server resource and checks that the destroy plan contains a delete action for that exact address before apply. Unknown providers fail before an override file is written.

**Xray migrations are changelog-driven** — `docs/XRAY-RELEASE-LINE.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

## What's done well

- **`set -euo pipefail` everywhere** — fail-loud is the default.
- **`shellcheck` in CI** — the `ci.yml` workflow runs shellcheck on every
  `.sh` file; warnings break the build.
- **Idempotent where it matters** — `validate-target`, `check-certs`,
  `audit-permissions` can run repeatedly with no side effects.
- **One script = one job** — no flag-driven multi-mode scripts. `new-client.sh`
  and `new-cohort.sh` are separate even though they share boilerplate.

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
