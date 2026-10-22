# vpnd — Python convenience CLI

## Design decisions

Fleet status remains a Make operation over admitted inventory, with passive
observations separate from authenticated client-path health. Fleet rotation
forwards a versioned plan to the canonical controller; it does not interpret or
reset the controller's exact-plan journal or bypass its survivor/review gates.

Explicit diagnostic hosts carry their validated public address through each host-specific script. Fleet and local permission checks remain labeled global; external target canaries do not claim host-specific evidence. Explicit ASN probes keep a separate address-bound baseline.

Recipient URLs use the canonical inventory-host subscription port resolver when secrets omit a port. QR output is conditional in both rendering and publication; refreshing without QR removes only admitted owned QR files before publishing the page.

Remote import and QR targets use the existing bare `/sub/<token>` endpoint.
The backend serves JSON there; a filename suffix is not a second public alias.
Generated targets are tested against the actual local delivery handler and
the native nginx frontend, including expiry and revocation.

**Make owns operations.** Python command handlers delegate infrastructure work
to documented Make targets. Reconverge resolves exact inventory keys for the
selected environment/provider before the deployment controller's dry-run,
deploy and verify calls. `--explain` shows a redacted plan without executing it.
Each child Make invocation removes inherited recursion, flags and injected
Makefile controls. Structured output stays free of directory banners, and the
parent process environment remains unchanged.

**Reviews gate mutation.** `deploy` asks for terminal confirmation after
`make plan` and before `make apply`; `reconverge` asks after `make dry-run` and
before `make deploy`. `require_review` defaults to no, ignores `--yes` and runs
inside the cleanup boundary, so a declined or unavailable review still runs
`make clean`. Dispatch keeps default terminal signals, so the review alone maps
SIGINT, SIGQUIT, SIGTERM and SIGHUP to an ordinary failure that exits
128 + signal; otherwise Ctrl-C or a dropped session at the prompt would kill
vpnd with plaintext on disk. Around the whole pipeline and its cleanup,
`StopSignals` records the same four signals on the event loop; the pipeline
stops at the next step boundary, runs `make clean` and exits 128 + signal.
The prompt keeps its own handler because a blocking prompt stops the loop.
vpnd never kills the running Make step: terminal signals reach it directly,
and a killed Make could leave a child that writes plaintext after cleanup.
`StopSignals.cleanup` keeps `make clean` under the guard, so a signal there
still exits 128 + signal. An inherited ignored signal (SIGHUP under `nohup`)
stays ignored: a caught signal resets to the default action in Make children,
so guarding it would let a lost session kill a running apply.

**One command definition.** `src/vpnd/cli.py` owns the standard-library parser,
global-flag precedence, help, completions and all twenty man pages. Add commands
there and an async `run(ctx, args)` handler under `src/vpnd/commands/`; dispatch
lives in `src/vpnd/__main__.py`. Completions are a context-free synchronous
handler. Test actual parser behavior and update operator guidance with changes.

**One package version.** `pyproject.toml` is the version authority. The
repository launcher is `scripts/vpnd-cli.py`; installed execution reads distribution
metadata. Release packaging copies reviewed tracked source/docs and bundles
Jinja templates plus parser-generated manuals. Python 3.12, exact hashes and
an isolated offline installation replace the native executable distribution.
SBOM generation uses its own hash-pinned tool environment from
`sbom-requirements.txt`. Its optional schema-format libraries must never enter
the operator validation environment or change signed-policy acceptance.

**Documentation export follows the docs tree.** `ai-docs` walks `docs/`
recursively, skips the `tasks/`, `demo/` and `measurements/` folders that have
their own contracts, mirrors each page under `md/<folder>/<page>.md`, and
writes an `llms.txt` with one H2 per documentation folder in reading order and
an `## Optional` section for `archive/`. The committed `docs/llms.txt` is that
output; regenerate it when a page is added, moved or removed. A rerun into
the same `--out` removes only the pages listed in the `.vpnd-ai-docs`
manifest, so `--out` may point at a directory that holds other files; a tree
without a manifest is overwritten page by page, never deleted. The manifest is
written with the union of old and new pages before the first page write, so an
interrupted run leaves nothing untracked; every page is decoded before any
write; and a symlink at any component under `md/` makes the run refuse rather
than write or delete through it. The runbook excerpt map in `docs_bundle.py`
names pages relative to the docs root.

**State retains its formats.** The local TOML registry resolves host aliases to
environment/provider/IPs. TOML reads use the standard library; writes use
`tomli-w` and the private atomic writer. Secrets remain a read-only typed view
of descriptor-gated YAML. Shared strict loading preserves scalar semantics and
rejects duplicate mappings with categorical errors.

Lifecycle fixtures publish complete PID manifests by rename before readers observe them; file existence alone cannot admit a partially written process list.
Loopback release fixtures bound accept and thread cleanup even when no client
connects. Timeout tests require an observed request before claiming network proof.

After a successful cancellation signal, wait retries only reap the retained leader. Darwin rejects a repeated group signal once only its unreaped zombie remains; signal errors still propagate rather than counting as successful termination.

**Process ownership is explicit.** `src/vpnd/runner/process.py` (`Cmd`) carries argv,
environment, cwd and a description. Foreground operations retain terminal
behavior. Doctor and matrix captures opt into owned groups; each worker drains
pipes while holding an unreaped leader, kills owned descendants before reaping
on cancellation, and completes cleanup before returning. Matrix owns SIGINT
and SIGTERM so durable partial evidence precedes exits 130/143.

**Matrix owns orchestration and analysis.** Its shell calls remain canonical
Make targets. `src/vpnd/commands/probe_matrix.py` preserves fixed-rate scheduling,
concurrent cells, control/target validation, topology classifications, schema-3
JSON, per-tick JSONL journals and private persistent session locks. The exact
report snapshot and real lifecycle tests protect these contracts.

**Recipient artifacts remain private.** `src/vpnd/pages/recipient.py` uses Jinja2 with
mandatory HTML autoescaping and `StrictUndefined`. The source template is
`templates/recipient.html`; the installed template is package data. `share`
accepts an opaque token only through stdin or a current-owner private file.
`qrcode` produces both SVGs through the private atomic writer.

**Release recovery is transactional.** Verified flat wheel bundles carry a
platform/version/file manifest and locked runtime wheels. Installation validates
metadata, dependency closure, templates/docs and parser-derived manuals before
publishing. A persistent prefix lock serializes publication; rollback restores
previous native files or symlinks and pages after interruption. Recovery selects
a complete prior verified environment, without migrating operator state.

## What's done well

- **Safety contracts share implementations.** Make values use per-key
  expansion-safe allowlists; Terraform calls use `scripts/terraform-env.sh`.
  Secret/token files use held-descriptor owner/type/privacy checks and fd-based
  hardening. JSON/HTML/QR outputs use unique private temp files, sync and rename.
- **Diagnostics retain evidence.** Doctor continues after individual failures,
  keeps both streams and redacts every exported report/archive/clipboard surface.
- **Tests retain their baseline identity.** Source annotations and the checked
  transfer manifest map every baseline function to collected, passed Python node
  IDs against permanent `test-inventory.md`, independently of task archival.
  Hypothesis properties retain the explicit regression seeds; snapshots
  retain machine-contract assertions.
- **Distribution checks exercise artifacts.** Package tests install offline into
  a private prefix, use packaged assets outside the checkout, verify every manual,
  and exercise failed/interrupted replacement. The five runtime packages have
  locked hashes plus reviewed license/source policy.
  Real installation assertions read the expected version from `pyproject.toml`.

## Pitfalls

- **Stage new inputs before packaging or mutation.** Both use reviewed tracked
  working-tree files and require sibling docs, fixtures and scripts. Use
  `make vpnd-mutants`; `pyproject.toml` defines its full scope. The wrapper rejects
  partial selections and treats missing, empty, incomplete or technical results
  as failures. Never mutate the operator checkout.
- **Review snapshots semantically.** Files live under `tests/snapshots/`; inspect
  every changed command, flag, default, link and machine field. Preserve the exact
  schema-3 report snapshot and property seeds. Run `make vpnd-parity-check` after
  the complete `make vpnd-test`, without skipped or focused baseline cases.
- **Keep parser defaults deterministic in packaged docs.** Global flags must
  work at every nesting depth without subcommand defaults replacing explicit
  values. Generate release manuals with environment-derived defaults cleared;
  actual command parsing retains the operator's environment defaults.
- **Retain output escaping and redaction.** Keep Jinja autoescape enabled and
  sensitive paths registered before rendering invocations. Bearer URLs stay in
  protected recipient artifacts; diagnostics never export secret-file locations.
- **Plaintext stays volatile.** `XDG_RUNTIME_DIR` wins; fallback storage is a
  user-specific temporary directory. Pass that exact path to every Make call.
  `make decrypt` overwrites it; share/preflight check for existing plaintext
  first. Missing, empty or unsafe input must fail before dependent work.
- **Limits are inventory keys.** Match the `vpn` group, env/provider and
  `vpn_service_address`; reject absent, ambiguous or pattern-shaped matches.
  A cleanup failure fails success but never replaces a primary pipeline error.
- **Rotation names one alias.** `runner.ansible.rotate` takes one exact alias,
  passes it as `--limit` with `ENV` (the play refuses a host whose inventory env
  differs from it) and drops inherited `ANSIBLE_SKIP_TAGS`/`ANSIBLE_RUN_TAGS`;
  the play's `always`-tagged guard refuses a group, pattern or list, so a
  fleet-wide rotate is never built here. Its alias grammar is a copy of the
  guard's in `ansible/playbooks/tasks/exact-node.yml`;
  `tests/unit/test_operator_verb_scope.py` compares them, so a drift fails there
  (`vpnd/tests` cannot read the playbook: mutation copies have no `ansible/`).
  The builder exists for the permanent parity baseline and has no command
  caller; it skips the Make verb's clean-source, pre-check and inventory gates,
  so a real command must route through `make rotate-credentials`.
- **Respect capture lifetimes.** Doctor/matrix need group ownership and signal
  owners. Share/reconverge retain foreground captures and default signals during
  token input and confirmation. Kill before reaping; await cleanup rather than
  relying on garbage collection or an executor queue.
