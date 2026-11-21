---
task_id: SEC-1795260338347014
change: sec-1795260338347014-transport-generation-capability-bound
commit_sha: null
local: required
local_evidence: "2026-11-21 working tree on 502ccc540: `python3 -m pytest tests/unit/test_transport_egress_role.py` 131 passed; `make snapshot-check` 200 templates match; `make -k -j 4 check` passed except a stale board (regenerated, `make task-check` then passed) and 7 load-induced timeouts in unrelated modules (runtime-release, deadman, render-inventory), which passed when rerun serially (14 passed). Capability probe in the debian13 Molecule image with capsh: with CAP_SETUID, CAP_SETGID and CAP_KILL the demoted readiness child runs and its timeout kill succeeds; without CAP_SETUID or CAP_SETGID the pre-exec demotion fails; without CAP_KILL the timeout kill raises EPERM. Systemd probe in the same image booted as PID 1 (systemd 257.13): a root unit with the generation unit's sandbox and `CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_KILL` (CapBnd 0xe0) ran `systemctl start`, `show`, `kill --kill-whom=main`, `stop`, `reset-failed` and `journalctl --unit --boot --output=json`, all successfully, so unit control needs UID 0 and no CAP_SYS_ADMIN. Local Molecule did not run: the Colima VM could not resolve ghcr.io, so the image pull and full-stack prepare failed before any role task."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-GENERATION-CAPABILITY-BOUND | SEC-1795260429892810 | Rendered unit golden and `test_generation_controller_retains_uid_drop_without_changing_recipient_capabilities` pin `CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_KILL`; the role note names the operation for each capability; capsh probe shows each one is needed | pass (local) |
| REQ-GENERATION-CAPABILITY-OPERATIONS | SEC-1795260460933493 | pending | pending |
