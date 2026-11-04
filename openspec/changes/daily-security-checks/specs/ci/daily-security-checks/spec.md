## Purpose

Find new dependency and image advisories without requiring source changes,
and notify the owner when the actionable result changes.

## ADDED Requirements

### Requirement: REQ-DAILY-SCANS — Scan unchanged inputs each day

The workflow MUST support a daily schedule and manual dispatch. It MUST scan
Python, npm and Go manifests, including npm development dependencies, and every
image from the existing image inventory. It MUST use pinned actions, current
advisory data and the existing image severity policy without rebuilding images,
accessing fleet credentials or changing infrastructure.

#### Scenario: New advisory without a source change

- **WHEN** a daily run starts against unchanged locks and image digests
- **THEN** current advisory data is checked and scan reports are retained even when findings fail a check

### Requirement: REQ-DAILY-NOTIFY — Notify on changed findings and failures

The workflow MUST create an owner-assigned issue for findings or failed/incomplete
scans. It MUST comment on changed results and remain quiet otherwise. Only a
complete clean run MAY close the issue. Issue writes MUST require the current
default-branch SHA; recovery MUST require current-attempt reports. Only the
notification job MAY write issues. Issue content MUST omit raw reports and secrets.

#### Scenario: Failure, repeated failure and recovery

- **WHEN** a report is missing, findings change, or all checks recover
- **THEN** the issue records the changed state with a run link; repeated identical findings do not create comments

#### Scenario: A clean report is incomplete

- **WHEN** one scan is clean but an expected image report is absent
- **THEN** the run cannot close the issue or report a clean result

#### Scenario: Manual feature-branch scan

- **WHEN** a maintainer manually scans a feature branch
- **THEN** scan reports remain available without changing the default-branch notification issue

#### Scenario: Retry an old or partial run

- **WHEN** a historical revision is rerun, or only some jobs produce current-attempt reports
- **THEN** old results cannot close the current issue; a complete retry uses new artifacts without name collisions
