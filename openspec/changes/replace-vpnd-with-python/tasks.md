# VPD-1791615284178957: Replace vpnd with Python while preserving commands and security

## Objective

Deliver one complete Python 3.12 CLI and trusted installed distribution with
the baseline command/state/security/test contract preserved, then retire
authored Rust and compiler tooling. Implementation and PR preparation are authorized. Steps are marked only after
observed checks; the portfolio advances at most to review.

## Ownership

- Implementation starts in a dedicated worktree after explicit authorization.
- Core contributor owns parser/context/runner/state/secrets, operational commands,
  `scripts/vpnd-cli.py` and their test files. Artifact contributor owns
  share/doctor/docs/update/completions/probe-matrix/pages and their test files.
  The primary integration owner owns packaging, conftest/test-transfer gate,
  dependencies, CI/release/installer and shared consumers. Contributors preserve
  each other's edits; only the primary runs the heavy baseline/final build gates.
- Artifact modules own recipient/QR, diagnostics, docs, cache and matrix output.
- A single integration owner serializes root Makefile, mise, dependency locks,
  hooks, CI selection/aggregation, release/install/version/SBOM, shared Python
  consumer tests and instruction/runbook updates listed in design.md.
- taskctl owns checkbox IDs/lifecycle and board generation; metadata edits are
  serialized. Parallel contributors, if later assigned, must preserve others'
  changes and record disjoint module ownership before editing.
- Real inventory, credentials, secrets, Terraform state and ignored local
  operator files are outside the migration's write/inspection scope.

## Execution

- [x] VPD-1791615721526525 Deliver the Python package launcher and complete parser, preserve all command flags, and establish baseline-to-pytest transfer checks with parser tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615722328162 Implement descriptor-safe secrets, atomic private files, validated Make runner, process groups and state formats with adversarial and lifecycle tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615723154686 Port deploy reconverge preflight probe fleet and host with exact targeting, side-effect-free explain and failure-cleanup subprocess tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615723996375 Port share recipient HTML deep links and both QR SVGs with escaped rendering, private-mode and write-failure tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615724808852 Port doctor ai-docs update completions and parser-derived man pages with resilient diagnostics, redaction, cache and packaged-doc tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615725580652 Port schema-3 probe-matrix scheduling classification journals and signals with full snapshot, concurrency, timeout and descendant-reaping tests #feature !high @item:VPD-1791615284178957
- [x] VPD-1791615726382311 Deliver verified Python wheel source distribution and atomic installer, version authority, SBOM and reproducibility with four-platform artifact tests #feature !high @item:VPD-1791615284178957
- [ ] VPD-1791615727227192 Switch CI dependency selection hooks release and mutation lanes to Python, transfer properties seeds snapshots and consumer tests, and enforce exhaustive test parity #feature !high @item:VPD-1791615284178957
- [ ] VPD-1791615728004540 Remove active Rust source and tooling after parity passes, update operator guidance, and pass full Rust-free gates independent security review and exact-SHA hosted checks #feature !high @item:VPD-1791615284178957

## Verification

Run steps in list order. Step 1 also implements the parity gate; each later
slice adds its transferred cases to that gate and runs its complete affected
tests. Steps 7-8 may prepare distribution integration while Rust reference
tests remain test-only. Step 9 requires complete parity first.

| Slice | Completion evidence |
|---|---|
| Package/parser | All matrix cases through launcher and installed entry point; invalid flags fail before invocation; baseline 206 functions plus any added upstream tests are inventoried |
| Safety/state | Real local symlink/FIFO/owner/mode and atomic-write tests; capture/foreground process-tree tests; Make allowlists; existing TOML fixtures and redaction properties |
| Operations | Local instrumented Make subprocess transcripts prove exact order, limit and cleanup; all commands execute positive cases; explain writes nothing |
| Share | Complete inherited rendering/QR/bundle tests, adversarial escaping, failure writes and umask tests; rendered HTML/QR inspection and decoded-payload checks |
| Diagnostics/docs | Local failing diagnostics and clipboard capture, packaged docs/archive members, generated shell/man parity, loopback HTTP/cache timeout tests |
| Matrix | Complete inherited cases/schema snapshot; real concurrent processes, SIGINT/SIGTERM, timeout cleanup, JSONL durability and analysis boundary tests |
| Distribution | `make vpnd-package-check` on Linux/macOS x86_64/arm64; offline hash-locked install, resource/version/SBOM/reproducibility and corrupt/failed-upgrade tests |
| CI/test transfer | `make vpnd-test vpnd-lint vpnd-parity-check vpnd-mutants vpnd-dependency-check`; every assertion maps to collected/passed tests, no waived cases |
| Retirement | Rust absent from required PATH and active build paths; `build-gate -- make check`, package/parity gates, independent security review and terminal exact-SHA required hosted checks |

The above Python targets are future implementation deliverables. Planning
validation runs only taskctl/OpenSpec and applicable documentation checks;
it does not mark any slice complete. Baseline Cargo compilation, any heavy
local build/test and the full implementation gate use build-gate with the
repository's global worker ceilings. New production dependencies require their
recorded approval/security/license review before introduction.

`verification.md` maps each normative requirement to stable step IDs. Local,
remote_ci and artifact are required implementation categories. Dry-run,
staging, live and client are not applicable to this source/package replacement;
it leaves the underlying deployment controller, rendered runtime inputs and
VPN protocols unchanged. Real deployments need separate scoped authorization.
