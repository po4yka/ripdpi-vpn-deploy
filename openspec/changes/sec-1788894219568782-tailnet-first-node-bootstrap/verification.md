---
task_id: SEC-1788894219568782
change: sec-1788894219568782-tailnet-first-node-bootstrap
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
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

Implementation is in progress in the dedicated worktree; no implementation
commit or external acceptance exists yet. The inspected baseline is
`3a7a48220e89e99e4d2f96125941eecfcf281479`; it is not an implementation SHA.
Its existing deploy module tests passed (105 tests), and direct local context
validation refused a public-only fresh-node configuration. These observations
establish the dependency defect, not bootstrap acceptance. All implementation
and external evidence below remain required.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TFB-INPUT | SEC-1788894502237285 | New controller boundary tests; pinned public connection and zero-write negative cases | Required |
| REQ-TFB-BOUNDARY | SEC-1788894503320732 | Firewall candidate validation and real nftables source isolation; preserved sshd/DNS/routes | Required |
| REQ-TFB-RECOVERY | SEC-1788894502776578 | Domain fault injection plus native two-phase boot ordering, interruption, timer and controller-loss recovery | Required |
| REQ-TFB-PROOF | SEC-1788894503869488 | Fresh public/Tailnet SSH and SFTP with matching host key and observed socket identities | Required |
| REQ-TFB-DEPLOY | SEC-1788894503869488 | Deploy tests reject enrollment keys and absent management; normal VPN proof still runs | Required |
| REQ-UPF-STAGING | SEC-1788894504408980 | Cleanup guard tests and exact-state manifests before bootstrap and after firewall transitions | Required |
| REQ-TFB-ACCEPTANCE | SEC-1788894504951632 | Exact-SHA local/hosted gates, positive staging, recovery, deployment, protocol proof, provider absence | Required |

## Required evidence scopes

- Local: complete changed-module tests, affected Molecule scenarios, native
  Linux systemd/nftables recovery, `build-gate -- make ci-fast`, and
  `build-gate -- make validate`; record exact tested SHA and command results.
- Remote CI: all required hosted checks on the exact implementation revision,
  with current run URLs and conclusions; queued or skipped work is not proof.
- Dry-run: ordinary deploy with actual observed bootstrap socket contexts and
  a valid exact-node promotion configuration; no capability consumed.
- Staging: one authorized disposable clean node; positive bootstrap, interrupted
  enrollment, reboot recovery, public access after rollback, repeated positive
  bootstrap, ordinary deploy, provider firewall promotion and acceptance.
- Live: agreed serial one-node checks after staging and a valid operator
  window, preserving public recovery. Lack of current authority blocks this
  category and must not be relabeled as a local-only success.
- Client: real authenticated required VPN profiles with exact target binding;
  successful enrollment or on-node status does not satisfy this category.
- Artifact: private mode-0600 observed-context handoff, unchanged host identity,
  cleanup manifests with unchanged resource identities/deadlines, redacted
  guarded-delete receipts, and authenticated exact-resource provider absence.

Record failures and rollbacks with the same scope precision as successes.
Never copy secrets, raw provider state, or sensitive capability material into
this document. No requirement may close on refusal-only implementation.

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
