## Purpose

Define correctness and permission requirements for vpnd-generated recipient bundles so a shared bundle is always usable and never exposes the bearer token through file modes or crash residue.

## ADDED Requirements

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

Every regular file in the bundle including QR SVGs MUST be created mode 0600 through a temp-and-rename write whose temp carries 0600 from creation, MUST tolerate and replace a leftover temp from a previous crashed run, and MUST remove its temp when the write fails.

#### Scenario: Re-run after interrupted share

- **WHEN** a previous share crashed between temp creation and rename leaving name.tmp behind
- **THEN** the next share run succeeds, replaces the stale temp, and all bundle files are mode 0600

#### Scenario: Write failure mid-bundle

- **WHEN** the disk fills during a bundle write
- **THEN** the command exits nonzero and no partial temp files remain in the bundle directory
