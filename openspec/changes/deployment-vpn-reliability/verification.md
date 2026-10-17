---
task_id: OPS-1792263187492070
change: deployment-vpn-reliability
commit_sha: b001d337fab20a35f3c8aec38e8b348eed8a8c72
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

## First hosted run and scoped repairs

Hosted run 39063347083 at head 0d1875d425a36275ed9fc00f7ecc3f83bda79251
found two fresh-host integration failures and a target-unit property mismatch.
The inline reader now preserves the lookup file's actual final newline. Its
regression uses actual Ansible rendering. Ingress recovery skips a stop only
when nginx is still absent. The fixed AWG target alone normalizes its missing
service PID property; missing service PID remains a refusal.

The reader and ingress suites passed 83 tests. The target boundary reproduced
three failures before its fix; the target/consumer/profile bundle then passed
59 tests. Hosted native acceptance must be repeated for these repairs.

The complete local make check passed task validation, all four provider
validations, Gitleaks, production Ansible lint, syntax, Go helper tests and
action/workflow checks. It stopped at the bounded cloud-init Docker fallback
with exit 125 after timeout. Docker inspection also timed out. Cleanup of the
exact owned container vpn-cloud-init-schema-8576-ccab3b56d8add0a5 is unconfirmed.
No local full-gate or native pass is claimed.

The same hosted run reports new HIGH findings in the unchanged pinned Debian13
CI image. This security gate is retained. Its artifact refresh is a separate
validation dependency; no suppression or production rollout is authorized.

## Consolidated hosted-failure repair proof

The complete ten-file repair command passed 274 tests in 56.58 seconds. It
includes actual Ansible rendering, fresh and accepted AWG check-mode execution,
unit-state parsing, all six stale source-contract repairs and the original
privacy guards. The only warning comes from Python ipaddress handling of an
intentional invalid boolean CIDR fixture. Structured review of the final repair
bundle reported no actionable P0 finding; TruffleHog also passed.

The owner explicitly authorized the CI-only Debian13 image refresh and coherent
pin update. Publisher run 39064420607 uses main source
082eea068adecfc705c149540b18c980244f113c with unchanged publisher and Dockerfile.
Its new digest remains unaccepted until the current security scan passes.

## Scanned CI image receipt

Publisher 39064420607 passed at source
082eea068adecfc705c149540b18c980244f113c. It produced and scanned immutable
index digest sha256:b3f2db18b8a6f53891196f7a166e36896f9200357d453a0129be09fa9bf94e84.
Fresh Trivy 0.70.0 database and SARIF analysis 1973697119 report zero findings.
Registry manifest digests were verified; the nine parent layers are unchanged.
Only the package-upgrade layer changed. The previously published alternative
has the same vulnerable package versions and was not adopted.

All 47 references in 45 Molecule files and their pin guard now select this
verified digest. The pin tests passed both cases; all 45 YAML files passed lint.
Byte comparison confirms only exact digest changes in that owned file set.
The next complete PR run must verify role and native compatibility before merge.

## Fresh retained firewall parent

Hosted run 39065219318 at source 4c07a768a4255d0ed196e7d72db90fa38b8fb5a1
confirmed that first full-stack publication can reach the strict transaction
before its shared runtime parent exists. The role now admits existing ancestry
and creates only an absent parent before publication. Existing trusted metadata
is preserved; unsafe ancestry still refuses. Actual Ansible preparation with
the real file transaction reproduced two failing cases before the fix. All four
new cases and the complete 23-test consumer suite pass after the fix, including
check mode and symlink refusal. Targeted production Ansible lint passed.
The hosted AWG Molecule scenario passed convergence, idempotence, all 31 verify
assertions and destruction in that run. Both image scans passed with fresh
databases and zero SARIF findings. A complete run of the final source is still
required before merge.

## Repeated AWG retirement

At source dd126d8f33c67a77c316bc14f058073624f93ba0, hosted run 39066025063
passed all 7,815 unit tests and 45 subtests, the AWG Molecule scenario and its
cleanup, and all 19 infrastructure and image jobs. Both full-stack scenarios
passed convergence. Their second application exposed a real retirement no-op
defect: cleanup pruned every absent-path claim, so identical fixed-path
retirement bypassed the retained transaction fast path. The final source must
retain bounded canonical absence authority and keep dynamic retirement cleanup,
then pass full-stack idempotence and the complete exact-source gates.

The AWG-specific repair retains only the three canonical absence claims.
Dynamic configuration retirement remains bounded and pruned. The regression
failed on a second runtime preparation before the fix and now forbids runtime
publication and lifecycle changes while checking firewall acceptance and
readiness. The consumer/profile suites passed 54 tests; generic transaction,
unit-state and reload suites passed 84 tests. Exact older cleanup journals
resume; a changed retirement subset refuses. The generic transaction and
Ansible changed-condition are unchanged.

## Native expected-render boundary

The native core job in run 39066025063 passed initial AWG role activation and
the exact-pair wire/warm-adoption case. Three previous-runtime cases then failed
an expected-configuration byte assertion. Cleanup was confirmed with no
remaining differences. A bounded actual Ansible comparison identified exactly
two extra newline bytes from the fixture renderer's block-trimming setting;
this was not a production configuration mismatch or a trailing-newline change.
The fixture expectation must match Ansible block trimming and retain an exact
portable lookup regression before native failure recovery is accepted.

## Complete first native run

Run 39066025063 finished all six native groups. Both transport partitions passed
12 cases in total with successful retirement. Both recovery plans passed all
15 cases with confirmed cleanup and no differences. Core passed 24 cases and
failed the three expected-render assertions described above; cleanup passed.
Runtime integration observed 337 passing tests and one stale warm-AWG fixture
lookup for the removed notification task. Its final AWG dual-stack Make goal
did not execute after that failure. That stale fixture must move to the complete
publisher without removing process, hardening, unit-adoption or no-op assertions.
No cleanup receipt is claimed for the failed pre-activation fixture setup.

The warm fixture now starts through the actual role and replays its current
complete publication task for changed binary and custom unit candidates.
It retains ELF/hash/PID and process-hardening checks, exact configuration bytes,
unit-only UMask adoption, and unchanged convergence. A complete accepted
generation can replace identical file inodes; inode stability applies to the
no-op, while rollback retains its separate exact-inode requirement. The custom
unit candidate does not claim that a full role run would retain fixture-only
settings. Local collection and a portable Ansible render comparison pass; native
execution remains a required hosted check.

## Warm startup diagnostic boundary

Run 39070390257 at source 6534e9f9c638b3ec66bb390ce3de2cf10b5c6c8a passed
7,819 unit tests and 45 subtests, both full-stack idempotence/verify/destroy
cycles, AWG Molecule and all infrastructure/image gates. Core and both recovery
plans passed all 44 cases with confirmed cleanup and no differences. Both
transport partitions passed all 12 cases with successful retirement. Native
integration observed 337 passing tests, then refused initial warm-fixture
publication; the last AWG dual-stack target did not run. The internal cause is
not established by empty stdout. Safe failure metadata and an early warm case
are required to distinguish fixture authority and service startup conditions.
The complete runtime suite and all gates remain required; raw journal, private
configuration and key output remain prohibited. Workflow lint passed for the
early test step.

Diagnostic leak regressions and the actual Ansible renderer comparison passed
11 tests. They reject unknown or duplicate properties, non-ASCII/negative/large
exit values, exception/timeout command strings, raw journal and parent-error
paths. CI selection and protective workflow coverage passed 68 tests; actionlint,
Zizmor and all four Zizmor gate regressions passed. No native acceptance is
claimed from these portable checks.
