---
task_id: SEC-1794807596362904
change: sec-1794807596362904-baseline-live-audit-hardening
commit_sha: null
local: passed
local_evidence: "make task-check, make snapshot-check and make validate exit 0. make -k -j 4 check ran the unit suite with 12173 passed and 6 failed under parallel load; the 6 pass in a serial rerun (368 passed). The two Linux-only tests in tests/unit/test_host_policy_native.py and Molecule (amd64-only images on an arm64 host) did not run locally and rest on remote CI."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: Host policy change with no staging-only path; Molecule and the per-node dry run cover it.
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
| REQ-BASELINE-KERNEL-GAPS | SEC-1794807731415728 | `pytest tests/unit/test_baseline_sysctl_recovery.py`, `make snapshot-check`; Molecule `baseline` in CI | local passed; CI and live pending |
| REQ-BASELINE-ROOT-LOCK | SEC-1794807783915807 | Molecule `baseline` prepare and verify in CI; `security-verify` root status check on a node | CI and live pending |
| REQ-BASELINE-UNUSED-PACKAGES | SEC-1794807812667879 | `pytest tests/unit/test_baseline_vps_packages.py`; simulated purge with autoremove on two live nodes; Molecule `baseline` in CI | local passed; CI and live pending |
| REQ-JOURNAL-BUDGET | SEC-1794807838451591 | `pytest tests/unit/test_monitoring_journald.py` | local passed; live pending |
