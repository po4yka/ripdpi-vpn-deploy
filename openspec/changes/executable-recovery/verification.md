---
task_id: OPS-1792678016174902
change: executable-recovery
commit_sha: 69bbf62f930de88a04106d43161dbc0dca511930
local: passed
local_evidence: Full make check completed with exit 0 on b0ae6b495f9372dbbe429d487967f383e6693c21; 10152 Python tests and 45 subtests, 387 vpnd tests and 10 documentation tests passed. Its tree e2ae4adcb2afa7daf38096f48105615f41e111c9 is identical to the recorded main commit. 253 Linux native cases were deselected on macOS and are covered separately by hosted Linux acceptance.
remote_ci: passed
remote_ci_evidence: Exact-head PR run 39923816763 passed all required checks, including all seven native jobs; 99 checks succeeded and one scan result was neutral. Main run 39934072990 for 69bbf62f930de88a04106d43161dbc0dca511930 passed all required checks and all seven native jobs with confirmed cleanup; 98 checks succeeded and the release dispatch was correctly skipped.
dry_run: required
dry_run_evidence: Source workflow and refusal tests passed; a real canonical full-profile dry-run against the admitted replacement remains unobserved.
staging: not_applicable
staging_evidence: No additional distinct staging rehearsal is required; the live category owns the outstanding positive external acceptance.
live: required
live_evidence: Actual provider provisioning, authenticated guest ownership, full deployment and restored service remain unobserved; isolated provider and SSH models are not external acceptance.
client: required
client_evidence: Local recovery-to-migration acceptance integration passed; real replacement-path device continuity and physical-device acceptance remain unobserved and required.
artifact: passed
artifact_evidence: Recovery tests exercised actual private snapshots, registry publication, durable interrupted-operation journals and encrypted migration artifacts; no deployed recovery receipt is claimed.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RECOVERY-PLAN | OPS-1792678266947663 | `test_recovery_io.py` and `test_recovery_runtime.py` passed manifest admission and durable local execution | passed |
| REQ-RECOVERY-PROVISION | OPS-1792678267794418 | Local provider reconciliation and lost-response models passed; actual admitted provider provisioning remains unobserved | partial |
| REQ-RECOVERY-MANAGEMENT | OPS-1792678268575909 | Positive source workflow and guest models passed; actual authenticated bootstrap and SSH ownership remain unobserved | partial |
| REQ-RECOVERY-RESUME | OPS-1792678266947663 | `test_recovery_io.py` actual process death and `test_recovery_runtime.py` reconciliation passed | passed |
| REQ-RECOVERY-CONVERGE | OPS-1792678268575909 | Source convergence, promotion and lost-acknowledgement regressions passed; real full-profile dry-run, deployment and fresh acceptance remain unobserved | partial |
| REQ-RECOVERY-DELIVERY | OPS-1792678268575909 | Actual encrypted migration and local publisher integration passed; replacement-device and stable-origin external acceptance remain unobserved | partial |

Step OPS-1792678269304356 owns source integration and exact-main CI. The task
remains in review until the retained provider, guest and device requirements pass.

## Implementation checks observed

- Recovery admission/provider/runtime/promotion/guest and restore-contract suites:
  105 passed. These include actual process death with durable intent, reviewed
  provider-state reconciliation models, input races, real private snapshot and
  registry publication, exact sentinel receipt reuse, and the actual encrypted
  migration/local publisher path from incomplete to accepted device evidence.
- Ruff for changed recovery Python modules/tests, Shellcheck for `restore.sh`,
  and `git diff --check` passed.
- Provider, guest SSH and sentinel networking in these tests are isolated models
  or mocked boundaries; no live cloud/host/client acceptance is claimed.
- Shared disposable onboarding, promotion proof, baseline and deploy-controller
  suites: 295 passed; two environmental failures passed exact reruns (installed
  pinned SOPS under an isolated HOME, and the existing 25-second selection timeout).
- Full repository checks, independent review and protected PR CI passed on the
  integrated source tree, including exact-main CI. None of these source
  results closes the outstanding external recovery requirements.

## Integrated source evidence

[PR 369](https://github.com/po4yka/ripdpi-vpn-deploy/pull/369) integrated the
features. [PR 370](https://github.com/po4yka/ripdpi-vpn-deploy/pull/370),
[PR 372](https://github.com/po4yka/ripdpi-vpn-deploy/pull/372) and
[PR 374](https://github.com/po4yka/ripdpi-vpn-deploy/pull/374) corrected native
readiness, Snell listener allocation, recovery scheduling and AWG control
readiness. The source main commit is
`69bbf62f930de88a04106d43161dbc0dca511930`.
Runtime admission and denial assertions remain strict; recovery retains all
21 cases in three disjoint groups and the original 2400-second deadline.
Earlier failed or cancelled runs do not count as acceptance evidence.

The full `build-gate -- mise exec -- make check` passed on
`b0ae6b495f9372dbbe429d487967f383e6693c21`: 10,152 Python tests and 45 subtests,
387 vpnd tests and 10 documentation tests. Its Git tree
`e2ae4adcb2afa7daf38096f48105615f41e111c9` is identical to the source main commit
and hosted PR merge. No separate local run on the literal merge SHA is claimed.
The macOS run deselected 253 Linux native cases; it is not Linux runtime evidence.

[Exact-head PR CI](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39923816763)
passed all required checks: 99 successful checks and one neutral scan result,
including the required aggregate and all seven native jobs. Core passed
33 cases; recovery passed all 21 unique cases in disjoint groups of 6, 8 and 7,
with internal cleanup confirmed and no residual differences. Both runtime
partitions passed 9 cases. Integration passed 184 cases, including restored AWG
access, all Snell combinations and interrupted lifecycle scenarios, followed by
10 endpoint, 4 delivery and 169 topology cases. All owned environment cleanup
steps passed. Runtime and recovery overlap is not additional unique coverage.

Independent source review found no remaining actionable defect. AWG readiness
has 29 new portable regressions. Actual pinned Linux ARM64 binaries reproduced
the old worker's premature configuration with a diagnostic startup delay; the
corrected worker passed real HTTPS traffic, fresh handshakes and cleanup with
both that delay and the unchanged daemon, making one configuration write.
The failed earlier main run retained no setup stderr, so its precise failing
command is unknown; the reproduced startup defect is independently confirmed.

[Exact-main CI](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39934072990)
passed on the recorded source commit: 98 successful checks and one expected
release-dispatch skip, including the required aggregate, all seven native jobs
and owned cleanup. The restored AWG access regression, 184 integration cases,
10 endpoint cases, 4 delivery cases and 169 topology cases passed. Core, recovery
and both runtime partitions passed the same complete case sets described above.
These isolated checks do not establish a real fleet rollout or physical-device
acceptance.
