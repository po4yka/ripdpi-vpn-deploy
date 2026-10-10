# vpnd/probe-matrix Specification

## Purpose
Preserve long-running probe-matrix observations, classification and durable
results when the orchestration loop is implemented in Python.
## Requirements
### Requirement: REQ-PYMATRIX-SCHEMA — Schema-3 observations and classification

Python probe-matrix MUST preserve baseline configuration validation, protocol,
target/topology/control semantics, verdicts, error kinds, stable cell ordering,
analysis rules, schema_version 3 and machine-readable summary fields. It MUST
call existing Make control/cell targets and preserve their Python driver
interface instead of implementing another protocol engine.

#### Scenario: Mixed probe outcomes

- **WHEN** a local matrix returns successes, malformed output, timeouts and control failures
- **THEN** the report classifies each outcome and produces the same schema and observations as the baseline regression cases

### Requirement: REQ-PYMATRIX-SCHEDULE — Concurrent bounded timed execution

The loop MUST preserve monotonic scheduling, duration parsing, positive
interval/timeouts, configured per-cell concurrency, sweep/overrun metrics and
duration bounds. Completion order MUST NOT reorder report cells. Blocking disk
work MUST NOT prevent cancellation from being handled.

#### Scenario: Slow concurrent cells

- **WHEN** cells finish out of order and one exceeds its configured deadline
- **THEN** siblings execute concurrently, the slow cell is timed out with its process tree cleaned, and report order remains deterministic

### Requirement: REQ-PYMATRIX-DURABILITY — Interrupts preserve reports and journals

Reports and JSONL journals MUST retain private permissions and checkpoint
semantics at startup, sweeps and completion. SIGINT/SIGTERM MUST stop new work,
clean owned jobs, flush partial observations and return 130/143 respectively.
Interrupted reports MUST distinguish interruption from successful completion.

#### Scenario: Termination during a sweep

- **WHEN** a real local probe-matrix process receives SIGTERM with cells in flight
- **THEN** its complete partial JSON and readable JSONL checkpoint survive, completed is false, interrupted is true, no owned descendant remains and exit status is 143
