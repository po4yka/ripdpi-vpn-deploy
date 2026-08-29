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
| REQ-ADMIN-MIGRATION | SEC-1787917604306451 | 301 affected planner/core/adapter tests plus pinned Debian 13 and Ubuntu 24.04 packaged-main checks include real OpenSSH full effective parity, custom port, unknown-layout, bounded execution, read-set races and four-file crash boundaries | local source and packaged-main checks passed; complete local, hosted and staging pending |
| REQ-ADMIN-ROLLBACK | SEC-1787917604868749 | Installation/upgrade and earlier fault tests passed; native apply reproduced a readiness contention refusal, so the activation step is reopened pending the corrected positive path | readiness correction and migration/confirm/timeout acceptance pending; guest firewall and real reboot remain pending |
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
PR #117 merged normally as `bdc6b5a9c7f3d47b801341eba5560171ce41b589`.
Its tree exactly matched the final local gate: 1702 unit tests passed with one
existing skip, 55 Bats and 169 Rust tests passed. Exact-main CI 33183588047
passed all 51 jobs; CodeQL 33183587834 passed. This source delivery does not
establish migration acceptance.

### Reopened activation step after native contention refusal

On 2026-08-28, the exact seven installed source files from that main commit
passed actual non-root TCP SSH login and SFTP roundtrip in an isolated native
ARM Ubuntu 24.04/systemd 255.4 container. Prepare succeeded but apply refused.
A separate deterministic diagnostic held the real transaction lock, observed
periodic exit 75, and traced immutable Runtime readiness to its rejection of
that status. One canonical apply then refused with the state still prepared
and bytes/modes of all four SSH configuration files unchanged. Containers and
their volumes were removed with absence confirmed. No product patch or retry
was used to obtain this result.

The implementation step SEC-1787917604868749 is reopened: this safe refusal is
not positive migration/confirmation/timeout proof. Completion now requires
RED/GREEN contention and state-fence regressions, independent review, actual
native SSH/SFTP before and after confirmed migration and timer-driven rollback,
then the full local gate and exact-source hosted checks. Guest reboot, staging
and production remain separate unverified boundaries.

The readiness correction's four existing SSH test modules passed 198 tests in
the primary's independent run. Tests first reproduced transaction contention,
then covered two lock phases, exact state/snapshot revalidation, bounded command
execution and real flock ordering. Independent review found a prior worker
failure could be erased by start and future completion timestamps were accepted;
12 additional cases failed before those fixes and passed afterward. The final
review found no remaining blocking issues in that diff.

Corrected-source native acceptance then passed in one 90.9-second isolated run.
All seven source hashes matched the candidate; bundle generation was
`367aeb25ef8defb6886f7e3ee4ff4fc9068fafd5c6a00c989040d43c4225fd5b`.
Actual lock contention first produced periodic exit 75. One canonical apply
then succeeded, with a fresh completed exit-0 execution observed during that
invocation. A new non-root TCP SSH connection and SFTP roundtrip passed before
local-root fixture confirmation, and the transaction stayed committed. In an
independent second case, a 60-second unconfirmed lease expired and the real
periodic timer restored all four files' bytes, modes, owners and effective SSH
policy without any manual recovery call. Fresh SSH/SFTP passed after rollback.
Five distinct TCP connections and two invocation-bounded execution proofs were
observed; copied source stayed unchanged. Container and volumes were removed,
with absence confirmed. The full local and exact-source hosted gates remain
pending. This is native container engine acceptance, not staging, actual reboot,
remote confirmation-controller or production acceptance; exact second-lock
contention ordering remains unit-test evidence.

Normal baseline convergence still restores the old duplicate authentication
directives, and fresh bootstrap ownership has not yet been aligned. Do not
perform a real-node ownership migration until that separate source change is
delivered. Tailnet configuration, guest/provider network transactions,
staging and serial production acceptance remain unfinished.

The unpublished baseline-convergence slice passed all four affected SSH test
modules together: 301 tests in 14.81 seconds. Tests first exposed schema-one
plans, acceptance of nonterminal historical state, rejection of the real
packaged-main ownership defaults and the missing fourth-write crash boundary.
The resulting schema-two ownership operation
owns `main→10→20→50`; full effective policy is identical after every publish
prefix and reverse rollback suffix, while packaged SFTP, unrelated bytes and
metadata remain unchanged. Baseline owns only main+20, preserves algorithm sets,
supports a verified absent 20 and validates explicit before/after phases.

The current parser accepts only the exact canonical original three-fragment
schema-one ownership receipt in committed or rolled-back state for status and
recovery no-op. `prepare` alone may archive those exact bytes before creating a
distinct schema-two transaction; it never rewrites the historical receipt.
Apply, confirm and rollback categorically refuse schema one, as do
pending/applied/unknown and noncanonical historical states. Frozen/current parser
tests cover committed and rolled-back upgrade, publication interruption/retry,
and frozen-parser downgrade refusal for terminal schema-two ownership and
baseline receipts before pointer, journal, state or activation changes. The
frozen source fixture remains byte-identical; this is source/parser evidence,
not a historical live-node upgrade.

Pinned packaged-main checks passed against planner source
`974371576baf2df810ac38a0758be19c656637b9138fba8d2cb0813c1e17a686`.
The Debian 13 image index was
`sha256:fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e`;
OpenSSH server was `1:10.0p1-7+deb13u4` and the 3424-byte packaged main file
hashed to `f1805313ad346bdb80dff4a560a080edfca9a998f620b64da2a1aba6bcf6782e`.
The Ubuntu 24.04 image index was
`sha256:48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1`;
OpenSSH server was `1:9.6p1-3ubuntu13.18` and the 3517-byte packaged main file
hashed to `64325541513d33ea1d2ccd19c77750d458e67e7967fd2e7ef81d92f0aa2ffe21`.

Both ephemeral amd64 containers installed the distribution package through
the signed APT path, then disconnected their network before the proof. They had
no host mounts. Ubuntu required the normal `/run/sshd` boot precondition because
systemd was not PID 1. Real `sshd -t` and contextual `sshd -T` verified schema
two, exact `main→10→20→50` ownership, all four candidate writes, every publish
prefix and reverse rollback suffix, preserved packaged SFTP and an unchanged
on-disk SSH snapshot. Private evidence was written mode 0600 with SHA256
`8b5b45770e042144c6fc46cf1c4b151cd7797e2c3b627c46bebc09cfe0f7b302`.
The owned container profile stopped successfully and the Docker context stayed
unchanged.

Bootstrap and ordinary-role integration, fresh remote confirmation, complete
local and hosted gates and real connection proof remain required before host
use. Prior PR117 native hashes and acceptance predate this schema-two source
and are not evidence for it.

The schema-two recovery sandbox prerequisite was fixed in source commit
`4869edbc83eada009f036365015bb8f3c08e99a5`. Both exact recovery units retain
`ProtectSystem=strict` but now grant the `/etc/ssh` directory write required by
their transaction's atomic temporary-file publication of both the main config
and drop-ins; the immutable transaction allowlist still rejects every other SSH
path. The two adapter/bundle modules passed 139 tests, configured pre-commit
hooks passed, unit hashes matched independently, and independent review found
no blocker.

A local ARM systemd proof ran those exact unit bytes with only `ExecStart`
replaced by a bounded atomic-operation probe. Both services successfully
replaced the main file and a drop-in inode while preserving bytes and metadata,
removed their temporary drop-in, and were denied writes to `/etc` outside the
exception and to a sibling of the one writable bundle lock. The owned profile
stopped and Docker context was unchanged. The private mode-0600 result hashes to
`a5a4be3196e16221085c2163426bb8f99c396ed5b286ad4d6fec46534a3556af`.
This proves the exact units' mount-namespace semantics only: the Colima guest
does not retain oneshot execution timestamps, and the derived probe does not
prove the real bundle dispatcher, a pending schema-two journal, sshd reload,
reboot ordering, staging or host migration.

The unpublished fresh-bootstrap and baseline-template slice passed 133 focused
tests. It installs a byte-exact stdlib helper through all four provider
templates, accepts only the canonical top-level drop-in include, rejects every
active Match and unexpected fragment, validates the six effective SSH values
with a bounded process-group-cleaning `sshd -T` invocation, and publishes
10→20→50 in a non-weakening order. Fault tests kill the process after each file
fsync, replace and directory fsync; every visible prefix remains safe and a
fresh invocation removes only owned residues and converges. This is process
crash evidence, not three-file power-loss atomicity or reboot evidence. The
four provider server mock suites passed 8, 6, 6 and 6 tests; all 102 rendered
snapshots matched and independent review found no blocking issue.

The exact helper SHA256
`ff856c50c401e797dd7bfc8b79f4f20538a37ff041cc5ab5968ebe0da98d11b3`
then passed real OpenSSH parsing in pinned Debian 13 and Ubuntu 24.04 amd64
containers. The signed distribution package versions were respectively
`1:10.0p1-7+deb13u4` and `1:9.6p1-3ubuntu13.18`. The containers had no host
mounts and were disconnected from Docker networking after package installation.
Both runs proved exact effective port/authentication/X11 values, empty helper
stdout/stderr, preserved packaged main bytes, exact fragment membership and an
inode-and-byte-identical repeat. The mode-0600 private result hashes to
`ff2c5b983149046c189c0e31c360b4c1da76b68883759d181c7f8373976b38e0`;
the owned profile stopped and Docker context remained unchanged. This remains
parser/bootstrap evidence only: cloud-final interruption/reboot, ordinary
baseline transaction wiring, fresh TCP SSH and staging are not proved.

Local source work is authorized. No local test implies staging or live acceptance. Provisioning waits for available approved executor, verified actual cost/credit, exact-resource cleanup and the approved deadline; policy application waits for a fresh separately approved ACL diff. The serial fleet step remains open until observed direct and Tailnet SSH and actual VPN probes all pass.
