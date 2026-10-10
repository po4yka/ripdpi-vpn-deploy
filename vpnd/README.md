# vpnd

Convenience CLI for [vpn-deploy](../).

`vpnd` is a Python 3.12 front door for the existing Makefile, Terraform roots,
Ansible playbooks and SOPS-encrypted secrets. Make and `scripts/` remain the
canonical operator surface. The command definition in
[`src/vpnd/cli.py`](src/vpnd/cli.py) drives parsing, help, completions and man
pages. Design decisions live in [`CLAUDE.md`](CLAUDE.md).

## Install

**Installation contract break:** releases now ship Python wheels and offline
wheel bundles instead of native executable binaries. Python 3.12 is required
on the operator machine. Linux and macOS x86_64/arm64 remain supported.

Download and inspect the repository installer, then run it with a writable
prefix:

```bash
PREFIX="$HOME/.local" bash scripts/install-vpnd.sh
"$HOME/.local/bin/vpnd" --version
```

The installer checks the bundle checksum and retains the existing optional
GitHub provenance policy: `gh attestation verify` is required when `gh` is
available and `VPND_SKIP_ATTESTATION` is unset; absent `gh` produces a warning.
Root installation requires explicit `ALLOW_ROOT=1`.

Each `vpnd-<target>.tar.gz` contains the application wheel, exact hash-locked
runtime wheels, `requirements.txt`, `MANIFEST.json` and the verified installer.
Installation creates an isolated environment under `PREFIX/lib/vpnd/releases`,
uses offline pip installation, checks dependency closure and resources, and
then publishes the launcher and man pages. Failed or interrupted publication
restores the previous command and pages. Prior verified environments remain
available for whole-release recovery.

The release also supplies `vpnd-X.Y.Z-py3-none-any.whl` and
`vpnd-X.Y.Z.tar.gz`. Templates, reviewed tracked documentation and generated
manuals are package resources. The five runtime packages are PyYAML, Jinja2,
MarkupSafe, qrcode and tomli-w; their pins/hashes live in `requirements.txt`
inside this directory. Source, reviewed license-file hashes and allowed SPDX
licenses are checked by `dependency-policy.json` and the dependency gate.

## Develop

From the repository root, use the pinned toolchain and hash-locked tooling:

```bash
mise install
mise exec -- python3 -m pip install --require-hashes --no-deps -r requirements.txt
mise exec -- python3 scripts/vpnd-cli.py --help
make vpnd-test vpnd-lint vpnd-parity-check
make vpnd-package-check vpnd-dependency-check
```

These Python paths require no Rust development toolchain. `vpnd-test` runs the
complete pytest suite; the transfer manifest and parity gate preserve every
baseline assertion, property, seed and snapshot. The package gate builds
reproducible wheel/source artifacts and exercises a real isolated installation
outside the checkout.

For mutation checks, stage new inputs and run `make vpnd-mutants`. The wrapper
uses a disposable tracked working-tree copy with sibling docs, fixtures and
scripts. `pyproject.toml` defines the mutation scope. Empty, incomplete,
uncovered, timed-out or technically failed runs fail; exit 2 denotes verified
completed results containing survivors. Reports are retained per invocation
under `vpnd/mutants/`. See [testing guidance](../docs/TESTING.md).

## Use

The twelve top-level commands preserve the existing operator interface:

| Command | Purpose |
|---|---|
| `deploy` | Confirm and run the ordered deployment pipeline with cleanup |
| `reconverge` | Resolve exact inventory hosts and run dry-run/deploy/verify |
| `share` | Private recipient HTML, sing-box JSON and optional QR SVGs |
| `doctor` | Resilient diagnostics, redacted AI prompt, clipboard or archive |
| `probe` | P0/P1/P2 profile probes |
| `probe-matrix` | Concurrent topology-aware sweeps, schema-3 reports and JSONL checkpoints |
| `preflight` | Secrets, permissions and optional certificate guards |
| `fleet` | `status`, `rotate` and `drift` |
| `host` | Local TOML registry `list`, `show`, `add` and `remove` |
| `ai-docs` | `llms.txt`, `llms-full.txt` and per-document Markdown |
| `update` | Bounded advisory release check with a 24-hour cache |
| `completions` | Bash, Zsh, Fish and PowerShell; `pwsh` is an alias |

```bash
vpnd deploy --explain
vpnd reconverge --env prod --dry-run
printf '%s\n' "$TOKEN" | vpnd share phone --qr --token-stdin
vpnd share phone --token-file ~/.config/vpn-provision/sub-token
vpnd doctor --ai --bundle doctor.tar.gz
vpnd probe --profile p0
vpnd preflight --skip-certs
vpnd fleet status
vpnd host list --json
vpnd ai-docs --out ./ai-docs/
vpnd update --explain
vpnd completions bash
```

`share` requires exactly one token input: stdin or a current-owner private file.
Bearer tokens never belong in argv. Use the command's `--help` for all flags.

## `--explain`

Global flags work before or after subcommands. Every command accepts
`--explain`, which prints the underlying calls or local-artifact plan without
executing commands, contacting hosts, prompting or changing registry/cache
state. Secret-file locations are redacted. Inventory-dependent limits remain
explicitly unresolved.

## Man pages

Release packaging generates twenty pages from the same parser definition: the
root, twelve top-level commands and seven nested fleet/host commands. The
installer places all pages in `PREFIX/share/man/man1` and checks them against
the installed parser before publication.

```bash
MANPATH="$HOME/.local/share/man" man vpnd
MANPATH="$HOME/.local/share/man" man vpnd-probe-matrix
```

## Working directory

Infrastructure commands discover `Makefile`, `ansible/` and `terraform/` above
the current directory, or accept `--root` / `VPN_DEPLOY_ROOT`. Completions and
`update --explain` do not require a checkout. An installed `ai-docs` command can
use packaged documentation when the selected checkout has no `docs/` directory.
