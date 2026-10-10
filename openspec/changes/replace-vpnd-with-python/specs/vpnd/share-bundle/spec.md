## Purpose

Preserve private atomic recipient outputs and clarify temporary-file ownership
so the Python migration does not delete another writer's artifacts.

## MODIFIED Requirements

### Requirement: REQ-SHARE-BUNDLE-PERMS — Crash-safe 0600 bundle writes

Every regular bundle file, including QR SVGs, MUST be created through a unique
mode-0600 temporary file, synced and atomically renamed. The bundle directory
MUST be mode 0700. A failed write MUST remove only the temporary file owned by
that invocation. Unrelated stale or concurrent temporary files MUST remain
intact and MUST NOT prevent a subsequent successful write.

#### Scenario: Re-run after interrupted share

- **WHEN** an earlier invocation left a temporary file behind
- **THEN** a new invocation uses its own unique temporary name, succeeds with private output modes and preserves the unrelated leftover

#### Scenario: Write failure mid-bundle

- **WHEN** a bundle write fails during generation
- **THEN** the command exits nonzero and removes its own incomplete temporary file without deleting another writer's files
