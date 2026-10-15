---
task_id: "ANS-1791618048083304"
change: "awg-forwarding-dualstack"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior; physical Android arm64 must establish the exact currently supported baseline core, three reconnects, DNS and sustained bidirectional transfer; S3/S4 floor remains unchanged"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-FORWARD | ANS-1791618053810186 | Extend firewall render tests and add real nftables namespace enforcement with exact AWG clients, observing per-instance counters and return traffic. | required |
| REQ-PROTO-AWG-FORWARD | ANS-1791618055065632 | Extend firewall render tests and add real nftables namespace enforcement with exact AWG clients, observing per-instance counters and return traffic. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618053112824 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618054450509 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618055065632 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618053112824 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618054450509 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618055065632 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618053810186 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618054450509 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618055065632 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |

## Implementation checks (2026-10-15)

The implementation and coordinated consumer are prepared for source review;
requirement rows above remain required until their complete named evidence is
observed. Consumer work is `po4yka/RIPDPI#DAT-1792081130689287`, proposed in
RIPDPI PR #616. No deployment or actual operator-secret migration occurred.

Observed focused checks:

- Shared device/transport/liveness suite: 155 passed.
- Combined firewall, bundle, sentinel, semantics and dual-stack boundaries: 255 passed.
- Real SOPS/age transactions, fixture round trip, selected consumer generation
  and retirement: 261 passed using real local binaries instead of HOME-sensitive
  tool-manager shims.
- New dual-stack identity, precedence, MTU and uplink boundaries: 42 passed.
- Final schema/transport/profile regression run: 263 passed; related caller
  regression run: 241 passed. Final firewall policy run: 23 passed, including
  both source and destination claim guards before retained conntrack acceptance.
- Role activation and fresh check-mode contracts: 49 passed; dispatch and
  liveness policy guard follow-up: 91 passed.
- Dual-family liveness policy/sentinel boundaries: 85 passed. A complete
  liveness run had one unrelated Xray-startup failure among 151 cases; all three
  affected Xray cases passed unchanged on their focused rerun. This does not
  erase the failed aggregate run.
- All 163 templates rendered, and all 163 snapshots matched after reviewing
  and refreshing only AWG and firewall outputs. Secrets schema and coverage
  validation passed. Affected roles and rotation play passed ansible-lint.

The full `build-gate -- mise exec -- make check` and exact-source native build
are queued behind other machine-wide heavy jobs; these are pending, not passed.
The exact upstream Go checkout initially failed after a partial filtered fetch;
a no-filter refetch repaired the same pinned commit. No runtime or checksum pin
was relaxed. A dedicated root/systemd/TUN container and hash-pinned Python
requirements are prepared for the complete native lane.

Consumer JVM and Android emulator/native-core tests are also gate-queued. The
new evidence target validates that component evidence and does not claim
physical Android VPN leak prevention. Physical baseline evidence remains
required for its separate scope.

Federation validation was attempted and failed because the client checkout
lacks the deployment federation's `tools/tasking/project.json` contract. A
qualified task reference does not stand in for successful federation. Hosted
contract-sync compares the client default branch and remains dependent on the
reviewed client contract integration; the gate is retained.

The all-files pre-commit run reached Terraform provider initialization and
failed on registry connection deadlines for the pinned hcloud/Vultr packages.
No Terraform source or pins changed. That aggregate run also encountered a
Galaxy dependency-download stall and baseline vendored-shell/placeholder and
formatting failures. Its formatting edits outside this change were removed;
only owned paths belong in the commit. The actual lint hook is rerun against
the installed exact collection versions. This is a failed aggregate check,
not a waiver; normal commit hooks still apply to every changed path.
