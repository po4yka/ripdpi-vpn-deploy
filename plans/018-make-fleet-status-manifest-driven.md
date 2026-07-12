# Plan 018: Make fleet status manifest-driven and machine-readable

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, do not edit `plans/README.md`; the reviewer maintains the index in the advisory checkout.
>
> **Dependency preparation (run first in the isolated worktree)**: start from commit `7bdba37`, then merge dependency commit `7a1c13e` with a Conventional Commit merge message so the original Plan 017 identity remains an ancestor. It must apply cleanly and preserve Plan 017's `docs/TESTING.md` and `scripts/CLAUDE.md` changes. Stop on conflict.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: 017 (`7a1c13e`, transitively 013)
- **Category**: direction
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`scripts/fleet-status.sh` gives a useful live table, but it reparses ad hoc remote state and has a TODO to consume the already-shipped node capability manifest. Its missing/unreachable states collapse into punctuation, capability comparisons require SSH-by-hand, and the global `vpnd --json` flag is ignored by `fleet status`. Add one versioned, non-secret status model that separates declared manifest capabilities from live observations, renders the existing human view with added capability context, and emits stable JSON for automation. A manifest is deployment evidence, not liveness proof; the implementation must never synthesize a single healthy verdict from declared state.

## Current state after dependency preparation

- `scripts/fleet-status.sh` parses `HOSTS=provider:environment,...`, reads Terraform outputs, performs a best-effort ASN lookup, SSHes for Xray version/config mtime/watchdog state, probes TCP/443, and prints a table.
- It has no CLI arguments or JSON mode. Its header TODO says to read `/var/lib/ripdpi-vpn-deploy/manifest.json` when capability columns grow.
- Missing Terraform output prints `(no tfout)` plus dashes. SSH failure produces `?|?|?`; manifest missing/invalid/unsupported cannot be distinguished because it is not read.
- `ansible/roles/node_manifest/templates/manifest.json.j2` emits schema version 1 with non-secret `generated_at`, hostname, provider/environment, enabled transports, public listeners, security controls, and recovery configuration.
- `ansible/roles/node_manifest/CLAUDE.md` makes the manifest explicitly late, non-secret, additive, deterministic, world-readable, and unsuitable for client/peer/credential detail.
- `tests/unit/test_node_manifest.py` pins the producer schema and forbidden secret vocabulary. Do not change the producer in this consumer plan.
- `vpnd` already exposes a global `--json` flag in `Context`; `vpnd/src/commands/fleet.rs` currently calls plain `make fleet-status`, so the flag has no effect.
- `Makefile:488-489` invokes the script without forwarding a JSON selector; its help describes only the human summary.
- `scripts/CLAUDE.md` says nontrivial data shaping belongs in stdlib Python while shell remains the operator entry point. Follow that pattern: Bash gathers bounded external observations; a new Python module validates/normalizes/renders.
- `vpnd/CLAUDE.md` says the Makefile/scripts surface is canonical and `vpnd` must map flags honestly through argv/Make variables.
- `docs/TESTING.md` on the Plan 017 baseline records 123 Rust tests and 537 collected Python tests. Live discovery during execution found that the dependency baseline already contains 133 Rust tests, so this plan's one new Rust unit test produces 134; five new Python unit tests produce 542 collected. Update the stale documented counts to 134 and 542 only after confirming both collections.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Dependency ancestry | `git merge-base --is-ancestor 7a1c13e HEAD` | exit 0 |
| Bash syntax | `bash -n scripts/fleet-status.sh` | exit 0 |
| Shell lint | `shellcheck -s bash -S warning scripts/fleet-status.sh` | exit 0, no diagnostics |
| Focused Python tests | `mise exec --no-deps -- python3 -m pytest tests/unit/test_fleet_status.py tests/unit/test_node_manifest.py -q` | eight tests pass (five consumer tests, including script integration, plus three producer tests) |
| Direct missing-output JSON | `HOSTS=unknown:prod scripts/fleet-status.sh --json | python3 -m json.tool >/dev/null` | exit 0; pure JSON on stdout |
| Focused Rust tests | `cd vpnd && cargo test --locked commands::fleet` | all fleet command tests pass |
| Full Rust regression | `cd vpnd && cargo test --locked` | all 134 tests pass |
| Rust lint | `cd vpnd && cargo clippy --locked --all-targets -- -D warnings` | exit 0 |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | 541 pass, 1 skip / 542 collected on this dependency baseline |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files the Plan 018 commit may modify relative to the Plan 017 dependency baseline):

- `scripts/fleet-status.sh`
- `scripts/fleet_status.py` (new)
- `tests/unit/test_fleet_status.py` (new)
- `Makefile`
- `vpnd/src/commands/fleet.rs`
- `docs/TESTING.md`
- `scripts/CLAUDE.md`
- `vpnd/CLAUDE.md`

**Out of scope** (do not modify):

- The node manifest producer/template/defaults/tasks/schema version, Ansible roles/playbooks, listener manifest, Terraform outputs, host registry, generated completions/manpages, snapshots, dependencies, or lockfiles.
- Adding secrets, client/peer identity, certificate material, subscription details, IP reputation, geography/carrier/operator labels, or raw remote command output to status JSON.
- Treating manifest presence/freshness as health, calculating an overall healthy/unhealthy verdict, triggering rotation/deploy/recovery, writing state, or changing remote nodes.
- Replacing SSH host-key behavior, ASN lookup semantics, TCP probing, Terraform workspace routing, or existing best-effort live observation behavior except to make failure states explicit.
- Adding a daemon/API/dashboard, polling loop, database, host-registry migration, network dependency, or new CLI flag; global `--json` already exists.
- Updating `CHANGELOG.md`, plans, generated docs, or any ninth file.

## Git workflow

- Branch: `codex/advisor-018-manifest-fleet-status`.
- Start from `7bdba37` and merge `7a1c13e` before editing; preserve the original dependency SHA as an ancestor.
- Create one focused incremental Conventional Commit: `feat(fleet): add manifest-driven JSON status`.
- Do not push, merge into the user's branch, or open a pull request.

## Steps

### Step 1: Define a strict non-secret fleet status model in stdlib Python

Create `scripts/fleet_status.py` with no third-party imports. It must expose importable pure functions used by tests and a small CLI used by the shell collector.

The top-level rendered JSON contract is:

```json
{
  "schema_version": 1,
  "hosts": []
}
```

Each host record has exactly these ownership layers:

- identity: `provider`, `environment`, `address` (nullable);
- `declared`: manifest-derived data with `status` (`ok`, `missing`, `invalid`, `unsupported`, `unavailable`), nullable `schema_version`, nullable `generated_at`, nullable `hostname`, and capability fields `enabled_transports`, `public_listeners`, `security_controls`, `recovery`;
- `observed`: live/best-effort fields `terraform_output` (`ok`/`missing`), `ssh` (`ok`/`unreachable`/`not_attempted`), nullable `asn`, nullable `xray_version`, nullable `config_updated_at`, `watchdog` (`ok`/`fail`/`unknown`), and `tcp_443` (`reachable`/`blocked`/`not_probed`).

Do not add `healthy`, `status` at host level, scores, recommendations, or inferred remediation.

Implement:

1. `normalize_manifest(raw, expected_provider, expected_environment, available)`:
   - `available=false` → declared `unavailable` (SSH/TF path prevented read);
   - empty raw when available → `missing`;
   - malformed JSON/non-object/wrong required field types/provider or environment mismatch → `invalid`;
   - integer `schema_version` other than 1 → `unsupported`, preserving only schema version/generated timestamp and returning empty/null capabilities;
   - valid version 1 → `ok` and exact sanitized capability values.
2. Treat `generated_at` as deployment metadata only. Preserve it as a string when valid; do not label stale/fresh or compare to wall-clock time.
3. Normalize unknown `?`, empty, or malformed live fields to null/`unknown`, never pass remote diagnostics through.
4. `build_record(...)` that combines explicit identity, declared, and observed layers.
5. `render_json(records)` using deterministic pretty JSON and a trailing newline.
6. `render_table(records)` that retains provider/environment/IP/ASN/Xray/config time/watchdog/TCP columns and adds `MANIFEST` plus a compact comma-joined `TRANSPORTS` column. Missing/unsupported/invalid states must be words, not ambiguous punctuation. Table output may truncate display strings but never mutate JSON.
7. CLI subcommands:
   - `record` accepts explicit non-secret scalar arguments, reads base64-encoded manifest bytes from stdin, writes exactly one compact JSON record to stdout;
   - `render [--json]` reads JSON Lines records from stdin and emits either pure JSON or the table.

Use `argparse`, `base64`, `json`, and stdlib only. Diagnostics go to stderr; stdout is data only.

**Verify**: focused tests cover every declared status, identity mismatch, separation from observed health, deterministic JSON, and table state words.

### Step 2: Make the Bash collector read the manifest and emit explicit observations

Refactor `scripts/fleet-status.sh` without changing its default human invocation:

- Parse only optional `--json`/`-h|--help`; reject unknown flags.
- Validate every `HOSTS` pair: provider is `upcloud|hetzner|vultr`, environment is the repository technical slug pattern, and exactly one colon separates them. Invalid input fails before external calls.
- Create an owner-private temporary JSONL file with portable `mktemp -t`, `umask 077`, and a cleanup trap.
- For missing/invalid Terraform IPv4, call the Python `record` command with `terraform_output=missing`, `ssh=not_attempted`, `tcp_443=not_probed`, and declared `unavailable`; do not SSH/probe.
- Preserve best-effort ASN behavior and normalize only `AS<number>`; discard unexpected output.
- Replace the remote three-field response with a bounded SSH response containing Xray version, config mtime, watchdog observation, and base64 of `/var/lib/ripdpi-vpn-deploy/manifest.json`. Use Linux `base64 -w 0` with a fallback that removes newlines if necessary. The manifest is explicitly non-secret, but never interpolate decoded JSON into a shell command.
- Distinguish successful SSH with missing manifest (`missing`) from SSH failure (`unavailable`). A malformed/unsupported manifest is determined only by Python.
- Preserve the current bounded TCP/443 observation and label it `reachable` or `blocked` only when an IP exists.
- For each host, pipe only manifest base64 on stdin to `fleet_status.py record` with all scalars quoted; append its single JSON line to the private file.
- After all hosts, call `fleet_status.py render` with `--json` when requested. In JSON mode stdout must contain only the JSON document; progress/errors stay stderr.

Do not use `eval`, raw Terraform, unbounded SSH, shell-built JSON, or delimiter parsing of decoded manifest data.

**Verify**: direct `HOSTS=unknown:prod ... --json` command emits a valid missing-output record without network access; syntax/ShellCheck pass.

### Step 3: Add focused consumer and shell-integration tests

Create exactly five test functions in `tests/unit/test_fleet_status.py`:

1. Valid schema-1 manifest yields `declared.status=ok`, preserves generated time/capabilities, and keeps observed fields separate.
2. Parametrized subcases cover missing, invalid JSON, wrong identity/types, unsupported schema, and unavailable without leaking raw input.
3. Unknown live values normalize to null/unknown and cannot create a host-level health verdict.
4. JSON/table renderers are deterministic, JSON has only top-level schema/hosts, and table contains explicit manifest/transport state words.
5. Run the real Bash script with `HOSTS=unknown:prod --json`; assert exit 0, stderr contains no data payload requirement, stdout parses, and the single record is Terraform-missing/SSH-not-attempted/manifest-unavailable/TCP-not-probed. This path must not require network stubs because unknown provider has no Terraform directory; if input validation requires a supported provider, instead use a supported provider with a temporary seam that avoids all external calls only if the seam is non-production and documented—STOP before adding broad command overrides.

Import `scripts/fleet_status.py` via `importlib` following `test_node_manifest.py`. Do not duplicate manifest producer rendering; focused command includes `test_node_manifest.py` to preserve producer/consumer compatibility.

After collection, update the Python count in `docs/TESTING.md` to exactly `542 collected` and add manifest-driven fleet status to the existing coverage sentence.

**Verify**: `python3 -m pytest --collect-only -q tests/unit/` reports 542 and focused tests pass.

### Step 4: Wire Make and vpnd JSON selection honestly

Update `Makefile`:

- Help text becomes `fleet-status [HOSTS=…] [JSON=1]` and describes declared capabilities plus live observations.
- The target calls `./scripts/fleet-status.sh $(if $(filter 1 true,$(JSON)),--json)` so plain Make remains human and `JSON=1` is explicit.

Refactor `vpnd/src/commands/fleet.rs` with a small `status_target(ctx)` helper:

- plain context returns `make::target(ctx, "fleet-status")`;
- `ctx.json` returns `make::target_with(ctx, "fleet-status", &[("JSON", "1")])`;
- `FleetAction::Status` runs that helper, preserving `--explain` behavior.

Add one Rust unit test function covering both contexts via `Cmd::explain()`: plain status lacks `JSON=1`; JSON context includes it after provider. Follow the local `fake_ctx` pattern, keep test-only unwrap/expect allowances scoped, and do not add CLI flags or snapshot updates.

Update the stale Rust count in `docs/TESTING.md` from 123 to 134 after `cargo test --locked -- --list` confirms the dependency baseline plus the one new test. This count correction is documentation drift discovered during execution, not ten extra tests introduced by Plan 018.

**Verify**: focused Rust test, full Rust test, and clippy pass; `vpnd --json fleet status --explain` includes `JSON=1` and plain explain does not (use `cargo run --locked -- --root .. --json fleet status --explain` only if clap ordering permits; the unit test is authoritative).

### Step 5: Record ownership boundaries in the two knowledge files

Update `scripts/CLAUDE.md` within its three-section/line budget:

- Design decision: fleet status collection is Bash, normalization/rendering is stdlib Python; JSON schema version 1 separates declared from observed.
- Pitfall: manifest timestamp/capability presence is not live health; preserve unavailable/invalid/unsupported states.

Update `vpnd/CLAUDE.md`:

- Design decision or done-well note: global `--json` must be forwarded to canonical Make/script surfaces when supported; fleet status uses `JSON=1` rather than reimplementing collection.
- Pitfall: machine-readable commands must keep stdout data-only and must not discard explicit partial/failure states.

Do not add broad architecture prose or reflow unrelated paragraphs.

### Step 6: Run regressions and commit normally

Run Bash syntax/ShellCheck, focused Python producer/consumer tests, direct missing-output JSON parse, full Python unit suite, focused/full Rust tests, and clippy. Inspect the complete incremental diff against Plan 017 and confirm exactly eight files, no manifest producer change, no secrets, no overall health verdict, and pure JSON stdout.

Stage exactly eight files and run `git diff --check --cached`. Commit normally with hooks enabled using `feat(fleet): add manifest-driven JSON status`; never skip hooks. After commit, verify Plan 017 ancestry, exact eight-file diff-tree, scoped gitleaks, and a clean worktree.

## Test plan

- Producer tests keep manifest schema 1 and secret exclusions stable.
- Consumer tests characterize all manifest availability/schema/identity states and prevent declared capabilities from becoming health.
- Missing-Terraform integration proves direct JSON remains valid without SSH/network.
- Rust test proves global JSON selection reaches the canonical Make target without duplicating fleet logic.
- Full Python/Rust/clippy/shell gates protect existing orchestration, CLI, and documented counts.

## Done criteria

- [ ] Default fleet status remains human-readable and gains explicit manifest/transport context.
- [ ] Direct `--json`, `make fleet-status JSON=1`, and `vpnd --json fleet status` select one versioned pure-JSON contract.
- [ ] Each record separates identity, declared manifest state/capabilities, and observed live state.
- [ ] Missing, unavailable, invalid, unsupported, and live failure states remain explicit; no overall health verdict exists.
- [ ] Manifest schema version and provider/environment/type checks fail closed without exposing raw data.
- [ ] Five new Python tests and one Rust test pass; documented counts are 542 Python and 134 Rust.
- [ ] Bash/Python/Rust/clippy/full regressions, hooks, diff hygiene, ancestry, and scoped gitleaks pass.
- [ ] Exactly eight Plan 018 files are committed; the executor reports the SHA; isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Plan 017 does not merge cleanly or its testing/knowledge changes are absent.
- Current manifest schema differs from version 1, contains secret-bearing fields, or cannot be retrieved without privilege changes.
- Machine-readable status requires changing the manifest producer, Terraform outputs, SSH permissions, host registry, generated completions, dependencies, or a ninth file.
- The missing-output integration path would contact a network/provider, or isolating it requires broad production command override seams.
- The required JSON model cannot preserve current live observations without shell-evaluating/embedding decoded manifest data.
- Actual test counts differ from 542 Python/134 Rust after exactly the named tests, or generated docs/snapshots require updates.
- Focused/full tests, syntax, ShellCheck, clippy, hooks, ancestry, or scans fail twice after one reasonable in-scope correction.
- Any secret, real credential/address, carrier/geography/operator identifier, external knowledge-store reference, new dependency, state write, or behavior-triggering automation is required.

## Maintenance notes

Schema ownership stays with the node-manifest role; this consumer supports version 1 explicitly and must surface future versions as unsupported until reviewed. JSON consumers should key on top-level schema version and per-host declared/observed states. Future dashboard, diff, or rotation work may consume this output, but must never reinterpret declared configuration as proof of reachability.
