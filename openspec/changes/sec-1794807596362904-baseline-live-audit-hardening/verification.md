---
task_id: SEC-1794807596362904
change: sec-1794807596362904-baseline-live-audit-hardening
commit_sha: e4d5df3ad5e8bd1556f682838df0dd4f9e5bfead
local: passed
local_evidence: "make task-check, make snapshot-check and make validate exit 0. make -k -j 4 check ran the unit suite with 12173 passed and 6 failed under parallel load; the 6 pass in a serial rerun (368 passed). The two Linux-only tests in tests/unit/test_host_policy_native.py and Molecule (amd64-only images on an arm64 host) did not run locally and rest on remote CI."
remote_ci: passed
remote_ci_evidence: "Pull requests 615, 618 and 627 passed their checks before merge, including the Molecule scenarios for baseline, monitoring and tailnet-management. The main CI run on 643a7717edf6286710298bbd584d5992027288b4, the deployed revision, completed with success."
dry_run: passed
dry_run_evidence: "Full canonical dry-run at 643a7717edf6286710298bbd584d5992027288b4 on 2026-11-16 for each node, exit 0 and 0 failed: node-a 8 changed, node-b 9, node-c 8, split-hop node B 5, split-hop node A 9. Every changed task was reviewed before deploy; each is a change from this task or a check-mode prediction seen in earlier accepted previews."
staging: not_applicable
staging_evidence: Host policy change with no staging-only path; Molecule and the per-node dry run cover it.
live: passed
live_evidence: "Deployed at 643a7717edf6286710298bbd584d5992027288b4 on 2026-11-16. node-a, node-b and node-c: deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness exit 0, with profiles p0-reality, p1-xhttp, p2-amneziawg and p2-hysteria2 ok from the external sentinel. Split-hop node A and node B: deploy, verify, source-drift and security-verify exit 0; the sentinel proof for node A passed after its generation was reinstalled. security-verify includes the root password and kernel key checks from this task. The first deploy of node-a and of node-c converged the site and then stopped at the controller promotion step; a second round passed with no further host change on node-c and one prediction on node-a. A read-only check on all five nodes after the deploy showed kernel.kexec_load_disabled 1, IPv6 redirects refused and no Tailscale apt pin; the journal flush marker and /var/log/journal exist on the four nodes that run the monitoring role, and split-hop node B, which does not run it, still keeps its journal in memory. No device test was run. The observer host does not run these roles."
client: not_applicable
client_evidence: No client contract, bundle or recipient material changes.
artifact: not_applicable
artifact_evidence: No built or published artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-BASELINE-KERNEL-GAPS | SEC-1794807731415728 | `pytest tests/unit/test_baseline_sysctl_recovery.py`, `make snapshot-check`; Molecule `baseline` in CI | passed: CI and live deploy at 643a7717 |
| REQ-BASELINE-ROOT-LOCK | SEC-1794807783915807 | Molecule `baseline` prepare and verify in CI; `security-verify` root status check on a node | passed: CI and live deploy at 643a7717 |
| REQ-BASELINE-UNUSED-PACKAGES | SEC-1794807812667879 | `pytest tests/unit/test_baseline_vps_packages.py`; simulated purge with autoremove on two live nodes; Molecule `baseline` in CI | passed: CI and live deploy at 643a7717 |
| REQ-JOURNAL-BUDGET | SEC-1794807838451591 | `pytest tests/unit/test_monitoring_journald.py` | passed: CI and live deploy at 643a7717 |
| REQ-JOURNAL-ON-DISK | SEC-1794815487021281 | `pytest tests/unit/test_monitoring_journald.py`; Molecule `monitoring` verify in CI; journal location on a live node | passed: CI and live deploy at 643a7717 |
| REQ-TAILSCALE-NO-APT-HOLD | SEC-1794825780144669 | `pytest tests/unit/test_tailnet_management.py`; Molecule `tailnet-management` in CI; `apt-cache policy tailscale` on a live node | passed: CI and live deploy at 643a7717 |
