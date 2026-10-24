## Purpose

Complete CLI pipeline cleanup after interruption or cancellation without
retaining terminal readers or replacing the primary failure.

## MODIFIED Requirements

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
- **THEN** it MUST remove its reader registration, restore descriptor flags and close only owned descriptors
- **AND** it MUST await secrets cleanup and propagate cancellation without a gated mutation

#### Scenario: Cancel again while cleanup runs

- **WHEN** another cancellation arrives while cleanup is in progress
- **THEN** the operation MUST retain and await that cleanup rather than detach or cancel it
- **AND** cleanup failure MUST NOT replace the original failure or cancellation

#### Scenario: Stop an active Make step

- **WHEN** a handled signal arrives while an existing Make step runs
- **THEN** the established foreground and captured process ownership rules MUST remain in force
- **AND** the review fix MUST NOT kill or detach the Make step to force progress
