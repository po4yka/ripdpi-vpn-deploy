---
task_id: OPS-1795165613781138
change: ops-1795165613781138-ops-roles-live-audit-repairs
commit_sha: null
local: passed
local_evidence: "On the task branch, 2026-11-20: the serial pytest run of the 23 affected tests/unit files passed (876 tests after one replaced test was rerun), with tests/unit/test_runtime_release_contract.py passing when run one test at a time; make snapshot-check, make docs-check, make task-check, make shellcheck and make validate exit 0. Molecule did not run locally (amd64-only images on an arm64 Docker host) and the Linux-only native tests did not run; both rest on remote CI."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: Role and script changes with no staging-only path; Molecule and the per-node dry run cover them.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client contract, bundle or recipient material changes.
artifact: not_applicable
artifact_evidence: No built or published artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-WATCHDOG-PROFILES | OPS-1795165849317051 | `pytest tests/unit/test_deploy_profile_guard.py tests/unit/test_fleet_status.py` | passed locally; Molecule and native tests rest on CI |
| REQ-WATCHDOG-STATS-DIAGNOSTIC | OPS-1795165849317051 | `pytest tests/unit/test_watchdog_protocol_probe.py` | passed locally; Molecule and native tests rest on CI |
| REQ-WATCHDOG-OUTAGE-BUDGET | OPS-1795165849317051 | `pytest tests/unit/test_watchdog_protocol_probe.py` | passed locally; Molecule and native tests rest on CI |
| REQ-WATCHDOG-RESOURCE-BOUNDS | OPS-1795165849317051 | `make snapshot-check` | passed locally; Molecule and native tests rest on CI |
| REQ-BACKUP-START-DEADLINE | OPS-1795165951713970 | `pytest tests/unit/test_backup_restore_drill_contract.py`, `make snapshot-check` | passed locally; Molecule and native tests rest on CI |
| REQ-BACKUP-REMOTE-IDENTITY | OPS-1795165951713970 | `pytest tests/unit/test_backup_stage_status_contract.py` | passed locally; Molecule and native tests rest on CI |
| REQ-RESTORE-DRILL-WINDOW | OPS-1795166046539242 | `pytest tests/unit/test_fleet_inspection.py tests/unit/test_backup_restore_drill_contract.py tests/unit/test_observability_agent_health_render.py` | passed locally; Molecule and native tests rest on CI |
| REQ-INSPECT-REBOOT-SIGNAL | OPS-1795166130277066 | `pytest tests/unit/test_fleet_inspection.py` | passed locally; Molecule and native tests rest on CI |
| REQ-UPGRADE-WINDOW-STAGGER | OPS-1795166130277066 | `pytest tests/unit/test_package_updates_check_mode.py`; Molecule `package_updates` | passed locally; Molecule and native tests rest on CI |
| REQ-TAILSCALED-NO-LOG-UPLOAD | OPS-1795166204645783 | `pytest tests/unit/test_tailnet_management.py`; Molecule `tailnet-management` | passed locally; Molecule and native tests rest on CI |
| REQ-ACTIVATION-LOCK-DEADLINE | OPS-1795166204645783 | `pytest tests/unit/test_runtime_release_contract.py` | passed locally; Molecule and native tests rest on CI |
| REQ-LYNIS-OFFLINE | OPS-1795166204645783 | `pytest tests/unit/test_audit_improvement_host_contracts.py` | passed locally; Molecule and native tests rest on CI |
