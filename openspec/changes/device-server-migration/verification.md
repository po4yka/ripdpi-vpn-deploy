---
task_id: OPS-1792673523985723
change: device-server-migration
commit_sha: null
local: required
local_evidence: Narrow migration suites, SOPS transactions, publisher CAS, TLS routes, schema and snapshots passed; full make check is running.
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Complete blue-green lifecycle and operator-path suites exercise preview refusal, exact retirement gates and retained publisher inventory without infrastructure access.
staging: not_applicable
staging_evidence: Source implementation only; no staging deployment is authorized.
live: not_applicable
live_evidence: No real provider, private credential or host operation is part of this change.
client: required
client_evidence: Paired client source, four-baseline behavior, explicit export and shared contract checks are required; physical-device live acceptance is separate.
artifact: not_applicable
artifact_evidence: Repository source and contract fixtures are the deliverables; no separate release artifact is requested.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEVICE-MIGRATION-PLAN | OPS-1792674210176785 | test_device_migration.py, test_device_migration_io.py and test_device_migration_review.py passed, including strict inventory/pins and mutable-input fencing | passed |
| REQ-DEVICE-MIGRATION-CREDENTIALS | OPS-1792674210176785 | test_device_migration_credentials.py passed with real test-only SOPS/age roundtrips and complete journal schema validation | passed |
| REQ-DEVICE-MIGRATION-PUBLISH | OPS-1792674211571053 | test_subscription_migration.py and test_device_migration_route.py passed; actual local publisher CAS, loopback trusted TLS, timeout, lost acknowledgement and cleanup | passed |
| REQ-DEVICE-MIGRATION-RECEIPT | OPS-1792674215498584 | Pending paired client and shared receipt vectors | required |
| REQ-DEVICE-MIGRATION-RETIREMENT | OPS-1792674212965582 | test_device_migration.py, test_blue_green_lifecycle.py, test_device_migration_inventory.py and test_audit_operator_paths.py passed; complete operator-path suite 26 passed, inventory suite 8 passed | passed |

## Completion boundary

Step OPS-1792674228402400 records independent review, complete local gates and
exact-SHA protected PR/main CI. Fixtures establish controller behavior and local
runtime operations; they do not establish deployed or physical-device acceptance.

## Current validation

The combined controller, IO, route and independent-review suites passed (48
tests); the expanded frozen-transport review suite passed with 40 tests. The
subscription template snapshot, example secrets schema and all 165 render
snapshots passed. The full local gate remains pending, as do paired client final
validation and exact protected PR/main CI. Source integration is not deployment
or physical-device acceptance.
