## Purpose

Retain the security boundaries and lifecycle guarantees of the operator CLI
independently of its implementation language.

## ADDED Requirements

### Requirement: REQ-PYSAFE-EXPLAIN — Side-effect-free explain for every command

Explain mode MUST describe intended operations without spawning operational
commands, fetching HTTP, prompting, decrypting, modifying registry/cache state
or producing output artifacts. Inventory-dependent limits MUST remain visibly
unresolved rather than widened. Completions and update --explain MUST work
outside a checkout as they do at baseline.

#### Scenario: Explain a local mutation

- **WHEN** host add or host remove runs with --explain against a synthetic registry
- **THEN** its intended operation is displayed and registry contents remain byte-identical
- **AND** filesystem/network/process sentinels confirm no mutation or external operation

### Requirement: REQ-PYSAFE-PROCESSES — Explicit process ownership and redaction

Subprocess invocation MUST remain argv-shaped without an interpreter string.
The runner MUST preserve foreground interaction and opt-in owned capture
groups, concurrent stream draining, errors and return codes. Cancellation and
timeouts MUST terminate and reap owned children/descendants without signaling
the caller's foreground group. Displayed invocations and diagnostic exports
MUST redact sensitive values and resolved secrets paths.

#### Scenario: Cancel a captured descendant tree

- **WHEN** an owned local subprocess tree is cancelled while producing both output streams
- **THEN** all owned descendants are terminated and reaped, the caller remains alive, and partial diagnostics contain no sensitive input

### Requirement: REQ-PYSAFE-CLEANUP — Pipeline cleanup preserves primary failures

Once deploy/reconverge starts its pipeline, secrets cleanup MUST run on success,
failure and dry-run completion. Cleanup failure MUST fail an otherwise
successful command, and MUST NOT replace the primary pipeline error. Explain
mode MUST describe cleanup without performing it.

#### Scenario: Operation and cleanup both fail

- **WHEN** a middle pipeline step and its subsequent cleanup both fail
- **THEN** cleanup is attempted once and the original operation failure remains the primary error

### Requirement: REQ-PYSAFE-TRANSFER — Existing security specifications survive

All existing vpnd/make-interface and vpnd/secrets-path requirements MUST hold
in Python, including per-key Make allowlists, one explicit volatile plaintext
path, fail-closed hardening, current-owner regular-file permission checks on the
held descriptor, symlink/FIFO refusal and resolved-path export redaction.
Python MUST delegate decryption to SOPS through the existing Make contract.

#### Scenario: Unsafe input before secret consumption

- **WHEN** a synthetic secrets/token file is replaced by a symlink or FIFO, has a foreign owner or unsafe mode, or decrypt produces no file
- **THEN** the command fails before reading the document or producing recipient artifacts
