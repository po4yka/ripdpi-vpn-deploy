---
task_id: TST-1787497001212692
change: tst-1787497001212692-verification-truthfulness
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: no Terraform surface changed; playbook gating verified via live-inventory runs
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule covers scenario changes
live: required
live_evidence: null
client: not_applicable
client_evidence: no client emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-VERIFY-HOSTCLASS-GATING | TST-1787496118906453 | Local source-task verify predicates and credential-free smoke subscription/all-disabled regressions passed | conditional/task-slice PASS; combined full and live acceptance pending |
| REQ-DRIFT-FULL-IDENTITY | TST-1787496118906639 | Complete production playbook on local synthetic manifests: matching identity passes; wrong revision with matching digest and wrong digest fail | local source verified; live acceptance pending |
| REQ-VERIFY-DEPLOYED-LISTENERS | TST-1787496118906882 | Local production-task regressions for configured Hysteria and conditional fallback ports passed; required full gates and live verify remain open | local source verified; acceptance pending |
| REQ-IDEMPOTENCE-WHERE-DECLARED | TST-1787496118906321 | full-stack idempotence phase output showing second-run changed=0 | pending |
| REQ-SCENARIO-RUNS-ROLE | TST-1787496118906595 | rewritten amneziawg converge executing role tasks | pending |
| REQ-TESTING-DOCS-REALITY | TST-1787496118906567 | row-by-row matrix audit vs molecule.yml sequences | pending |
| REQ-SINGLE-SSH-LISTENER | TST-1787496118907256 | verify assertion output on socket-activated image | pending |

## Gates

- Local: touched molecule scenarios, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA including both full-stack variants.
- Live: one verify + source-drift cycle against live inventory.

## Published scenario prerequisite slice — 2026-08-29

- Scope: only the dependency path and listener-contract inputs needed by step `TST-1787496118906321`, in `codex/high-published-prerequisites-20260829` from `fc3acc6`.
- Tests-first RED: the entire existing dependency module reported **2 failed, 2 passed in 0.52s**. The published dependency path resolved to a different checkout's requirements, and the provider listener contract was absent (`/private/tmp/ripdpi-published-prerequisites-red.log`).
- Before choosing the contract, an installed-Ansible regression loaded all 28 actual static site roles with literal `when: false`. Its private localhost inventory uses local connection/no escalation, a closed environment and the shared synthetic secrets. Only the exact manifest pre-task and a debug observation succeed (`ok=2 changed=0`); roles, handlers, services and host connections are not exercised. It confirms `xray_fallback_port` is undefined and the effective fallback is zero, with five active listeners matching the declared inputs.
- The first version of that observation test compared inactive records too and failed because static role defaults add disabled records. The corrected comparison follows the production validator's enabled-listener boundary, while preserving separate defined/value fallback assertions. Its final hermetic run, with an owned empty collections path rather than ambient Ansible collections, passed **1 test in 1.67s** (`/private/tmp/ripdpi-published-static-defaults-hermetic.log`); the initial test-shape failure is not product RED evidence.
- The source fix points the dependency at this checkout's `requirements.yml` from the documented `ansible/` CWD and supplies the five-listener provider snapshot. No port, toggle, role or sequence changes. The existing module's final hermetic run passed **5 tests in 1.56s** (`/private/tmp/ripdpi-published-prerequisites-hermetic.log`), including actual template/validator comparison and rejection of a changed runtime port.
- These are local input/default-visibility checks, not a full site run or Molecule proof. Step `TST-1787496118906321`, full Molecule idempotence, hosted checks and live acceptance remain open; no Docker, provider or live-host operation was performed.

## Listener-only local regression evidence (2026-08-28)

- Scope: step `TST-1787496118906882` in `codex/high-verify-listeners-20260828`, based on `7da8b74`. No SSH, watchdog, liveness, backup, source-drift, toggle-default, Makefile, or Molecule changes are included. The task and its full/live acceptance remain blocked; this entry does not complete the other host-class gating step.
- Tests execute the unmodified selected shell tasks and their `when` expressions through real Ansible on localhost. Only external `ss` output is supplied by an executable in a private temporary directory. They do not run the full verify playbook, contact hosts, inspect real listeners, or prove protocol traffic.
- RED/GREEN: configured Hysteria port cases first failed twice (custom port rejected; unrelated UDP/443 accepted), then both passed; four fallback cases first failed because the assertions were absent, then passed; subscription-only cases initially produced one Hysteria failure and two skips, then all three passed.
- `mise exec -- python3 -m pytest -q tests/unit/test_listener_contract.py`: **39 passed in 16.34s**, including 21 new cases. Coverage includes matching/wrong ports, fallback enablement, Xray explicit cohorts, zero/absent/same-as-primary fallback ports, disabled transports, subscription-only hosts, and existing runtime default ports.
- `mise exec -- ansible-lint ansible/playbooks/verify.yml`: production profile passed, one file; `mise exec -- yamllint ansible/playbooks/verify.yml` and `git diff --check` passed.
- Local execution logs: `/private/tmp/ripdpi-listeners-hysteria-{red,green}.log`, `/private/tmp/ripdpi-listeners-fallback-{red,green}.log`, `/private/tmp/ripdpi-listeners-subscription-{red,green}.log`, `/private/tmp/ripdpi-listeners-entire.log`, and `/private/tmp/ripdpi-listeners-lint.log`. These are local run evidence, not hosted CI or live acceptance.
- Independent parent review matched the fallback conditions against the canonical runtime templates and found no blocking issue. Its separate full listener-module run passed **39 tests in 18.27s** (`/private/tmp/ripdpi-listeners-independent.log`). Step `TST-1787496118906882` is complete for this implementation; the other nine execution steps and overall acceptance remain open.
- Collection-only checks observed **1521 repository tests** and **1468 tests under tests/unit/**; TESTING.md records these observed counts without a full-suite success claim.
- Outstanding: combined full gates, exact-SHA hosted checks, and the authorized live verification required above. No commit, push, or host operation was performed by this slice.

## Exact source revision regression evidence (2026-08-28)

- Step `TST-1787496118906639`: the complete unchanged production playbook is executed through installed Ansible against a temporary local manifest. Only inventory connection, manifest path and expected synthetic identity are supplied by the fixture; no SSH or live manifest is used.
- Before the fix, a valid but different 40-character revision with the expected digest incorrectly returned success: one regression failed and two controls passed. Adding revision equality makes all three cases pass; the full existing source-identity module passed **7 tests in 5.83s**. The matching identity remains accepted, and a mismatched digest remains rejected.
- This deliberately requires the exact deployed source commit even when a documentation-only commit leaves the deployable digest unchanged. Existing live nodes may fail this stricter gate until a reviewed deploy; no manifest was rewritten and no deployment was performed.
- Collection-only checks found **1615 repository tests / 1562 unit tests**. Full combined checks, exact hosted checks and live acceptance remain required; this implementation does not close the portfolio task.

## Bounded smoke host-class slice — 2026-08-28

- Step `TST-1787496118906712` shares the smoke playbook change with `OPS-1787496118906646`, based on main `2009b6f694e326fa1f6d99333da497544b115cdd`; `verify.yml` and every other execution step are unchanged by this slice.
- `test_smoke_skips_all_transport_access_without_credentials` runs the actual source task graph with subscription-only and all-disabled inputs and zero transport credentials. Both pass, invoke no temporary systemd/network executable, create no smoke workdir and report skipped transports. The required secrets-file entrypoint assertion remains in place.
- Final `mise exec -- python3 -m pytest tests/unit/test_smoke_test_cleanup.py -q`: **57 passed in 314.81 seconds**, including the two host-class cases and all supported-protocol positives/failure paths. Production Ansible lint, strict OpenSpec validation and task validation passed; original configuration/ports were preserved, and probe commands gained only `--noproxy ''` to prevent inherited proxy bypass. See the OPS verification slice for the observed tests-first cleanup and truthful-probe regressions.
- These are local Ansible control-flow/temporary-file tests plus eight real-curl dynamic-loopback proxy-bypass regressions, not Linux systemd, deployed transport, hosted CI or live subscription-host proof. No full gate was run in this bounded lane, and the overall verification task and remaining acceptance stay open.
- Only implementation step `TST-1787496118906712` is marked complete through taskctl after the approved local checks; parent-task state and every other execution step are unchanged by this slice.

- Parent final review: `make validate` exited zero after backend-disabled, lockfile-readonly initialization of all four Terraform roots; production Ansible lint and syntax passed. Parent independently passed 19 lifecycle cases and two source-derived real-curl NO_PROXY cases. Configured pre-commit passed after synthetic fixture labels were changed to the repository-approved STUB convention; no scanner rule or acceptance assertion was weakened. Full combined checks and live evidence remain open.

## Verification host-class regression evidence (2026-08-28)

- Scope: step `TST-1787496118906453`, branch `codex/high-verify-hostclass-20260828`, based on `a823ed23f82180f69e597a1dc776e5a4afe0711e`. The source change adds only the existing subscription-only predicate to eleven transport tasks. Parsed-source comparison confirmed every other task field, original toggle default, command, assertion and shared check is unchanged.
- Tests-first: after correcting a temporary-executable newline setup error (not counted as behavior evidence), all eleven subscription-only cases failed because the real source task executed instead of skipping; four enabled/disabled/shared-hardening controls already passed. After the source fix, the entire existing module passed: `mise exec -- python3 -m pytest tests/unit/test_listener_contract.py -q` reported **54 passed in 52.65 seconds**. The fifteen new cases include each transport task, all-enabled execution, all-disabled nonexecution, and shared bootstrap/nft/SSH/sysctl execution with a failing-sysctl control.
- Tests reuse the existing real-Ansible task runner and preserve task conditions, command arguments and assertions. Temporary executables supply external inspection results; only the absolute Snell binary and bootstrap-marker path are relocated into the fixture. P1 DNS is an external fixture boundary. This proves conditional/task-slice behavior, not execution of the full verify playbook, deployed services, DNS, SSH or sysctls on a live host.
- Production Ansible lint passed with zero failures/warnings; yamllint, strict OpenSpec validation, task validation (27 tasks, 130 steps), parsed-source predicate-only comparison and `git diff --check` passed. Logs: `/private/tmp/ripdpi-verify-hostclass-{red,green,lint}.log`; the separate fixture-setup log is not RED evidence.
- No full gate, Molecule, hosted CI or live acceptance was run in this lane. The primary agent later marked only implementation step TST-1787496118906453 complete through taskctl and regenerated board/counts; parent-task and live acceptance remain open.

- Independent parent review passed all **15 new cases in 21.72 seconds** and confirmed predicate-only source changes. Collection-only checks observed **1630 repository tests / 1577 unit tests**; these counts do not assert a full-suite pass.

## Combined main integration check — 2026-08-28

- The combined source tree `70c8ed645126c3b4c6c75458cad02f41c2664868` includes main `bdc6b5a9c7f3d47b801341eba5560171ce41b589` and the allowlist, restore-point, source-parity, smoke and host-class fixes. Full `make check` passed validation, Terraform/policy, parsers and MSRV, then stopped with **1810 unit tests passed, one existing placeholder skipped and one failed in 1181.35 seconds**. The failure was an older static hostname test assuming `when` was a string, although the added subscription guard correctly makes it a list; Rust release and Bats were not reached.
- The two hostname assertions now require the complete original toggle condition as a list member. No runtime source, timeout or acceptance predicate changed. The complete listener and Xray modules passed **72 tests in 54.52 seconds**. A repeated full gate and exact hosted checks remain required before integration; the parent task remains open.
