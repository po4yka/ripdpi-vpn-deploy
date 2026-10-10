# vpnd — Python convenience CLI

## Design decisions

**Make owns operations.** Python command handlers delegate infrastructure work
to documented Make targets. Reconverge resolves exact inventory keys for the
selected environment/provider before the deployment controller's dry-run,
deploy and verify calls. `--explain` shows a redacted plan without executing it.

**One command definition.** `src/vpnd/cli.py` owns the standard-library parser,
global-flag precedence, help, completions and all twenty man pages. Add commands
there and an async `run(ctx, args)` handler under `src/vpnd/commands/`; dispatch
lives in `src/vpnd/__main__.py`. Completions are a context-free synchronous
handler. Test actual parser behavior and update operator guidance with changes.

**One package version.** `pyproject.toml` is the version authority. The
repository launcher is `scripts/vpnd.py`; installed execution reads distribution
metadata. Release packaging copies reviewed tracked source/docs and bundles
Jinja templates plus parser-generated manuals. Python 3.12, exact hashes and
an isolated offline installation replace the native executable distribution.

**State retains its formats.** The local TOML registry resolves host aliases to
environment/provider/IPs. TOML reads use the standard library; writes use
`tomli-w` and the private atomic writer. Secrets remain a read-only typed view
of descriptor-gated YAML. Shared strict loading preserves scalar semantics and
rejects duplicate mappings with categorical errors.

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
  IDs. Hypothesis properties retain the explicit regression seeds; snapshots
  retain machine-contract assertions.
- **Distribution checks exercise artifacts.** Package tests install offline into
  a private prefix, use packaged assets outside the checkout, verify every manual,
  and exercise failed/interrupted replacement. The five runtime packages have
  locked hashes plus reviewed license/source policy.

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
- **Respect capture lifetimes.** Doctor/matrix need group ownership and signal
  owners. Share/reconverge retain foreground captures and default signals during
  token input and confirmation. Kill before reaping; await cleanup rather than
  relying on garbage collection or an executor queue.
