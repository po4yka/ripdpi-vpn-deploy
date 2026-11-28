---
task_id: OPS-1795856574795376
change: ops-1795856574795376-service-ip-rotation
commit_sha: 0938faa0968b0bb1d0433f4f8301b0b796b8f42d
local: passed
local_evidence: "Implementation f9c981b78 (merged as f9c0988a3, #782): tofu test upcloud 101, hetzner 66, vultr 86, scaleway 61 passed; conftest verify 101/101; native provider bootstrap lifecycle 24 passed; make -k check passed except five pre-existing ansible-lint line-length hits outside this change and one load-sensitive kuma test that passes alone. Follow-ups 32b996347 (#784, ansible-lint baseline roles passed) and 97ea66971 (#786, native stub modules collect)."
remote_ci: passed
remote_ci_evidence: "main ci run 46144362488 at 0938faa09, which contains f9c0988a3, 3887e5617 and 4c2e33cf2: every tofu fmt, validate and test job, ansible-lint + syntax-check, all pytest groups, all Molecule scenarios including baseline and tailnet-management, native runtime integration 1-4, native transport runtime acceptance 1-4 and native four-transport acceptance core-1, core-2 and recovery-1 to 4 passed. contract-sync, the two observability-kuma trivy scans and the required-checks aggregate failed, as they did on b8c16a8ef (run 46134832790) before this change; this change touches none of their inputs."
dry_run: not_applicable
dry_run_evidence: "Owner decision on 2026-11-28: dry-run evidence moves to OPS-1795867688528839 (mapping below). The feature is off by default; an empty service_ipv4_generations list renders the same inventory addresses as before."
staging: not_applicable
staging_evidence: "Owner decision on 2026-11-28: staging evidence moves to OPS-1795867688528839 (mapping below). Offline proof meanwhile: mock-provider plans for all four roots and the baseline Molecule attach, retire and clear sequence, which passed in CI on #782."
live: not_applicable
live_evidence: Rotating a production node is a separate operator decision.
client: not_applicable
client_evidence: "Owner decision on 2026-11-28: client evidence moves to OPS-1795867688528839 (mapping below). Offline proof meanwhile: client payload, device lifecycle and device migration route tests with distinct host and service addresses."
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---
# Verification

Local and CI evidence covers plan shape, inventory rendering, guest `/32` lifecycle and consumer selection. Provider attach timing, provider-edge delivery to the new address and device refresh from filtered networks move to `OPS-1795867688528839`.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SIP-GENERATIONS | OPS-1795857751222463 | `make tf-test`: three `service_ipv4_*` runs per provider root | passed |
| REQ-SIP-SPLIT | OPS-1795857809017056 | `tests/unit/test_render_inventory.py`, `test_fleet_inspection.py`, `test_fleet_rotation.py`, `test_device_migration_route.py`, vpnd runner tests | passed |
| REQ-SIP-GUEST | OPS-1795858050569373 | Molecule `baseline` attach, retire and clear sequence in CI on #782 | passed |
| REQ-SIP-POLICY | OPS-1795857932939870 | `make tf-policy-verify` | passed |

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
