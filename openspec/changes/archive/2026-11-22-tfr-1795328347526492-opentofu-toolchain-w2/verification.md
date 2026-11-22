---
task_id: TFR-1795328347526492
change: tfr-1795328347526492-opentofu-toolchain-w2
commit_sha: 7f93291ff3ec860d3d6717fa75a3eb2ce665a33f
local: passed
local_evidence: "make -k check -j 4 under mise (OpenTofu 1.13.9): tofu test 91/61/80/55 passed for upcloud/hetzner/vultr/scaleway, vpnd 551 passed, bats 92 passed, unit 12741 passed with 2 load-sensitive failures that pass when rerun alone; task-check passed after board regeneration. Baseline comparison on origin/main showed the same 5 local-only native failures."
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy pull request 682 merged as 7f93291f: 79 checks success, 3 planned skips, 1 neutral."
dry_run: not_applicable
dry_run_evidence: No Ansible input changes.
staging: not_applicable
staging_evidence: The production read-only plan is the live gate; staging roots use the same code.
live: passed
live_evidence: "2026-11-22 OpenTofu 1.13.9 read-only plans (-lock=false, refresh on, no saved plan, state bytes unchanged) at the state owner revision c0bacceb for p0-upcloud, observer-upcloud, p1-scaleway and p2-vultr: all four No changes. Current p0/p1/observer tfvars were rebuilt from the recorded 2026-11-11 SSH-source rotation and the observer state restored from its 2026-11-15 encrypted backup with scripts/restore-tf-state.sh; private receipt receipts/opentofu-w2-20261122/final-read-only-plans.json. Current main code also shows no resource changes for p2-vultr."
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TOFU-PIN | TFR-1795328401186589 | `tests/unit/test_workflow_terraform_version.py`; stub-only `PATH` script tests; pin test and stub-only PATH tests green in CI | passed |
| REQ-TOFU-LOCKS | TFR-1795328413365163 | `tofu init` on a clean checkout in CI; tofu init -lockfile=readonly in CI and locally | passed |
| REQ-TOFU-CHECKS | TFR-1795328425689060 | `make tf-test`, `make tf-policy-verify`, `make tf-conftest`; tofu test 91/61/80/55, tf-policy-verify, tf-conftest | passed |
| REQ-TOFU-STATE-COMPAT | TFR-1795328448740009 | private kit receipt receipts/opentofu-w2-20261122/final-read-only-plans.json; four production roots No changes (2026-11-22) | passed |
