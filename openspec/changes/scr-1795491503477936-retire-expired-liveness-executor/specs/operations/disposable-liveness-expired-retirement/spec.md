## Purpose

Give every prepared disposable liveness executor a supported removal path, including one that no promotion intent names or whose run has no client left to retire, without weakening the protection of assigned executors.

## ADDED Requirements

### Requirement: REQ-EXPIRED-EXECUTOR-RETIRE — Retire an expired never-assigned executor

The implementation MUST provide `make retire-expired-disposable-liveness EXECUTOR_MANIFEST=… EXECUTOR_RECEIPT=…`, which stops and deletes the exact Colima profile of an expired prepared executor after it verifies the root marker, the profile configuration and the Docker context, and then writes a private receipt with the status `retired-expired` and no client field.

#### Scenario: Expired prepared executor

- **WHEN** the manifest's `expires_at` has passed and the profile journal holds no assignment
- **THEN** the profile is stopped and deleted, the default Docker context is unchanged, and the receipt is written with mode 0600

#### Scenario: Repeat

- **WHEN** the command runs again with the same manifest and receipt
- **THEN** it makes no Colima change and reports `changed: false`

### Requirement: REQ-EXPIRED-EXECUTOR-GUARDS — Refuse before expiry and for assigned executors

The implementation MUST refuse, before any Colima stop or delete, a manifest whose `expires_at` has not passed (`executor-not-expired`) and an executor whose profile journal records an assignment (`executor-claimed`).

#### Scenario: Not yet expired

- **WHEN** the command runs before the manifest's `expires_at`
- **THEN** it fails with `executor-not-expired`, the profile still exists and no receipt is written

#### Scenario: Assigned executor

- **WHEN** the executor was bound to a sentinel, even if the manifest has since expired
- **THEN** it fails with `executor-claimed`, the profile still exists and no receipt is written

### Requirement: REQ-EXPIRED-EXECUTOR-MAKE — Exact Make boundary

The implementation MUST accept only `EXECUTOR_MANIFEST` and `EXECUTOR_RECEIPT` as command-line fields of `retire-expired-disposable-liveness`, refuse non-literal values and other goals in the same invocation, and run the script under the machine build gate.

#### Scenario: Unowned field

- **WHEN** the operator adds another command-line field
- **THEN** Make refuses before it expands the value or starts a child process
