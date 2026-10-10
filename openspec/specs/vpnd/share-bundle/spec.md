# vpnd/share-bundle Specification

## Purpose
Define correctness and permission requirements for vpnd-generated recipient bundles so a shared bundle is always usable and never exposes the bearer token through file modes or crash residue.

Preserve private atomic recipient outputs and clarify temporary-file ownership
so the Python migration does not delete another writer's artifacts.

## Requirements
### Requirement: REQ-SHARE-TOKEN-VALIDITY — Non-empty base64url token gate

The share command MUST reject a subscription token that is empty or contains characters outside [A-Za-z0-9_-] before constructing any URL, regardless of whether the token arrived via stdin or a token file.

#### Scenario: Empty stdin token

- **WHEN** the operator pipes zero bytes or whitespace only through --token-stdin
- **THEN** the command exits nonzero naming the token source and writes no bundle files

### Requirement: REQ-SHARE-HOST-RESOLUTION — Configured host required

If neither subscription.server_name nor nginx_xhttp.server_name resolves to a host, the share command MUST fail with an error identifying the missing secrets key and MUST NOT produce a bundle containing placeholder hosts.

#### Scenario: Cohort without server_name

- **WHEN** the decrypted secrets contain the client but no subscription or transport server_name
- **THEN** the command exits nonzero naming the missing key and creates no bundle directory

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
