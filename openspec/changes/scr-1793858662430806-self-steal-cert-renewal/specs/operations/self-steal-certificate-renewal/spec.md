## Purpose

The P0 self-steal certificate is reissued before it expires, without credentials on the node and without an unreviewed deploy.

## ADDED Requirements

### Requirement: REQ-OPS-SSR-DUE-ONLY — Reissue only when due and only once

The renewal MUST NOT contact the CA while more than 30 days remain on the current certificate, and MUST NOT issue again while a renewed document for the same source exists.

#### Scenario: Time left

- **WHEN** the current certificate has more than 30 days left
- **THEN** the run reports `not-due` and calls no ACME client

#### Scenario: Renewal awaiting deploy

- **WHEN** a renewed document for the source already exists
- **THEN** the run reports `awaiting-deploy` and issues nothing

### Requirement: REQ-OPS-SSR-NEW-DOCUMENT — Write a validated pair into a new encrypted document

The renewal MUST write the reissued pair only into a new SOPS document, MUST leave the source unchanged, MUST remove the issued plaintext key from disk, and MUST refuse a pair whose name, key or lifetime does not match.

#### Scenario: Due certificate

- **WHEN** the certificate is due and the CA issues a matching pair
- **THEN** a new encrypted document carries the pair, the source is unchanged, and no issued key remains on disk

#### Scenario: Wrong name

- **WHEN** the issued certificate names another host
- **THEN** the run refuses with `issued-name-mismatch` and writes no document
