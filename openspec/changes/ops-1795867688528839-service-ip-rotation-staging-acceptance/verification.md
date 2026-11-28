---
task_id: OPS-1795867688528839
change: ops-1795867688528839-service-ip-rotation-staging-acceptance
commit_sha: null
local: not_applicable
local_evidence: No source change; source coverage belongs to OPS-1795856574795376.
remote_ci: not_applicable
remote_ci_evidence: No source change; protected-main checks belong to OPS-1795856574795376.
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Rotating a production node is a separate operator decision.
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---
# Verification

The staging run has not started. It needs operator authorization, provider credentials and a client device.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SIPA-STAGING | OPS-1795867789913124 | Dry-run, plan, deploy, verify and burn-check records of the attach and retire cycle | required |
| REQ-SIPA-CLIENT | OPS-1795867789913124 | Device lifecycle refresh receipt with authenticated traffic on the new address | required |

## Shared operational evidence ownership

| Source task | Operational owner | Requirement | Acceptance command | Evidence category | Source revision |
|---|---|---|---|---|---|
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GENERATIONS | `make dry-run ENV=staging` | dry_run | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-SPLIT | `make dry-run ENV=staging` | dry_run | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GUEST | `make dry-run ENV=staging` | dry_run | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-POLICY | `make dry-run ENV=staging` | dry_run | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GENERATIONS | `make deploy ENV=staging` | staging | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-SPLIT | `make deploy ENV=staging` | staging | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GUEST | `make deploy ENV=staging` | staging | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-POLICY | `make deploy ENV=staging` | staging | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GENERATIONS | `make device-lifecycle ACTION=refresh` | client | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-SPLIT | `make device-lifecycle ACTION=refresh` | client | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-GUEST | `make device-lifecycle ACTION=refresh` | client | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
| OPS-1795856574795376 | OPS-1795867688528839 | REQ-SIP-POLICY | `make device-lifecycle ACTION=refresh` | client | 0938faa0968b0bb1d0433f4f8301b0b796b8f42d |
