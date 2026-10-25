# vpnd/runtime-safety Specification

## Purpose
Retain the security boundaries and lifecycle guarantees of the operator CLI
independently of its implementation language.
Complete cleanup after interruption or cancellation without retaining terminal
readers or replacing the primary failure.

## Requirements

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
failure, interruption, cancellation and dry-run completion. Cleanup failure MUST fail an otherwise
successful command, and MUST NOT replace the primary pipeline error. Explain
mode MUST describe cleanup without performing it. Cleanup MUST complete and
release owned terminal resources before the operation returns.

#### Scenario: Operation and cleanup both fail

- **WHEN** a middle pipeline step and its subsequent cleanup both fail
- **THEN** cleanup is attempted once and the original operation failure remains the primary error

#### Scenario: Cancel a review with retained terminal resources

- **WHEN** a task is cancelled during a complete or partial review read
- **THEN** it MUST remove its reader registration, preserve inherited descriptor flags and close its owned terminal descriptor
- **AND** it MUST await secrets cleanup and propagate cancellation without a gated mutation

#### Scenario: Cancel again while cleanup runs

- **WHEN** another cancellation arrives while cleanup is in progress
- **THEN** the operation MUST retain and await that cleanup rather than detach or cancel it
- **AND** cleanup failure MUST NOT replace the original failure or cancellation

#### Scenario: Cancel again while a runner worker stops

- **WHEN** another cancellation arrives before a cancelled runner worker finishes
- **THEN** the caller MUST retain and await that worker before starting pipeline cleanup
- **AND** no retained worker may write pipeline output after cleanup begins

#### Scenario: Terminate at the initial confirmation

- **WHEN** a signal terminates deploy or reconverge while its initial confirmation reads input
- **THEN** the command MUST NOT change the inherited terminal's open-file flags
- **AND** this guarantee MUST hold even when process termination skips Python finalizers

#### Scenario: Stop an active Make step

- **WHEN** a handled signal arrives while an existing Make step runs
- **THEN** the established foreground and captured process ownership rules MUST remain in force
- **AND** the review fix MUST NOT kill or detach the Make step to force progress

### Requirement: REQ-PYSAFE-TRANSFER — Existing security specifications survive

All existing vpnd/make-interface and vpnd/secrets-path requirements MUST hold
in Python, including per-key Make allowlists, one explicit volatile plaintext
path, fail-closed hardening, current-owner regular-file permission checks on the
held descriptor, symlink/FIFO refusal and resolved-path export redaction.
Python MUST delegate decryption to SOPS through the existing Make contract.

#### Scenario: Unsafe input before secret consumption

- **WHEN** a synthetic secrets/token file is replaced by a symlink or FIFO, has a foreign owner or unsafe mode, or decrypt produces no file
- **THEN** the command fails before reading the document or producing recipient artifacts
