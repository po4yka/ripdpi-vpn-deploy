## Purpose

Bind first-node bootstrap to its actual build marker and routed workspace so
named permanent nodes retain the same exact-target and disposable safety gates.

## ADDED Requirements

### Requirement: REQ-SEC-1791223987683372-006 — Build marker and workspace binding

Every bootstrap producer SHALL supply the canonical build environment separately
from the routed workspace. Inventory and the root-owned cloud-init build marker
SHALL agree with that field before guest writes. Disposable workspace identity
SHALL always require its manifest even when its build label resembles production.
Named permanent workspace support SHALL not relabel state or fabricate contexts.

#### Scenario: Existing permanent workspace

- **GIVEN** a named workspace, canonical production build metadata and the matching guest marker
- **WHEN** exact-node bootstrap validates its request
- **THEN** classification succeeds with original workspace identity and strict host pins preserved.

#### Scenario: Missing build binding

- **WHEN** a request or producer omits the required build field or its guest marker differs
- **THEN** the request refuses before host writes; no deprecated input path is retained.
