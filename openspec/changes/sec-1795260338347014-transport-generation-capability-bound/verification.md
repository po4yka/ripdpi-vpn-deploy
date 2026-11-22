---
task_id: SEC-1795260338347014
change: sec-1795260338347014-transport-generation-capability-bound
commit_sha: 0aee909055
local: required
local_evidence: "2026-11-21 working tree on 502ccc540: `python3 -m pytest tests/unit/test_transport_egress_role.py` 131 passed; `make snapshot-check` 200 templates match; `make -k -j 4 check` passed except a stale board (regenerated, `make task-check` then passed) and 7 load-induced timeouts in unrelated modules (runtime-release, deadman, render-inventory), which passed when rerun serially (14 passed). Capability probe in the debian13 Molecule image with capsh: with CAP_SETUID, CAP_SETGID and CAP_KILL the demoted readiness child runs and its timeout kill succeeds; without CAP_SETUID or CAP_SETGID the pre-exec demotion fails; without CAP_KILL the timeout kill raises EPERM. Systemd probe in the same image booted as PID 1 (systemd 257.13): a root unit with the generation unit's sandbox and `CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_KILL` (CapBnd 0xe0) ran `systemctl start`, `show`, `kill --kill-whom=main`, `stop`, `reset-failed` and `journalctl --unit --boot --output=json`, all successfully, so unit control needs UID 0 and no CAP_SYS_ADMIN. Local Molecule did not run: the Colima VM could not resolve ghcr.io, so the image pull and full-stack prepare failed before any role task."
remote_ci: passed
remote_ci_evidence: "PR 669 (head fb80db52c0): 59 checks passed, none failed. Main CI run 44923464687 on 696cab2c64, which contains all four follow-up changes and the refreshed debian13 Molecule image (PR 674): 84 of 84 jobs passed on 2026-11-21, including the four pytest groups, native runtime integration, native transport runtime acceptance and native four-transport acceptance lanes, every Molecule group and the Trivy scans of the refreshed images. The transport-egress Molecule group and the native transport lanes ran the generation controller under the bound."
dry_run: passed
dry_run_evidence: "make dry-run at b56ed6434 passed on node-a, node-b and node-c (3, 4 and 4 predicted changes, all the transport-egress generation candidate and TLS issuance prediction); node-a used a static site/ bundle of its unchanged self-steal pages, required since 81f10188a."
staging: required
staging_evidence: "Partial, 2026-11-22: one disposable UpCloud node vpn-ci-staging-acc1 (device-full-staging, source 90442f787) was provisioned with a pinned SSH host-key seed, Tailnet-enrolled (lock-signed key), ownership-migrated and deployed; the data plane converged (xray, hysteria, nginx, AWG active). The controller then refused the disposable four-profile proof (onboarding-refused): the generated staging certificate is self-signed and the operator Colima executor does not trust it, while the liveness profiles require verified TLS. The node was destroyed through make staging-destroy with verified provider absence. Observed on the node: ripdpi-transport-generation.service active with CapabilityBoundingSet=cap_kill cap_setgid cap_setuid and NoNewPrivileges=yes; after a reboot (new boot_id) the unit returned active, Result=success, NRestarts=0, no failed units. Not done: the WARP namespace refresh (needs a Cloudflare WARP registration) and the fresh four-profile proof."
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
