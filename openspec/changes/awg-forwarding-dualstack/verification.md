---
task_id: ANS-1791618048083304
change: awg-forwarding-dualstack
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
staging: not_applicable
staging_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
live: not_applicable
live_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
client: not_applicable
client_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
artifact: not_applicable
artifact_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-FORWARD | ANS-1791618053810186 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-FORWARD | ANS-1791618055065632 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-DUAL | ANS-1791618053112824 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-DUAL | ANS-1791618054450509 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-DUAL | ANS-1791618055065632 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-MTU | ANS-1791618053112824 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-MTU | ANS-1791618054450509 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-MTU | ANS-1791618055065632 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618053810186 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618054450509 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618055065632 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |

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
