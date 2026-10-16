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
client_evidence: "actual supported recipient parser plus authorized arm64 emulator/native-core authenticated IPv4/IPv6 TCP/UDP/DNS at MTU 1280 and 1420 through three reconnects each; physical-device and Android VpnService/TUN gates removed by owner; S3/S4 floor unchanged"
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
| REQ-PROTO-AWG-NOLEAK | ANS-1791618053810186 | Linux routing/nft enforcement and packet observations, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618054450509 | Linux routing/nft enforcement and packet observations, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618055065632 | Linux routing/nft enforcement and packet observations, failed activation compensation and prior-address/profile preservation assertions. | required |

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

The resumed full `build-gate -- mise exec -- make check` acquired a slot and
failed while downloading exact pinned Terraform providers: the UpCloud registry
request and hcloud checksum request timed out. Hosted Terraform validation and
mock-provider tests passed for that source; the local aggregate remains failed.
The exact-source native build remains queued behind machine-wide heavy jobs.
The exact upstream Go checkout initially failed after a partial filtered fetch;
a no-filter refetch repaired the same pinned commit. No runtime or checksum pin
was relaxed. A dedicated root/systemd/TUN container and hash-pinned Python
requirements are prepared for the complete native lane.

Consumer JVM and Android emulator/native-core tests are also gate-queued. The
new evidence target validates that component evidence and does not claim
physical Android VPN leak prevention. The owner explicitly removed physical-device
and Android VpnService/TUN acceptance from this change; the required Android
acceptance is the authorized arm64 emulator/native-core procedure.

Federation originally failed because the client lacked a native shared-contract
export and the deployment tool reparsed peer records using its own risk schema.
The paired changes now add a client-owned validated export and bounded producer
wire validation, preserving all native task records and historical receipts.
The federation/history regression suite passed 141 tests and 43 subtests;
real paired-checkout validation still requires clean committed source in both
repositories. A qualified reference alone is not successful federation. Hosted
contract-sync retains its reviewed consumer integration requirement.

Hosted source CI exposed remaining test callers of the former AWG contracts.
The onboarding positive fixture now uses the required dual-stack HTTPS hostname;
rotation and lifecycle tests follow complete configuration compensation and
retained firewall authority, and the native job assertion includes the new
six-case lane. These changes retain the actual failure/security assertions.

The all-files pre-commit run reached Terraform provider initialization and
failed on registry connection deadlines for the pinned hcloud/Vultr packages.
No Terraform source or pins changed. That aggregate run also encountered a
Galaxy dependency-download stall and baseline vendored-shell/placeholder and
formatting failures. Its formatting edits outside this change were removed;
only owned paths belong in the commit. The actual lint hook is rerun against
the installed exact collection versions. This is a failed aggregate check,
not a waiver; normal commit hooks still apply to every changed path.

The deployment source commit passed every applicable normal commit hook,
including full Ansible lint (696 files), ShellCheck, task contracts, secret
coverage/schema, template rendering and snapshots. The clean branch was pushed
for draft PR review; no hook was bypassed.

Final source review found and fixed a mixed-generation failure: AWG activation
now retains the accepted firewall file through complete service acceptance and
restores it before prior tunnels restart. Fresh unowned distro configurations
use a canonical default-drop baseline with AWG forwarding disabled; global-flush
recovery authority is refused. Two actual Linux nft/Ansible retention cases
passed (owned generation and fresh baseline), preserving a foreign table. The
four authenticated native cases remain unobserved while the build gate waits;
the complete target now includes all six cases. The corresponding portable
firewall/activation/check-mode/semantic regression run passed 133 cases.


## Resumed acceptance (2026-10-16)

The owner explicitly authorized completing this prerequisite as part of the
authenticated-probe implementation. On isolated Linux arm64,
`make test-awg-dualstack-runtime` passed all six selected cases without skips
in 88.10 seconds using the exact pinned source-built AWG ELF runtimes. This
observed constrained-path dual-family traffic, per-instance forwarding/NAT,
reconnects, revocation, no native bypass and old/fresh activation compensation.
The source files exercised are unchanged from integrated source
`cdf85fed48e45600bf6f94907b382b94e5301ba5`.

Fresh consumer arm64 emulator/native-core acceptance and parser checks are
queued under the machine-wide gate. Historical prose about a prior successful
invocation is not reused because its artifact is unavailable. Generic native
acceptance, full local source checks, qualified federation and exact-source
CI remain open gates; the task is not complete.

The three named portable design suites passed all 204 tests on the resumed
source tree. Qualified federation validation passed with 189 tasks against the
current committed consumer source. Final topology native regression passed all
seven cases without skips. These results do not erase the incomplete generic
local native lane (87 passed, 26 failed, 19 setup errors, 6 skipped) or the
registry-network failure of the full aggregate. A fresh configured hosted
native lane and the complete source gate remain required.
