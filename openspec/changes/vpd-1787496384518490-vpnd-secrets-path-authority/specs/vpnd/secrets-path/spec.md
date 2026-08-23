## Purpose

Keep the decrypted runtime secrets file at exactly one operator-visible location across vpnd, make, and ansible entry points, and keep its location out of every exported diagnostic.

## ADDED Requirements

### Requirement: REQ-SECRETS-PATH-AUTHORITY — Explicit secrets path into every consuming invocation

vpnd MUST pass its resolved decrypted-secrets path explicitly (SECRETS_FILE) to every make target it invokes whose recipe reads or writes that file, so vpnd, make, and ansible agree on one location on every platform including those without XDG_RUNTIME_DIR.

#### Scenario: macOS without XDG_RUNTIME_DIR

- **WHEN** vpnd triggers decrypt and then loads secrets on a system without XDG_RUNTIME_DIR
- **THEN** make writes the plaintext to vpnd's resolved path and Secrets::load succeeds without re-running decrypt on the next invocation

#### Scenario: Reconverge hands the file to ansible

- **WHEN** reconverge runs the site playbook
- **THEN** VPN_SECRETS_FILE passed to ansible-playbook equals vpnd's resolved path and the file exists

### Requirement: REQ-SECRETS-REDACTION-COVERAGE — Resolved-path redaction on every export surface

Doctor-derived exports (bundle tarball and AI prompt output/clipboard) MUST mask any line containing the resolved decrypted-secrets path before leaving the process, in addition to legacy path patterns.

#### Scenario: AI prompt with echoed path

- **WHEN** a captured step prints the resolved secrets file path and the operator runs doctor --ai
- **THEN** the printed/copied prompt contains the redaction notice instead of the path

### Requirement: REQ-SECRETS-HARDEN-GATE — Enforced hardening and race-free permission gate

Failure to set 0600 on the freshly decrypted file MUST abort the calling subcommand with a clear error, and the secrets/token permission gate MUST evaluate type, owner, and mode from the same open file handle that is subsequently read.

#### Scenario: chmod fails after decrypt

- **WHEN** set_permissions cannot apply 0600 after a successful decrypt
- **THEN** the subcommand exits nonzero explaining the plaintext file could not be hardened, instead of continuing

#### Scenario: Path swapped between check and read

- **WHEN** the secrets path is replaced by a symlink after initial stat
- **THEN** the open-handle gate rejects the swapped file instead of reading it
