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
| REQ-VERIFY-HOSTCLASS-GATING | TST-1787496118906453 | verify + smoke against subscription-only profile inventory | pending |
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
