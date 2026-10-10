## Context

Task: `VPD-1791615284178957`. Baseline:
`5365cbd4b33dff5b3d0be0e1f8c5cb2c9d17ac50`. This is a planning-only change.
The current crate has 36 source files (including inline tests), 21 integration
test files and 271 Cargo lockfile packages. `test-inventory.md` enumerates 206
Rust test functions and ten directly referencing Python consumer suites; these
are static counts, not evidence that tests ran.

Source contracts: `vpnd/src/cli.rs`, `vpnd/src/main.rs`, `vpnd/CLAUDE.md`, runner
builders, state modules, protected_file.rs and command handlers. Normative
security requirements live in `openspec/specs/vpnd/`. The implementation must
refresh the baseline inventory if upstream changes before execution.

## Goals / Non-Goals

- Deliver the complete Python CLI and installed distribution, with all command
  behavior, structured data and security boundaries retained.
- Transfer all test assertions and properties before removing the old source.
- Retire active Rust tooling throughout development, CI and releases.
- Preserve Make, Terraform, Ansible, SOPS/age, existing shell utilities and the
  Go probe helper. The result is a Python operator CLI, not a rewrite of IaC.
- Preserve operator-owned state, secret schema, device identifiers and public
  bundle contracts. No real provider/SSH/decrypt operations belong to this task.
- Publish no release or PR during planning. Implementation delivery authority
  must be resolved separately; acceptance never implies a deployment.

## Decisions

### Package and entry points

Use `vpnd/pyproject.toml`, `vpnd/src/vpnd/`, `vpnd/tests/test_*.py` and a
repository entry point `scripts/vpnd.py`. Keep command handlers, context,
runner, protected files, registry, pages and matrix analysis as distinct modules
corresponding to the existing boundaries. A single Python command definition
feeds the standard-library parser, help, man pages and completion generation.
Preserve argv parsing before handler execution; global flags must work before
and after subcommands, without command defaults clobbering explicit globals.

Use Python 3.12, already pinned. Use standard-library process, async, signal,
filesystem, HTTP, JSON, TOML-read and archive facilities where appropriate.
Reuse existing PyYAML/Jinja2 and require HTML autoescape for recipient rendering.
Version authority moves from Cargo to the pyproject project version; installed
metadata and checkout execution must agree. Templates and release-time docs
are package data, not resources looked up in an arbitrary current directory.

Proposed production additions are `qrcode` for pure-Python SVG generation
(without Pillow) and `tomli-w` for registry/cache TOML serialization. They avoid
a new external QR runtime prerequisite and a custom serialization engine.
They expand the locked dependency/SBOM set and require Python 3.12/platform,
maintenance, vulnerability and license review. Their exact versions/hashes and
approval must be resolved before adding them during implementation; this plan
installs neither. A rejected dependency choice requires revising this design
before that slice, rather than silently implementing a homemade substitute.
Use Hypothesis for generated-property transfer and a pinned Python mutation
runner for the existing mutation contract. Build tooling is separately pinned;
no build backend may download unpinned inputs during release production.

### Complete command matrix

Global interface: `--explain`; `--env/-e` (VPN_ENV, default prod);
`--provider/-p` (VPN_PROVIDER, default upcloud); `--yes/-y`;
`--root` (VPN_DEPLOY_ROOT); help and version flags. Retain actual precedence,
short aliases and acceptance/rejection rules from cli.rs tests, including
duplicate/scoped flags. Parse failures return 2; runtime errors return 1;
successful commands return 0; matrix/owned-diagnostic interrupts return 130/143.

| Command | Arguments/actions to retain | Behavior/source |
|---|---|---|
| deploy | --skip-precheck, --tag-on-success | ordered check-prereqs, validate, decrypt, init, plan, apply, inventory, wait, deploy, verify, smoke-test; summary/confirmation and cleanup |
| reconverge | --host, --dry-run | registry/env/provider/inventory binding, decrypt/harden, init, plan, exact-limit dry-run, optional deploy/verify, cleanup |
| share | client, --qr, --type singbox/uri (default singbox), --out, exactly one of --token-stdin/--token-file | opaque URL/port, emit-singbox, escaped HTML/app cards, two SVGs, private writes |
| doctor | --host, --ai, --clip requiring --ai, --bundle | six Make diagnostics, resilient captured streams, redacted archive/prompt/clipboard, failure status |
| probe | --host, --profile p0/p1/p2/all (default all) | exact baseline profile targets and missing-host P1 notice |
| probe-matrix | --duration (default 4h), --poll-interval-seconds, --config, --output, --json | baseline default paths, config validation, control/cell loop, analysis, schema-3 report and journal |
| preflight | --skip-certs | conditional decrypt/harden then validate-secrets, spot-check-secrets, audit-permissions, optional check-certs |
| fleet status | none | fleet-status |
| fleet rotate | --plan required, --resume, --dry-run | canonical PLAN, RESUME/DRY_RUN assignments to fleet-rotate |
| fleet drift | none | drift-since-tag |
| host list | --json | sorted table or JSON array with name and all fields |
| host show | name, --json | pretty/compact JSON record; unknown host failure |
| host add | name, --env/--provider required, --ipv4/--ipv6 optional | TOML upsert, optional fields, atomic private save |
| host remove | name | exact record removal; missing record failure |
| ai-docs | --out (default ./ai-docs/) | llms.txt, llms-full.txt and per-document outputs from bundled docs |
| update | --explain in addition to global flag | bounded HTTPS advisory fetch, cached 24h, both tag schemes, no downgrade notices |
| completions | shell | case-insensitive bash/zsh/fish/powershell and pwsh alias; unknown shell error |

Preserve CLI behavior and data contracts, not accidental ANSI layout or generator
whitespace. Any changed human-output golden must retain every asserted command,
flag, default, link and message meaning and receive explicit review. Machine
JSON, matrix schema, archive member names and secrets redaction are not cosmetic.

### Security and process lifetime

Port the Make per-key allowlist and Terraform workspace wrapper without
loosening them. Every invocation carries ENV/PROVIDER/SECRETS_FILE and uses argv
construction. Secret values and file locations remain redacted in rendered
plans, errors, logs, diagnostics, clipboard and archives.

Use descriptor-open checks for final-component symlinks, FIFO nonblocking open,
regular-file type, current UID and private mode; harden through the same held
descriptor. Preserve valid private read-only files and refuse missing/empty
plaintext. Unique mode-0600 temporary files, sync and same-directory rename
retain crash-safe outputs. Preserve another writer's stale file. Registry
serialization retains its atomic save and existing last-write-wins behavior.

Foreground interactive commands retain their terminal semantics. Doctor and
matrix explicitly own captured process groups. Drain both pipes while waiting,
cancel/kill/reap only owned descendants, and preserve partial output. Use
structured task lifetime and explicit finally cleanup rather than relying on
Python garbage collection to mimic Rust Drop. Deploy/reconverge cleanup retains
the primary failure, and cleanup failure fails otherwise-successful results.

Explain is a no-operation plan for every command. Current host add/remove
ignore explain in their handler; implement the documented guarantee rather
than reproducing that discrepancy. This security correction is explicit in
the delta. Read-only discovery may inspect safe local configuration; inventory
operations/network calls remain unexecuted and unresolved limits stay visible.

### Packaging, releases and rollback

Use one platform-neutral Python wheel plus source distribution, with a locked
wheelhouse/artifact manifest for each of the four supported OS/architecture
installation surfaces. Installer behavior retains PREFIX/root guards and
existing provenance policy, verifies exact checksums before executing artifacts,
creates an isolated environment and installs offline with pinned hashes. Stage
a new versioned installation under PREFIX, smoke-test it, then atomically switch
the launcher; preserve the preceding installation on any failure. Document the
Python prerequisite and changed artifact names as the installation break.

Generate the SBOM from the actual packaged runtime dependency set. Preserve
SHA256SUMS, attestation, valid tag-to-source checks, reproducible builds from
the same exact source/locks and release-please version agreement. Package docs
from an explicit reviewed list and exclude credentials, inventory, operator
state, local caches and this machine's paths. Test wheel assets outside the repo.
Publication, pushing and release promotion require explicit authorization.

The existing installed Rust release may remain operator-owned during migration;
the shipped source has one implementation. Recovery selects the previous
verified complete release, or a normal changeset revert. It neither adds a
permanent fallback nor rewrites shared history or persisted configuration.

## Contracts and ownership

- CLI/package lane: `vpnd/`, `scripts/vpnd.py`, Python dependency inputs/locks.
- Safety lane: Python runner/protected-file/context/registry modules and their
  matching tests; no Terraform/Ansible controller behavior changes.
- Artifact lane: recipient template, QR, doctor/docs outputs and tests. Keep
  subscription-host's existing static directory interface unchanged.
- Delivery lane (serialize): root Makefile, mise.toml, pre-commit, requirements,
  `.github/workflows/{ci,_rust,release-vpnd,reproducible-build,mutants}.yml`,
  `.github/actions/vpnd-sbom/`, release-please/manifest, dependency automation,
  installer, CI selector/result aggregation and Python contract tests.
- Instruction/docs lane (serialize): root AGENTS.md, vpnd/CLAUDE.md, README,
  vpnd/README, docs/TESTING.md and all active runbook paths referencing Rust.
  Follow subtree CLAUDE.md guidance; symlinked AGENTS files remain symlinks.
- Task/OpenSpec metadata is one serialized lane through taskctl. Planning uses
  only this change and its portfolio record/board. Implementation must use a
  dedicated worktree and revalidate scope/status after changing checkouts.

## Risks / Trade-offs

- Lost tests hidden by file deletion: baseline transfer manifest maps every
  function and assertion to collected/passed Python node IDs; new upstream
  tests invalidate retirement until mapped. Parameter cases, seeds and snapshot
  data are included. Exact syntax/generator changes need reviewed equivalence.
- Lost signal/security semantics: real local process-tree, FIFO/symlink/race,
  file mode, timeout, crash/write-failure and partial-report tests on Linux/macOS.
- Lost self-contained binary: Python is now an explicit install prerequisite;
  isolated hash-locked installation and packaged assets preserve usability.
- New dependency risk: explicit approval/review and locks before introduction;
  no unpinned build isolation or Rust-dependent build backend.
- Matrix drift: pure analysis tests plus real local command scheduling,
  SIGINT/SIGTERM and JSONL durability tests preserve schema and timing behavior.
- Stale Rust lanes: inspect all tracked references, separating active consumers
  from historical records, then test full gates with Cargo/rustc absent.
- Existing specs mention clap and fixed stale-temp removal. This change makes
  parser authority language-independent and temp ownership match the stronger
  current unique-temp implementation. Other normative protections stay intact.

## Migration Plan

1. In an isolated worktree, run the complete baseline Rust suite through
   `build-gate -- make vpnd-test`, capture interface/assets and extend the static
   test inventory into a checked assertion-to-test transfer manifest. Use
   synthetic documents and local processes; no fleet/secret discovery.
2. Deliver the Python package/parser/launcher plus shared safety/state behavior,
   paired with their transferred tests. Keep temporary differential reference
   execution test-only; ship no incomplete handler as command parity.
3. Port deploy/reconverge/preflight/probe/fleet/host and their real local
   orchestration tests, then share/doctor/docs/update/completions/man pages.
4. Port matrix orchestration/analysis and all timing, cancellation and report
   cases. Run the complete Python suite, generated properties and snapshots.
5. Produce and verify Python artifacts/installer across the four platforms;
   switch CI/dependency/mutation/version/SBOM lanes atomically with contracts.
6. Remove Rust only after all mapped tests run and package tests pass. Preserve
   tracked data assets at their existing paths where consumed; move golden
   snapshot bodies with reviewed metadata changes. Leave ignored local state.
7. Run focused Python tests first, then `build-gate -- make check`, complete
   installed-artifact/platform/mutation/dependency gates and independent
   security review. Record exact source SHA and terminal required hosted CI
   before closure; if publication is not authorized, leave that evidence
   required and the implementation task open.

Future canonical checks: `make vpnd-test` (complete pytest suite),
`make vpnd-lint` (pinned Python lint/type validation), `make vpnd-package-check`
(build/install/resource/version/reproducibility checks), `make vpnd-parity-check`
(complete transfer/collection/pass manifest), `make vpnd-mutants` (real Python
mutation suite), `make vpnd-dependency-check` (locked input/SBOM/vulnerability
policy) and `make task-check`. These targets are requirements for future code,
not commands implemented or run by this planning change. Keep every test
mapped to one required CI lane; compiler-only target names are removed.
