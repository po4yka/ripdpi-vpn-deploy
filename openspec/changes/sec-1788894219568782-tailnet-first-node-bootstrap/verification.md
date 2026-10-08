---
task_id: SEC-1788894219568782
change: sec-1788894219568782-tailnet-first-node-bootstrap
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
staging: not_applicable
staging_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
live: not_applicable
live_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
client: not_applicable
client_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
artifact: not_applicable
artifact_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
---

# Verification

The corrected cold-backend source passed fresh recovery on disposable staging,
but ordinary SSH apply failed. Two execution steps remain open. Current
verification belongs to the apply observation repair and does not inherit
earlier full staging acceptance.
The prior protected-source observations below remain historical evidence.

## Periodic-worker overlap at ordinary apply — 2026-10-04

The preserved protected-source failure is `apply-rpc-failed`; its deleted
guest has no retained internal apply log, so the precise guest cause cannot
be asserted. A deterministic real baseline planner/transaction regression
reproduced `recovery-not-ready` when the actual systemd adapter observed an
in-flight periodic worker. Unlike readiness, activation previously rejected
that state before asking for its fresh execution.

The shared observation waits for the same invocation, generation, boot and
boot-worker identity. A failed or ambiguous result refuses before restart;
known exit-75 contention permits only the existing fresh execution request.
Observation, fresh exit-zero proof and its capability check share the same
30-second deadline; the transaction's later lock fence remains mandatory.
The original regression failed before repair, then the four affected SSH
modules passed 370 tests. Both independent read-only review axes approved.
Native systemd, complete local/hosted gates and fresh corrected-source
staging remain required. No execution step is closed by these fixtures.

## Cold-backend reboot failure and repair — 2026-10-03

Persistent guest logs from protected `6b29c727` show early firewall recovery
succeeded at 10:02:00 UTC. Late recovery failed with `tailnet-status-invalid`
at 10:02:01.222 while tailscaled was still `NoState`; backend transitions to
`Starting` and `Running` followed at 10:02:01.350 and 10:02:01.599. The
required late unit failed the original SSH start job. A periodic retry rolled
back successfully at 10:02:07.487 but did not requeue that failed SSH job.

Approved read-only console diagnostics verified the installed graph and
restored ordinary init. Pinned SSH/SFTP and canonical idle checks then passed.
That diagnostic boot retained a temporary kernel init argument and cannot
replace the failed canonical reboot evidence. The repair bounds backend
initialization without changing systemd dependencies or identity ownership.
The original regression failed before repair and all 137 domain tests passed
afterward. A review regression also reproduced reinitialization at the identity
query; all pre-logout observations now share the same bounded poll and retain
foreign-identity refusal. The earlier 5048-case full local gate and 75-job hosted
gate passed on the preceding repair, but the final repair requires fresh gates.
Exact corrected-source hosted and runtime acceptance remain open.

## Exact-source ordinary and separate recovery acceptance — 2026-09-29

### Historical acceptance metadata

```yaml
task_id: SEC-1788894219568782
change: sec-1788894219568782-tailnet-first-node-bootstrap
commit_sha: 8ab19efc1e2f92f97235ddad8b56c95a7aed1b75
local: passed
local_evidence: "Exact protected source 8ab19efc1e2f92f97235ddad8b56c95a7aed1b75 passed build-gate -- make check: 4709 pytest cases, 4 canonical native-runtime cases deselected locally, 20 subtests, 55 Bats cases, Rust tests and clippy, Terraform validation and policies, snapshots, gitleaks, shellcheck, Ansible lint and syntax. Native runtime and affected Molecule scenarios passed in the exact-source hosted gate."
remote_ci: passed
remote_ci_evidence: "Protected-source push run 36496105992 completed successfully at exact SHA 8ab19efc1e2f92f97235ddad8b56c95a7aed1b75: all 75 jobs succeeded, including native runtime integration, tailnet-management/firewall/baseline Molecule, both full-stack jobs, failure scenarios, image scans and required checks."
dry_run: passed
dry_run_evidence: "Ordinary isolated staging dry-run used the confirmed observed-context handoff and exact-node promotion configuration: ok=214 changed=68 failed=0 unreachable=0. Permanent-node dry-run remains unperformed under the separate live category."
staging: passed
staging_evidence: "Three separate disposable nodes on exact 8ab19efc source and digest 4081ecaf5614deb40809dad09060d62d72be79435019121413ea6773bf7e60b9 proved ordinary SSH/2222 deployment, real enrolled controller-loss recovery and real enrolled reboot recovery. Normal staging included positive dual-path bootstrap, SSH ownership, deploy/reconvergence, verify, security-verify, source-drift, four protocols, provider-firewall promotion, identity/deadline-preserving manifest reissue and guarded server/root-storage absence for all three nodes."
live: blocked
live_evidence: "No permanent-node rollout or serial live acceptance was performed."
client: passed
client_evidence: "Owned isolated current profiles and pinned runtimes proved authenticated REALITY, XHTTP, Hysteria2 and AmneziaWG traffic plus tunneled DNS before and after firewall promotion. A separate post-promotion invocation observed a fresh AWG handshake. These are staging client observations; permanent-fleet traffic remains unproved."
artifact: passed
artifact_evidence: "Separate mode-0600 controller-loss/reboot artifacts matched exact source, deployable digest and wrapper hashes under mode-0700 parents; reboot binding was independently recomputed. Diagnostics and fault-test handoffs remained absent. Canonical client/executor retirement, DNS absence and all three guarded provider-absence receipts passed within expiry. Own ephemeral nodes and ACL are absent; persisted policy equals the original byte-for-byte. Own API token deletion returned 204 and the old credential subsequently returned 401 AUTHENTICATION_FAILED; its local plaintext file was removed. Foreign capabilities were preserved."
```

All three invocations used deployable digest
`4081ecaf5614deb40809dad09060d62d72be79435019121413ea6773bf7e60b9`.
Normal staging used SSH/2222, confirmed real public/Tailnet SSH and SFTP,
then explicitly committed SSH ownership before ordinary deployment. The first
deploy refused an active unattended-upgrade dpkg lock; after that OS operation
completed, canonical reconvergence passed with ok=230 changed=18 and no failed
or unreachable tasks. Verify, security-verify and separate source-drift passed
before and after provider-firewall promotion. Promotion changed only the same
server's firewall activation and reissued cleanup authority without extending
expiry. Public/Tailnet SSH, SFTP, listener parity, outbound HTTPS/UDP DNS and
authenticated four-profile traffic passed on both sides of promotion. A
distinct later invocation proved another fresh AWG handshake.

The separate controller-loss node killed a durably pending real enrollment
without confirmation or explicit rollback. After the unchanged 300-second
lease, autonomous recovery, idle state, strict preinstall, fresh public SSH
and SFTP passed. Boot-change/current-boot flags were correctly false.

The separate reboot node's third canonical invocation passed all seven checks,
including changed boot identity and both current-boot recovery phases. Its
first two invocations exited nonzero without success evidence or diagnostics;
their failing stage is unproved and neither counts as acceptance. No lease,
deadline, timeout or check was weakened for the successful invocation.

Provider transport failures during cleanup remain failure observations; a
later unchanged canonical guarded cleanup succeeded. All three server/root
receipts verify absence, no active owned billing resources and completion
within the approved deadline. Owned client/executor, keys, DNS, nodes, ACL and
provider credential were retired. Permanent-node SSH still timed out; working
console access and owner rotation of the exposed VNC credential remain needed.
No permanent-node mutation or acceptance is credited here.

## Current ordinary staging and controller-loss checkpoint — 2026-09-28

On the same exact protected source `52eda3d97feb4b697e1465beee55df2e9f5b3eed`
and digest `a86591e11b5fc6d1f5b2b9405089353cc5e177e66ebe85c65062e6a4952fb983`,
the owned ordinary invocation passed positive pinned bootstrap, dual-path
handoff, SSH ownership transaction, ordinary dry-run/deploy, verify and
security-verify. All four authenticated profiles passed before and after
provider-firewall promotion, with a distinct fresh AWG handshake. Resource
identity and expiry were retained through state-bound cleanup-manifest reissue.
Canonical client/executor retirement and guarded provider absence passed.

A fresh, separate controller-loss invocation then exited zero after SIGKILL of
durable pending without confirmation or explicit rollback. Autonomous recovery,
idle, preinstall, pinned public SSH and SFTP passed. Its atomically published
0600 success file beneath a 0700 parent matched the exact source, deployable
digest and wrapper input hash; the incomplete diagnostic was absent. Unlike
reboot, boot-change and current-boot flags are correctly false for this scenario.
Guarded deletion completed at 17:32:34 UTC within expiry, with server/root 404,
no active owned billing resources, automatic own ephemeral-node absence and
retirement of the own watchdog and private one-use capabilities.

This checkpoint supersedes the earlier statements that ordinary staging and
current-source controller-loss were unavailable. The earlier exact-source
reboot proof remains separate. Agreed permanent-node acceptance and remaining
requirement reconciliation still prevent terminal closure; no execution step
is marked complete by extrapolation from staging.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TFB-INPUT | SEC-1788894502237285 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-TFB-BOUNDARY | SEC-1788894503320732 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-TFB-RECOVERY | SEC-1788894502776578 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-TFB-PROOF | SEC-1788894503869488 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-TFB-DEPLOY | SEC-1788894503869488 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-UPF-STAGING | SEC-1788894504408980 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-TFB-ACCEPTANCE | SEC-1788894504951632 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |

## Required evidence scopes

- Local: complete changed-module tests, affected Molecule scenarios, native
  Linux systemd/nftables recovery, `build-gate -- make ci-fast`, and
  `build-gate -- make validate`; record exact tested SHA and command results.
- Remote CI: all required hosted checks on the exact implementation revision,
  with current run URLs and conclusions; queued or skipped work is not proof.
- Dry-run: ordinary deploy with actual observed bootstrap socket contexts and
  a valid exact-node promotion configuration; no capability consumed.
- Staging: one authorized disposable clean node; redacted private evidence from
  the fixed controller-loss and reboot operations, including exact worker death,
  parent-loss worker cleanup, fresh recovery invocations, changed boot identity
  for reboot, idle state, restored public SSH/SFTP, distinct recovery/handoff
  outputs, and categorical audit records; then positive bootstrap, ordinary
  deploy, provider firewall promotion and acceptance.
- Live: agreed serial one-node checks after staging and a valid operator
  window, preserving public recovery. Lack of current authority blocks this
  category and must not be relabeled as a local-only success.
- Client: real authenticated required VPN profiles with exact target binding;
  successful enrollment or on-node status does not satisfy this category.
- Artifact: private mode-0600 recovery evidence and observed-context handoff,
  private mode-0600 SSH baseline failure receipts with unsafe/existing preflight
  refusal, late no-clobber race, and redaction regressions,
  unchanged host identity, cleanup manifests with unchanged resource
  identities/deadlines, redacted guarded-delete receipts, and authenticated
  exact-resource provider absence.

Record failures and rollbacks with the same scope precision as successes.
Never copy secrets, raw provider state, or sensitive capability material into
this document. No requirement may close on refusal-only implementation.

## Reboot acceptance diagnostic checkpoint — 2026-09-27

Controller-loss staging acceptance passed on an exact earlier main revision.
The first provider reboot exercise observed public SSH go down but exhausted
all bounded reconnect attempts without producing reboot success evidence. A
later operator-authorized provider power cycle restored the node; fresh public
checks then observed idle Tailnet state, successful current recovery units and
no failed units. The image did not retain the prior boot journal, so that later
recovery cannot prove the failed reboot attempt.

Before consuming another one-use enrollment key, the in-progress harness patch
adds a separate redacted private `incomplete` diagnostic for failures after SSH
loss and adds static complete-graph parsing with real `systemd-analyze` inside
a PID 1 container. The inert daemon fixture is not vendor-unit, activation, or
reboot evidence. This checkpoint is failure analysis, not acceptance. The patch,
its exact-SHA local/hosted gates, the repeated reboot exercise, positive
bootstrap, ordinary deployment, protocol proof and guarded deletion all remain
required; execution step `SEC-1788894504951632` stays open.

## Successful exact-main reboot acceptance — 2026-09-28

The diagnostic hardening merged through the protected branch as exact main
`52eda3d97feb4b697e1465beee55df2e9f5b3eed`, with deployable digest
`a86591e11b5fc6d1f5b2b9405089353cc5e177e66ebe85c65062e6a4952fb983`.
All 81 pull-request checks passed before merge. The exact main push then
completed `ci`, `codeql`, `scorecard` and `release-please` successfully; all
80 post-merge check runs completed without a failure.

An operator-authorized disposable provider run replaced the obsolete wrapper
with schema 2 and fresh distinct success/diagnostic outputs, then supplied a
new single-use one-day ephemeral enrollment key without placing it in command
arguments, logs or repository files. The fixed reboot harness exited zero and
published success evidence with all seven categorical checks true:

- the durable pending enrollment worker was killed without confirmation or
  explicit rollback;
- public SSH loss was observed and the boot identity changed;
- both recovery services proved current-boot success;
- the guest returned to idle unconfirmed state;
- fresh pinned public SSH and SFTP succeeded; and
- the strict preinstall probe accepted the restored state.

The success artifact was independently checked as an owner-controlled regular
mode-`0600` file beneath a mode-`0700` directory. Its exact field set, source
revision, deployable digest and wrapper input digest matched; it contained no
target alias, public address, enrollment key or remote output. The distinct
diagnostic path remained absent. A post-run live check reconfirmed idle state,
both recovery services, pinned SSH, SFTP and the preinstall probe after one
isolated transport retry. The control-plane key inventory then showed no valid
auth keys and one additional invalidated key, confirming single-use
consumption.

This closes the previously failed reboot-recovery acceptance checkpoint, not
execution step `SEC-1788894504951632`. The earlier controller-loss result is
still bound to its earlier main revision. Positive bootstrap with a third
fresh key, observed dual-path handoff, SSH ownership transaction, ordinary
dry-run/deploy, authenticated protocol proof, provider-firewall
promotion/manifest reissue, guarded deletion and authenticated provider
absence remain required.

## Two-phase implementation checkpoint — 2026-09-09

The domain now persists irreversible `rolling_back` and `firewall_restored`
phases. Early recovery restores firewall state without a daemon/runner
capability; late recovery completes owned-identity logout. Confirmation after
rollback begins refuses. Controller, guest RPC, bootstrap-only playbook and
verification-only deploy migration are present but remain under validation.

Observed local evidence (uncommitted working tree):

- Final changed-module run: `python3 -m pytest -q
  tests/unit/test_tailnet_management.py tests/unit/test_bootstrap_tailnet.py
  tests/unit/test_deploy_controller.py` — 194 passed in 153.26 seconds.
- Native nftables exercised fresh snapshot, namespace candidate parsing,
  apply/readback, early restoration and late restoration. Its service calls
  used an explicit fixture: this is kernel firewall evidence, not systemd
  activation or reboot evidence.
- The read-only NETLINK_NETFILTER preflight observed an empty namespace,
  detected a real added table, and observed empty state after exact test-table
  deletion. No table names or rules are fabricated by that preflight.
- A limited unit graph passed with the actual pinned Tailscale 1.102.3 package
  unit, and its old firewall-order negative control reproduced a cycle.
  This limited pass did not include the complete socket activation graph.
- The complete graph including Ubuntu OpenSSH `ssh.socket`, `basic.target`
  and `multi-user.target` FAILED: `ssh.socket -> vpn-tailnet-recover ->
  tailscaled -> basic.target -> sockets.target -> ssh.socket`.

Implementation is paused before changing the SSH activation contract. The
proposed correction gates `ssh.socket` only on early firewall restoration and
keeps `ssh.service` behind late enrollment recovery. This separates a listening
socket from an SSH daemon capable of servicing/authenticating connections;
it must be explicitly reconciled with the design and tested through actual
systemd startup and reboot before deployment. No execution step is complete.
Operator docs, Molecule migration, full gates, hosted CI, staging, live and
protocol/client acceptance remain outstanding. Do not deploy this worktree.

A container-only experiment removed the late worker's ordering/requirement
from `ssh.socket` while keeping `ssh.service` gated. The full vendor graph then
returned 0 with no diagnostics. This proposal is not applied to repository
units. Graph validation must inspect diagnostics as well as exit status:
systemd-analyze can print an ordering cycle and delete a job while returning 0.


## Approved SSH socket separation — 2026-09-09

The operator approved the early-socket/late-service split. Design and
REQ-TFB-RECOVERY now specify that the early worker gates `ssh.socket`, while
only the late worker gates `ssh.service`. Both unit templates and the
regression assertions implement that contract. This supersedes the preceding
pause; it does not supersede the outstanding native/runtime acceptance.

Current local checks: `build-gate -- python3 -m pytest -q
tests/unit/test_tailnet_management.py tests/unit/test_bootstrap_tailnet.py
tests/unit/test_deploy_controller.py tests/unit/test_staging_cleanup_guard.py
tests/unit/test_vultr_staging_cleanup_guard.py` passed 360 tests in 167.30 seconds;
Ansible-lint passes the bootstrap playbook, role tasks and migrated Molecule
inputs with the repository role path. OpenSpec strict validation and taskctl
validation pass. Operator documentation now separates bootstrap from ordinary
deployment and places cleanup ownership before guest writes. Molecule uses
real nftables with an explicitly synthetic Tailnet CLI; its execution remains
pending. No execution step or external evidence category is complete yet.


## Native package and full-graph result — 2026-09-09

An isolated x86_64 VM ran the pinned Debian 13 Molecule image with real systemd,
nftables and the role-installed Tailscale 1.102.3 package. Bootstrap installation
completed with `ok=24 changed=15 unreachable=0 failed=0`. The complete vendor
graph including ssh.socket, ssh.service, basic.target, multi-user.target,
network-pre.target, nftables and tailscaled passed with no diagnostics.
Restoring the old late-socket dependency in the disposable container reproduced
the ordering cycle; restoring current repository units passed again.

The subsequent native recovery exercise did not arm a transaction:
`Firewall.snapshot` refused with `bootstrap-foreign-firewall`. Real tailscaled
startup in `NeedsLogin` created exactly four empty tables: ip/filter, ip/nat,
ip6/filter, ip6/nat. The ruleset contained no chains or rules. Removing only
these test-created empty tables in the isolated container and restarting the
real daemon reproduced the same four tables. The native nftables service was
inactive and disabled before the test. This is a production-package mismatch
in the accepted empty-baseline model, not a reason to weaken foreign-rule checks.

Implementation is paused under the apply workflow before changing the accepted
firewall-state contract. Proposed refinement: preserve and snapshot only those
known chainless/ruleless empty tables as inert baseline objects, retaining
strict refusal for any chain, rule or other foreign table and exact restoration
of the baseline. The preinstall probe, candidate parser/readback and boot replay
would need one coherent classifier plus native regressions. No such matcher
change has been applied. PID1 restart recovery, Molecule, full gates, hosted CI
and external acceptance remain unperformed. No execution step is complete.


## Approved inert baseline — 2026-09-09

The operator approved preserving exactly the four empty daemon tables. The
shared preinstall/adapter classifier and coherent candidate/readback/boot
handling now implement this refinement. Negative tests cover partial and
duplicate sets, table attributes, chains, rules, sets, maps and other tables.
The two changed modules pass 102 tests. Native replay is being rerun; preceding
failure evidence remains valid for the earlier implementation, not acceptance
of this correction. This approval supersedes the preceding pause.

## Native empty-baseline rollback — 2026-09-09

The initial amd64 package run under emulation stopped on a Python segmentation
fault during Ansible module execution. It is failed setup evidence. A separate
ARM64 Ubuntu 24.04 container then installed the real pinned package and both
recovery foundations through their repository playbooks. SSH foundation
installation passed with `ok=10 changed=6 failed=0 unreachable=0`; Tailnet
installation passed with `ok=24 changed=15 failed=0 unreachable=0`.

The first PID1 restart exposed two distinct issues. The initial harness omitted
the prerequisite SSH recovery bundle, leaving `/run/sshd` absent before sshd
policy inspection. With that bundle installed, the unit sandbox changed only
the enumeration order of the IPv4/IPv6 `listenaddress` lines in `sshd -T`.
Raw policy comparison refused rollback despite identical endpoints. A failing
regression reproduced the permutation mismatch; the implementation now
normalizes only those lines, retaining all values, duplicates and other bytes.
Changed Tailnet/controller modules pass 108 tests after this correction.

A fresh container with the complete prerequisite sequence then passed:

- Full vendor systemd graph, including SSH ownership recovery, both Tailnet
  phases, ssh.socket, ssh.service, basic.target and network-pre.target: no
  diagnostics. The old late-socket dependency reproduced the ordering cycle;
  restoring repository units passed again.
- Real nftables snapshot, candidate parse, apply and readback preserving the
  exact four empty daemon tables.
- A durably armed crash point before login followed by container PID1 restart:
  exact original firewall rules, files, modes and service state restored;
  both Tailnet workers reported success; ssh.socket and ssh.service active;
  the unconfirmed transaction was removed.

This is uncommitted ARM64 container evidence for the pre-login crash point.
It does not prove x86_64 hosted execution, real enrolled-identity logout,
provider reboot, fresh external SSH/SFTP, client protocols or staging/live
acceptance. No execution step is complete on this evidence alone.

The same native stack also passed autonomous timer recovery with the real
300-second lease and no subsequent controller RPC: the unexpired transaction
survived timer ticks, then its exact baseline was restored after expiry and
SSH remained active. The isolated test profile was deleted and its absence
checked. This second exercise also stopped before real Tailnet login.

The expanded five-module regression command passed 379 tests in 161.31 seconds.
Two later controller regressions reproduced source changes during external
proof; source and input fences are now rechecked before confirmation or
handoff regeneration. The final Tailnet/controller modules pass 110 tests.
`build-gate -- make validate` passed all four Terraform roots, gitleaks,
Ansible lint (528 files, production profile), and site syntax. Terraform
initialization used existing exact-version local packages with the committed
lockfile read-only after registry downloads timed out; no plan/apply ran.
`make snapshot-update` changed only the two intended recovery-unit goldens;
`make snapshot-check` then matched all 140 templates. The complete `ci-fast`
retry is still in progress, not accepted.

## Preinstallation owned-state parity — 2026-09-09

Boundary reproduction showed that the nonempty preflight previously accepted
a managed header and successful syntax check without reading effective rules.
It now uses the existing canonical fragment parser delivered on SSH stdin,
shared kernel normalization/ownership and service-state validation, and an
isolated network namespace to compare the complete candidate with live rules.
No guest temporary file or installed Python module is needed for this check.
Unsafe parent paths also refuse before file reads. Controller source/input
fences still bind installation, confirmation and regenerated handoff.

The final changed modules pass 118 tests, including canonical acceptance,
foreign table/chain/rule, malformed fragment, unsupported service, standalone
parser loading and refusal before any installation/enrollment RPC. A fresh
ARM64 native suite accepted exact owned rules without changing them, rejected
an added foreign table and rule without modifying either, and again passed
the full dependency graph and exact pre-login PID1 restart restoration. The
profile was deleted and its absence verified. `build-gate -- make validate`
passed again on this implementation.

The full `ci-fast` process began before these final preflight edits; its result
must not be presented as one immutable final-revision gate. The separate final
module/native checks above are observed; final-revision full/hosted gates,
enrolled-identity recovery and external acceptance remain outstanding.

## Resource journal and caller migration — 2026-09-09

The approved resource journal now serializes manifest publication, explicit
state-bound reissue and complete destruction across both provider guards.
UpCloud schema 3 and Vultr schema 2 require a registered current generation;
legacy or copied artifacts cannot acquire authority. Publication and receipt
recovery retain write-ahead intent, exact identities and the original deadlines.

After integrating baseline `12351a4b3683c13aa56a27b433fe945c46f902c2`, the
frozen full gate passed validation but exposed a remaining onboarding caller
that copied the cleanup manifest. The run was deliberately interrupted after
1 failed, 1399 passed and 33 setup errors; this is not a completed CI gate.
An isolated regression reproduced the caller refusal. Onboarding now preserves
and revalidates the registered path instead of copying it; its test fixture
uses an isolated controller home. Negative cases reject a copied manifest and
same-byte inode replacement. The three onboarding/retirement/bootstrap modules
pass 198 tests in 5.11 seconds. Both guards and destroy caller pass 294 tests
in 35.11 seconds. Collection contains 4481 tests, including 4378 unit tests.
The final immutable full gate, hosted revision and external acceptance remain
required. No implementation step or external evidence category is closed.

## Staging installer delegation regression — 2026-09-09

Exact revision `b2262981b6f95599ac36b3fc3fdadd94f2702858` passed hosted CI,
but authorized staging exposed a controller integration gap. The initial
provider Ubuntu image had active/exited `ufw.service` despite inactive UFW;
the specified preflight refused it without changing that state. UUID-bound
cleanup then verified that server and its root storage absent.

A fresh Debian 13 node passed cloud-init, strict public preflight and SSH
recovery installation. Bootstrap then failed before package installation or
enrollment: global transport extra vars redirected the role's localhost source
validator to the VPS. The diagnostic play recap was `ok=3 changed=0 failed=1`.
The enrollment key remained unused and no Tailnet ACL change occurred.

A new real-Ansible regression failed with the same transport precedence bug.
The installer now scopes all pinned transport settings to its private one-node
inventory group, preserving ordinary local delegation without removing any
connection restriction. All 42 bootstrap-module tests pass, including exact
transport round-trip with a spaced key path and refusal of accidental SSH or
sudo in the delegated local task. This is local regression evidence only;
the corrected revision still requires full local/hosted gates and renewed
staging, protocol, recovery and live acceptance. No step is closed.

## Corrected installer and staging shutdown — 2026-09-09

Revision `09e178b0b78e5501cccfc08f96dcfb895f63de7b` passed the frozen
`ci-fast` gate: 4478 pytest cases passed, 4 deselected, 20 subtests; all 55
Bats cases and Rust checks passed. The targeted three-module suite passed
227 tests; `make validate` passed. Hosted CI run `34336075772` completed
with 75 successful jobs. The revision's PR checks were rechecked before
shutdown: 80 successful checks and one neutral result.

The corrected installer installed the real components and enrolled an
ephemeral node. External SSH/SFTP confirmation failed: the temporary exact
TCP/22 policy was confirmed after the controller's bounded pause had ended.
No handoff was produced. Subsequent guest inspection observed transaction
status `idle`, Tailscale `NeedsLogin`, and a passing strict public-socket
preflight. This is active-controller failed-bootstrap recovery evidence,
not positive bootstrap acceptance or a controller-loss/reboot fault test.

The exact temporary Tailnet rule and its two tests were removed, preserving
the original policy. UUID-bound cleanup verified the second server and root
storage absent at 10:05:41 UTC. A final authenticated provider read during
shutdown returned `SERVER_NOT_FOUND` / `STORAGE_NOT_FOUND` for both staging
attempts. No additional enrollment keys or paid resources were created.

The user requested a bounded shutdown. Positive bootstrap, both enrolled
fault tests, normal staging deployment, protocol liveness, provider promotion
and serial live acceptance remain incomplete. All six execution steps remain
open; neither CI nor the cleanup receipt closes these acceptance categories.

## Confirmed identity guard and current access diagnosis — 2026-09-24

Review found that ordinary `tailnet-check.py` accepted any running Tailnet
identity with the expected preferences. It now requires a durable confirmed
receipt for the exact inventory alias, public endpoint, SSH port and approved
sources, and compares the current node ID and both Tailnet addresses to the
confirmed enrollment. The site play checks this before role convergence.
Enrollment now requires the enabled early firewall recovery worker to execute
successfully before arming, alongside the late worker and timer.

The targeted Tailnet/bootstrap/security suite passed 177 tests. `make validate`,
`./taskctl validate` and the complete `build-gate -- make ci-fast` passed;
the latter observed 4489 pytest cases, 4 deselected, 20 subtests,
55 Bats cases, and Rust checks. A local Molecule attempt reached the early
service but could not start it: the arm64 Colima host ran the pinned amd64
image under QEMU, where systemd-journald, DBus and mount units also failed
with `Result=resources` before their executables ran. The scenario container
was destroyed. This is no native systemd or staging acceptance proof.

Fresh read-only consoles show the three permanent VPN VPS still running;
Tailnet last saw them on 23 August. P1 and P2 provider ingress rules permit
public SSH only from saved exact source addresses that exclude this Mac's
current egress; their public SSH timeouts are consistent with those rules.
P0's firewall page returned 401 after the console session expired, so its
current edge rule remains unverified.
No paid staging, ACL, production or task lifecycle mutation was made. All
six SEC execution steps remain open pending fresh authorized runtime proof.

## Refreshed Molecule image and hosted gate — 2026-09-24

The hosted checks for `4d90415aaf5c7f34ac4323215f3c0d7093951fb4`
finished with two underlying failures. Trivy rejected the old pinned Debian 13
Molecule digest with fixable HIGH/CRITICAL packages. The enabled
`observability_control_plane` fixture also failed before convergence: its
`curl` installation used a stale apt index and received HTTP 404 for
`libcurl4t64`. The required-checks aggregate failed accordingly.

An already published immutable Debian 13 image from successful publish run
`35583069099` has digest
`sha256:5c50bf51be9ac3bef7a6795f3e52dfebefa0767bf3c475226222be0fc02a2662`.
A fresh local Trivy 0.74 scan of that exact remote digest returned zero
fixable HIGH/CRITICAL findings. All 47 in-repository references to the former
digest now point to this one; the fixture refreshes apt metadata before its
bounded `curl` install. The affected image-pin, cloud-init and control-plane
modules passed 48 tests. The final `build-gate -- make ci-fast` returned
`ci-fast: OK` with 4489 pytest cases, 4 deselected, 20 subtests, 55 Bats
cases and Rust tests. Final `build-gate -- make validate` passed all provider
roots, gitleaks, production-profile Ansible lint and site syntax. New
exact-SHA hosted checks remain pending. No image was published, and no staging
or permanent resource changed.

## Cold OpenSSH policy inspection regression — 2026-10-02

Fresh controller-loss staging evidence passed on the previous protected source,
including autonomous recovery and new pinned SSH/SFTP proof. The separate
reboot exercise observed SSH loss but never observed SSH returning and produced
only an incomplete diagnostic. Provider-assisted restarts restored inspection
access; they do not satisfy reboot acceptance. Volatile journals did not retain
the failed boot, so its precise failure remains unconfirmed.

A read-only private mount namespace on the actual staging Debian reproduced
`sshd -T` refusing absent `/run/sshd` with exit 255 while `sshd -G` succeeded.
The late recovery worker precedes `ssh.service`, which owns that directory.
Policy inspection now uses syntax-validating `-G`, preserving the full dump and
existing listener-only canonicalization. Preparation no longer creates the
runtime directory. The new Molecule regression requires real cold `-T` refusal
and equality between complete cold `-G`, ordinary policy, and warm `-T` policy.

The targeted Tailnet suite passed 115 tests, including the new regression
observed failing before the fix. The same native policy comparison and invalid-configuration refusal passed on
an existing disposable Linux consumer in a private mount namespace. Local
Molecule did not reach convergence: the pinned image has no arm64 manifest;
its native amd64 hosted scenario remains required. No recovery or protocol
acceptance is credited to these source and namespace checks.

Canonical guarded cleanup verified the staging server and root storage absent
at 16:28:27 UTC, before the user deadline. Independent exact-identity API reads
also returned both absence categories. The cleanup heartbeat was stopped.
The two reopened execution steps remain open: corrected-source hosted gates,
fresh controller-loss and reboot proofs, positive bootstrap, ordinary deploy,
protocol proof, and serial permanent-fleet acceptance are still required.

## Unbound staging retirement — 2026-10-02

Revision `7348cc3427840850408c030f62ecdf5fc96cdb66` completed the real
canonical `retire-unbound-staging-client` and
`retire-unbound-staging-executor` Make targets, both with exit zero.
The original registered cleanup manifest, reserved provider-absence receipt
and current empty provider state authorized the operations; no onboarding
binding or authority was fabricated. The client receipt reports `retired`
and the executor receipt reports `retired-prepared`.

Independent in-memory inspection of the changed encrypted SOPS document
found zero client secret paths and zero Xray cohort references. The owned
prepared profile is absent from both its directory and fresh Colima listing.
Docker context and the directory identities of all five unrelated Colima
profiles are unchanged. Receipts and categorical verification were saved
privately with mode 0600; plaintext secrets were not logged.

The first retirement invocation refused an absent optional Snell root before
writing a journal or modifying ciphertext. Canonical issuance permits this
absence. The correction preserves refusal for configured null or malformed
Snell state; its real SOPS round-trip regression covers configured and absent
roots. The affected five-module suite passed 403 tests; two instruction/count
governance tests passed. The preceding merged revision passed the complete
local gate with 5017 portable pytest cases, four native cases deselected,
20 subtests, 55 Bats cases and Rust checks. A complete final-revision gate and
exact hosted checks remain required.

The staging provider server and root were already verified absent before
the approved deadline. The owned API credentials and temporary Tailnet policy
were retired; the current unfiltered machine inventory contains the prior
eight nodes and no owned staging node. Four one-use auth keys were consumed;
a fifth was not created. No fresh paid resource or permanent-node mutation
was performed. Corrected-source recovery, positive bootstrap, ordinary
staging deployment, four-protocol proof and serial permanent-fleet acceptance
remain open; this retirement does not close an execution step.
