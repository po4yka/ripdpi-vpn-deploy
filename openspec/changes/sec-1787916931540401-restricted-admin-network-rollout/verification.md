---
task_id: SEC-1787916931540401
change: sec-1787916931540401-restricted-admin-network-rollout
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: no Android or client contract change; actual SSH and VPN path probes belong to staging and live evidence
artifact: not_applicable
artifact_evidence: source and installed configuration only; no release binary artifact
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ADMIN-ISOLATION | SEC-1787917605386179 | Opt-in management configuration tests and staged resolver, routing and host-key comparisons | pending |
| REQ-ADMIN-SCOPE | SEC-1787917605386179 | Reviewed full ACL diff and positive/negative policy and connection tests | pending |
| REQ-ADMIN-MIGRATION | SEC-1787917604306451 | 45 planner regressions include real OpenSSH full effective parity, custom port, unknown-layout, bounded execution and read-set races | local source passed; hosted and staging pending |
| REQ-ADMIN-ROLLBACK | SEC-1787917604868749 | SSH fault injection covers publication boundaries, timeout, boot identity reconciliation, stale confirmation and corrupt state; native installation/upgrade acceptance passed | SSH foundation local passed; guest firewall, real reboot and hosted acceptance pending |
| REQ-ADMIN-PROMOTION | SEC-1787917605886845 | Exact-node selector, fresh strict SSH, required DNS/VPN probes and external provider rollback evidence | pending |
| REQ-ADMIN-EVIDENCE | SEC-1787917606418274 | Real isolated staging login, forced disconnect, reboot recovery and repeat rollback before fleet promotion | pending |

## Gates and remaining boundaries

The SSH foundation on base `2009b6f694e326fa1f6d99333da497544b115cdd`
passed the full local `make -j1 check` gate on 2026-08-28: 1688 unit tests
passed with one existing network skip, 55 Bats tests passed, all four provider
mock suites and policy checks passed, and Rust Clippy plus 169 tests passed.
The five new SSH modules' test files contain 164 passing tests. Separate
`make validate`, staged secret scanning and independent source review passed.
The full gate includes real local OpenSSH syntax and effective-policy checks;
it does not prove remote login or a guest reboot.

Native ARM systemd installation acceptance passed for the seven source files
in `4c4a6b41e438994bb743f1e6ff6696b761990d73`, with all copied SHA256 values
independently matched to the committed source. The isolated Ubuntu 24.04 image
was pinned to `sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90`;
systemd 255.4 ran as PID 1 and OpenSSH was 9.6p1. The earlier candidate failed
because systemd collected completed service timestamps; the current timer
dependency retention and journal-guarded worker quiescence fixed that failure.
Observed cases: initial installation with overdue OnBoot timer, unchanged
repeat, retained boot metrics and a fresh periodic execution after 17 seconds,
fixture generation upgrade and repeat, and actual transaction-lock contention
returning 75 while readiness refused it. After unlocking, worker exit 0 and
readiness passed. An internal loopback SSH process kept its PID and activation
timestamp across the fixture upgrade. All three units passed systemd-analyze
verification, and the isolated container was removed with absence confirmed.
This is not real SSH login, guest reboot or a real release-upgrade proof.
PR #117 is published; exact-head hosted CI remains pending.

Normal baseline convergence still restores the old duplicate authentication
directives, and fresh bootstrap ownership has not yet been aligned. Do not
perform a real-node ownership migration until that separate source change is
delivered. Tailnet configuration, guest/provider network transactions,
staging and serial production acceptance remain unfinished.

Local source work is authorized. No local test implies staging or live acceptance. Provisioning waits for available approved executor, verified actual cost/credit, exact-resource cleanup and the approved deadline; policy application waits for a fresh separately approved ACL diff. The serial fleet step remains open until observed direct and Tailnet SSH and actual VPN probes all pass.
