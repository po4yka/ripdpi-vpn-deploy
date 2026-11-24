# terraform/remote-state-readers Specification

## Purpose
Define how operator scripts read OpenTofu state after state moved to the encrypted remote backend, and how the disposable CI deploy keeps its state.

## Requirements

### Requirement: REQ-STATE-READ-PULL — Scripts read state only through an in-memory state pull

A script that needs OpenTofu state MUST read it with `scripts/terraform-env.sh state pull` for an explicit provider and environment (directly through `scripts/tofu_state.py`, or through the trusted OpenTofu binary and workspace data directory of a frozen snapshot), keep the bytes in memory and bound their size and the read time. It MUST NOT read, copy, bind or accept a path to a local state file, and MUST NOT write the pulled state to disk or to a log.

#### Scenario: Migrated workspace

- **WHEN** a promotion, recovery, cleanup or retirement script runs for a workspace whose state is in the encrypted backend
- **THEN** it evaluates the decrypted state that `state pull` returns and no local state path is opened

#### Scenario: Old interface

- **WHEN** an operator passes `--state`, `STAGING_CLEANUP_STATE`, `provider_state_path` or a manifest that still binds a state path
- **THEN** the script refuses before any provider call

### Requirement: REQ-STATE-READ-FAILCLOSED — An unreadable state is never empty

An existing workspace without state MAY read as no state. A missing workspace, a backend, credential or decryption failure, an oversized state and a timeout MUST refuse, and MUST NOT be treated as an empty or destroyed state.

#### Scenario: Missing passphrase

- **WHEN** `TF_VAR_state_passphrase` is absent and a cleanup guard reads its bound state
- **THEN** the guard refuses and issues no destroy

#### Scenario: Empty workspace

- **WHEN** the recovery runtime reads a workspace that `init` created but no apply wrote
- **THEN** it reports no existing server and continues with the create path

### Requirement: REQ-STATE-READ-BINDING — Digest bindings use the pulled bytes

A manifest, target or request that binds state MUST bind the SHA-256 of the pulled bytes and the provider and environment that select them. Every later read MUST pull again and refuse on a digest change.

#### Scenario: State changed after binding

- **WHEN** another writer changes the workspace after a cleanup manifest was created
- **THEN** the next guard step pulls a different digest and refuses

### Requirement: REQ-STATE-READ-CI — The disposable CI deploy keeps its state out of the bucket

The label-gated disposable CI deploy MUST use a gitignored local backend override with a per-run passphrase and backend settings in its private work directory, so that it needs no bucket identity and its state stays encrypted on the runner. Its age recovery bundle MUST carry the encrypted state and the run passphrase.

#### Scenario: CI run

- **WHEN** the disposable deploy initializes its `ci-staging-*` workspace
- **THEN** `init` succeeds with the generated `TF_BACKEND_ROOT` and passphrase and writes no object to the operator bucket
