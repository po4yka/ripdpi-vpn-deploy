## Purpose

Deliver and verify the complete Python CLI while removing authored Rust and
retaining trusted installation, test coverage and release integrity.

## ADDED Requirements

### Requirement: REQ-PYDELIVERY-INSTALL — Supported Python installation

The project MUST supply a repository launcher, installable Python wheel and
source distribution with one version authority, required templates/docs and
hash-locked runtime dependencies. Installation MUST validate Python 3.12,
retain the supported Linux/macOS x86_64/arm64 surfaces and PREFIX/root guards,
and perform checksum/provenance checks before replacing an installation.
Failed upgrades MUST retain the last usable installed command.

#### Scenario: Install and upgrade without Rust

- **WHEN** a verified Python release is installed into a disposable prefix with Cargo/rustc unavailable
- **THEN** vpnd runs with packaged templates/docs and the correct version
- **AND** a corrupt artifact or interrupted replacement preserves the previous installation

### Requirement: REQ-PYDELIVERY-TESTS — Exhaustive assertion and property transfer

Every baseline Rust test function, inline module test, property, regression
seed, snapshot and Rust-dependent Python contract assertion MUST map to an
executed Python equivalent before Rust removal. A checked transfer manifest
MUST reject unmapped/new baseline cases, absent target node IDs, skips and
weakened assertions. Generated properties and mutation checks MUST continue;
compiler checks MUST be replaced by relevant Python validation, not claimed
as runtime parity. All four platform test partitions MUST run their relevant
positive and failure cases.

#### Scenario: A test is lost during migration

- **WHEN** a baseline case lacks a destination or its destination is skipped
- **THEN** the transfer gate fails and Rust retirement remains blocked

### Requirement: REQ-PYDELIVERY-INTEGRITY — Release and dependency integrity

Python releases MUST retain validated tags/version agreement, SHA256SUMS,
build provenance, dependency SBOM, pinned/hashes-verified inputs and
reproducibility checks. Required CI MUST test the produced installed artifact,
packaged assets and offline dependency closure. Dependency-policy and mutation
failures MUST remain failures rather than empty successful lanes.

#### Scenario: Version or dependency artifact mismatch

- **WHEN** the wheel version, release tag, source version, SBOM or locked dependency set disagree
- **THEN** release verification fails before publication or installation

### Requirement: REQ-PYDELIVERY-RETIRE — Complete active Rust retirement

After Python behavior and test parity pass, active Rust source, Cargo
manifests/locks/configuration, toolchain pins, compiler hooks, CI consumers,
release build lanes and Rust-specific scripts MUST be removed or replaced.
Normal Make check and Python release operations MUST succeed without Cargo or
rustc. Historical task/spec/release records and operator-owned local files MUST
remain intact. No permanent dual implementation or Rust fallback is permitted.

#### Scenario: Credential-free post-retirement gate

- **WHEN** a fresh checkout runs its complete source/package gate with Rust tools absent
- **THEN** all required Python and existing infrastructure checks execute and no active invocation attempts to use Rust

### Requirement: REQ-PYDELIVERY-ROLLBACK — Whole-release recovery

Recovery MUST select a complete previously verified release or revert the
migration changeset, without introducing mixed Python/Rust runtime paths,
rewriting operator state or publishing rewritten history. The install contract
break MUST be documented before release.

#### Scenario: Python release rejected during acceptance

- **WHEN** installed-artifact verification fails before promotion
- **THEN** the previous verified installation remains usable and no configuration/state migration must be undone
