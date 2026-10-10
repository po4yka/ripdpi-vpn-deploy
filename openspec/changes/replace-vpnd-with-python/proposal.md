# Change: Replace vpnd with Python and retire Rust

Task ID: `VPD-1791615284178957`

## Why

Rust is confined to the optional operator CLI. Make and Python already own the
deployment controller, and Terraform/Ansible/SOPS retain their separate layers.
The CLI nevertheless requires a second language toolchain, a Cargo lockfile,
compiler gates and four platform release builds. Consolidating operator code
in Python reduces that maintenance burden while retaining the usable CLI.

The baseline is commit `5365cbd4b33dff5b3d0be0e1f8c5cb2c9d17ac50`.
This proposal is planning only: no command implementation, infrastructure,
secret, release publication or deployment change is authorized by its creation.

## What Changes

- Deliver the same `vpnd` executable interface through Python 3.12, preserving
  all twelve commands, nested actions, flags, defaults, state formats, output
  schemas and generated recipient/diagnostic/documentation artifacts.
- Preserve security and cancellation behavior with descriptor-level file
  checks, private atomic writes, redaction, validated Make inputs, exact host
  limits and owned subprocess cleanup.
- Carry every existing test assertion into the Python suite, including
  properties, snapshots, platform cases and Python tests consuming Rust assets.
- Replace Rust build/test/release lanes with Python packaging and verification;
  preserve artifact integrity, dependency policy, SBOM and reproducibility.
- **BREAKING:** new installations require Python 3.12 and the locked Python
  runtime dependencies. Native executable downloads and Cargo development
  commands are replaced by a Python wheel/source release and installer.
  Existing CLI invocations and persisted formats remain the product contract;
  this is one replacement implementation, with no legacy Rust fallback.
- Make the documented side-effect-free explain contract authoritative for
  local registry actions as well. Preserve safe semantics rather than any
  implementation discrepancy that currently violates a security guarantee.

## Capabilities

### New Capabilities

- `vpnd/command-contract`: complete Python command surface and orchestration parity.
- `vpnd/runtime-safety`: subprocess ownership, targeting, cleanup and explain guarantees.
- `vpnd/probe-matrix`: schema-3 probe orchestration, signals and durable observations.
- `vpnd/python-delivery`: Python installation, releases, exhaustive test transfer and Rust retirement.

### Modified Capabilities

- `vpnd/operator-output`: parser-derived man pages without requiring clap.
- `vpnd/share-bundle`: private atomic artifacts that preserve unrelated temporary files.

Existing `vpnd/make-interface` and `vpnd/secrets-path` requirements remain
normative without amendment and are mapped into this change's verification.

## Impact

- Operator CLI/package/launcher, tests, template and bundled documentation.
- Make, pre-commit, pinned tooling, CI selection and result aggregation, release
  installer/workflows, release-please version source, SBOM and mutation checks.
- Static share output consumed by subscription-host retains its existing
  interface. Terraform roots, Ansible runtime configuration, provider resources,
  secret schema, device credentials and RIPDPI bundle contracts are preserved.
- Live fleet/client acceptance is outside this source/package migration;
  local subprocess tests and installed-artifact tests exercise the positive CLI
  capability without invoking provider credentials, SSH or real inventory.
