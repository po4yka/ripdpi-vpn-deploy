## Purpose

Keep probe-matrix runs bounded, durable, and conservative: subprocesses die with their cell, no hang stalls the run, interruptions never masquerade as completed measurements, and impairment windows reflect filtering rather than local failures.

## ADDED Requirements

### Requirement: REQ-MATRIX-CELL-TIMEOUT-KILL — Timeout terminates the cell process tree

When a cell exceeds its timeout the spawned subprocess MUST be terminated rather than orphaned, and the cell recorded as Unknown with reason timeout.

#### Scenario: Hung target probe

- **WHEN** a cell's make invocation blocks past control.timeout_seconds
- **THEN** no process from that cell remains running when the next tick starts

#### Scenario: CLI interrupted during a captured invocation

- **WHEN** SIGINT or SIGTERM reaches the CLI directly or its foreground process group while ProbeMatrix or Doctor runs an explicitly group-owned capture
- **THEN** scoped dispatch cancellation drops the captured work and all nested cell jobs, terminates their owned process groups, and exits with 130 or 143
- **AND** this cancellation alone does not claim that a partial report was persisted

#### Scenario: Interactive commands keep foreground signal behavior

- **WHEN** Share waits for token stdin or Reconverge waits for confirmation after an inventory capture
- **THEN** their dispatch does not install ProbeMatrix/Doctor signal listeners or isolate captured process groups
- **AND** SIGINT/SIGTERM can still terminate them without waiting for further operator input

### Requirement: REQ-MATRIX-CONTROL-TIMEOUT — Bounded control probe

The per-tick control invocation MUST be bounded by the same timeout budget as cells; expiry records an Unknown control verdict and continues the run.

#### Scenario: Control target unreachable

- **WHEN** the control make invocation hangs past its timeout
- **THEN** the tick proceeds with an Unknown control verdict instead of stalling indefinitely

#### Scenario: Next poll cannot fit the monotonic clock

- **WHEN** a positive CLI/configuration poll interval makes the next scheduled tick unrepresentable
- **THEN** the bounded session ends with its already observed control/cell results instead of panicking or recording a synthetic Unknown

### Requirement: REQ-MATRIX-DURABILITY — Interruptible runs preserve evidence

The matrix MUST checkpoint accumulated results at least once per tick, MUST flush a partial report on SIGINT/SIGTERM marked as interrupted with a nonzero exit code, and MUST reject a zero total duration at config validation.

#### Scenario: Ctrl-C mid-run

- **WHEN** the operator interrupts a multi-hour run after several ticks
- **THEN** the output path contains all ticks observed so far, marked interrupted, and the exit code is nonzero

#### Scenario: Zero duration requested

- **WHEN** --duration 0 is passed
- **THEN** configuration validation fails before any probe runs

#### Scenario: Unrepresentable duration requested

- **WHEN** duration multiplication or the monotonic deadline would overflow
- **THEN** validation fails before any probe runs instead of saturating or panicking

### Requirement: REQ-MATRIX-EVIDENCE-SEMANTICS — Windows reflect filtering only

Impairment windows MUST open only on Blocked or Throttled protocol verdicts; local orchestration failures (Unknown/Error) MUST NOT open or extend windows and remain visible through Indeterminate observations.

#### Scenario: Transient make failure

- **WHEN** one tick's cell fails locally while every real probe verdict is Ok
- **THEN** no impairment window is reported for that pair

#### Scenario: Indeterminate evidence between impairment and success

- **WHEN** Blocked/Throttled is followed by Unknown/Error and then Ok
- **THEN** the earlier window has null recovery, meaning recovery was unobserved rather than impairment continuing through the gap
- **AND** the unchanged schema-2 summary retains at most one record for that protocol/target pair without asserting a continuous outage duration
