---
task_id: OPS-1792263187492070
change: deployment-vpn-reliability
commit_sha: 992c8905ff7acb31eb1b1d58047567ec6ed71f8c
local: passed
local_evidence: Focused 253-test consolidated result; final 97-test VPN/baseline bundle; final 65-test site/source suites; all applicable commit hooks, 164 snapshots and structured P0 review passed. Complete local gate remains host-limited as documented below.
remote_ci: required
remote_ci_evidence: null
dry_run: passed
dry_run_evidence: Actual blue-green environment dry-run exited zero without a SSH key or SOPS input; 12 Bats cases and ordered Make regressions passed. This is credential-free source prediction, not a real-host deployment check.
staging: not_applicable
staging_evidence: Source-only repair; no external staging resource is authorized or required. Isolated native runtime evidence belongs to remote_ci and artifact.
live: not_applicable
live_evidence: Source-only PR and merge; no external rollout is in scope.
client: not_applicable
client_evidence: No recipient device or external client acceptance is requested. Isolated test traffic does not establish live service health.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DR-ORDER | OPS-1792263261040276 | Executable inherited-parallel Make regression | required |
| REQ-DR-PREDICT | OPS-1792263261040276 | Environment and CLI dry-run regression with no private inputs | required |
| REQ-DR-STATE | OPS-1792263261891666 | Actual shell retention and documented recovery selection with synthetic encrypted state | required |
| REQ-DR-FIREWALL | OPS-1792263262980365 | Cross-role failure and tagged dependency regression | required |
| REQ-DR-AWG | OPS-1792263262980365 | Rejected executable/unit restoration and isolated native acceptance | required |
| REQ-DR-CHILD | OPS-1792263263700589 | Real exited-leader and retained-descendant deadline tests | required |

## Source scope

The starting source is 50cd9346c4a5f7e850f08a353c8877d5b1b50bf5.
All results below must retain their exact source and scope; no live deployment is claimed.

## Local observations before source publication

The consolidated focused command selected state-backup, blue-green, bootstrap
supervision, CI deployment, shared runtime acceptance, AWG profile, ingress
transaction, VPN consumer and instruction-contract suites. It passed 253 tests
and deselected one native test. This result precedes the final forwarding and
rescue-order adjustment; their final results must be recorded below.

Additional observed checks include 12 blue-green Bats cases, real age retention
and recovery cases, 164 matching template snapshots and targeted Ansible lint.
The native AWG fixtures collect nine cases. Collection does not establish runtime
acceptance. Hosted Linux execution remains required before merge.

The first complete local gate failed because the host ran out of disk space.
A repeat is queued behind the shared build slot. Docker Desktop is unavailable;
no local native or Molecule execution is claimed. The first structured review
reported no actionable P0 finding. Independent review then found and repaired
the inline Python composition and firewall recovery ordering; final review is
still required for the completed source.

## Final source review and focused evidence

The final VPN/baseline command passed 97 tests across
`test_baseline_forwarding_transaction.py`, `test_baseline_sysctl_recovery.py`,
`test_vpn_consumer_reliability.py`, `test_runtime_awg_profile.py`,
`test_amneziawg_check_mode.py`, `test_amneziawg_reload_contract.py` and
`test_transport_p2_lifecycle.py`. After the last required YAML line wrap, the
13 forwarding regressions passed again and Ansible lint passed for that file.
Four focused site tests confirm that firewall restoration precedes old runtime
readiness. The final site/source command passed all 65 tests in 431.60 seconds without skips.

The final structured review of the frozen source reported no actionable P0
finding. TruffleHog passed for that exact review bundle. The security review
verdict is APPROVE: private candidate data retains `no_log`, fixed helper and
executable authority is bounded, and no listener, credential or deployment
authority is added. Runtime and native evidence remains separate. The existing
one-live-deploy-per-node constraint still applies.

## Source receipt

Source commit: `992c8905ff7acb31eb1b1d58047567ec6ed71f8c`. All applicable
commit hooks passed with no bypass. The direct environment dry-run also exited
zero with an absent SOPS input and no SSH key. Its output was a plan only.
The final site/source suites passed 65 tests without skips.
