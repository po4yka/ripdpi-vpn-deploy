# ansible/source-build-process-lifecycle Specification

## Purpose
Keep source-build process ownership until foreground execution and cleanup finish, so output publication never depends on a stale process-group observation.

## Requirements

### Requirement: REQ-BUILD-SESSION-OWNERSHIP — Retain process ownership

The source-build helper MUST retain exact authority over its private foreground process group until execution and cleanup finish.

#### Scenario: Successful command reaches publication

- **WHEN** the foreground command exits successfully without surviving descendants
- **THEN** the helper confirms cleanup and permits the existing output and receipt transaction
- **AND** transient process-exit state does not cause a false build failure

#### Scenario: Leader exits before a live descendant

- **WHEN** the command leader exits with a descendant still in its private foreground group
- **THEN** the helper stops that group and refuses output publication
- **AND** it does not signal a recycled or foreign process group

### Requirement: REQ-BUILD-CLEANUP-FAILURE — Keep bounded failure semantics

The helper MUST reclaim its owned foreground processes before releasing the project lock after cancellation, timeout or command failure. Unconfirmed cleanup MUST fail without publication.

#### Scenario: Cancellation or timeout

- **WHEN** cancellation or the command deadline stops a build
- **THEN** the helper terminates and reaps its owned foreground session within a bounded cleanup period
- **AND** no descendant can later publish output

#### Scenario: Cleanup cannot be confirmed

- **WHEN** a signal or process-control failure prevents confirmed cleanup
- **THEN** the helper reports categorical cleanup failure and retains the primary failure as its cause
- **AND** it does not report success or publish a new receipt

#### Scenario: Existing transaction recovery

- **WHEN** a build reaches an existing journal, receipt or rollback boundary
- **THEN** process control preserves the existing transaction decision and exact inode checks
- **AND** no descriptor, public CLI or receipt format changes

### Requirement: REQ-LOCAL-ASYNC-TESTS — Observe completed asynchronous actions

Portable process tests MUST synchronize on completed fixture publication and process exit. They MUST preserve safety assertions and execute the complete applicable behavior.

#### Scenario: Process is still exiting

- **WHEN** a monitor child has a transient exiting state
- **THEN** the test waits within a bounded deadline for absence or a reaped terminal state
- **AND** persistent live or exiting state still fails

#### Scenario: Full source gate

- **WHEN** the process fixes and test synchronization changes are complete
- **THEN** the full local `make check` and required hosted checks pass without skipped applicable cases or weaker assertions
