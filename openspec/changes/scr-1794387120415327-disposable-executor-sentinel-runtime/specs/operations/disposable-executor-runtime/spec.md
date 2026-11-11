## ADDED Requirements

### Requirement: REQ-DER-RUNTIME — The disposable executor can carry every runtime its sentinel verifies

The repository MUST provide `make provision-disposable-liveness-runtime` that, for one live executor manifest, installs sing-box and Xray at the pinned versions, builds the AWG toolchain offline with `install-real-vps-awg-client-tools.py`, and prints an `expected_runtime` with `sing_box`, `xray`, `awg` and `awg_toolchain` observed inside that executor.

#### Scenario: Four-profile staging sentinel

- **WHEN** the operator runs the target against a running executor from `make prepare-disposable-liveness`
- **THEN** it exits zero and prints the executor's observed runtime, including the 64-hex toolchain source-input digest.

#### Scenario: Expired or foreign executor

- **WHEN** the manifest does not match a live owned profile
- **THEN** the target refuses before any VM command.

### Requirement: REQ-DER-PINS — Inputs are pinned and verified before they reach the executor

Engine archives MUST match a pinned SHA-256 for the executor architecture before extraction, and the amd64 pins MUST equal the CI pins of the same releases. AWG sources MUST be bundles of the `real-vps-awg-nat` commit pins, and the vendor archive MUST contain only `vendor/`.

#### Scenario: Pin drift

- **WHEN** a CI engine pin or the local parser version pin changes without the provisioner pin
- **THEN** the provisioner test fails.

### Requirement: REQ-DER-PREPARE — Executor preparation does not depend on the caller's umask

`make prepare-disposable-liveness` MUST create the Colima profile configuration owner-only.

#### Scenario: Default operator umask

- **WHEN** the operator runs preparation with umask 022 and Colima writes its config with the inherited umask
- **THEN** preparation succeeds and the manifest is published.
