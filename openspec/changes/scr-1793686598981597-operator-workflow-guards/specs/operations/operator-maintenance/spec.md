## ADDED Requirements

### Requirement: REQ-OPM-001 Continue exact scoped operations
Instructions SHALL resolve the state-owning checkout, component revisions,
active private authorities, pending journals and bounded existing grants before
resuming. Panel-only monitoring SHALL NOT require Telegram or a historical hold.

#### Scenario: Resume panel-only maintenance
- **GIVEN** a previously accepted panel-only service and an interrupted operation
- **WHEN** an operator follows continuation and acceptance instructions
- **THEN** the operator reconciles its journal before retry and keeps Telegram-only evidence outside the selected mode

### Requirement: REQ-OPM-002 Check actual release and package inputs
The local release checker SHALL verify selected archive bytes, SHA256, safe
regular members and architecture mappings without extraction. A selected APT
check SHALL compare installed, candidate and preference versions. It SHALL NOT
download or install a release.

#### Scenario: Stale archive member or downgrade pin
- **GIVEN** a valid new archive with an old selected member, or an APT downgrade candidate
- **WHEN** release preflight runs
- **THEN** it fails with a categorical result before any installation

### Requirement: REQ-OPM-003 Retain bounded encrypted diagnostics
Capture SHALL bound time, stdin and combined output, reclaim its owned process
group, preserve the command exit code, and publish only encrypted diagnostics.
Public output SHALL contain categories and counts, never captured text.

#### Scenario: Failure and capture limit
- **GIVEN** a command that emits sensitive output and fails or exceeds a limit
- **WHEN** capture finishes
- **THEN** its retained ciphertext distinguishes complete failure from incomplete capture, and no plaintext log or running owned descendant remains

### Requirement: REQ-OPM-004 Verify selected kit and downloaded recovery
Kit commands SHALL bind private catalog pointers, selected file hashes and
freshness. Sealing SHALL encrypt a complete bounded selected-file manifest.
Backup verification SHALL download the exact B2 object, check ciphertext,
decrypt in memory and compare every selected file and manifest entry. It SHALL
fail on changed authority, unsafe archives or wrong identities. Results SHALL
state the selected local scope and SHALL NOT claim fresh server health or
independent bucket-policy acceptance.

#### Scenario: Downloaded encrypted recovery
- **GIVEN** unchanged catalog-bound files and their encrypted B2 backup
- **WHEN** verification downloads and decrypts that backup
- **THEN** every member and hash matches, while a changed file, extra member or wrong decryption identity fails

### Requirement: REQ-OPM-005 Fail fast on missing pinned tools
Task validation SHALL check required installed tool availability before loading
portfolio history and SHALL retain all existing downstream validation.

#### Scenario: Missing task executable
- **GIVEN** a missing pinned mdtask executable
- **WHEN** normal task validation starts
- **THEN** it gives the existing install instruction before reading task history
