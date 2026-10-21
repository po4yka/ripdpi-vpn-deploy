---
task_id: OPS-1792512787218003
change: ops-1792512787218003-close-deployment-readiness-follow-up-findings
commit_sha: 86d76430707a0e6febedaf4c7c8c19351b224d36
local: passed
local_evidence: Each new regression fails on its parent commit and passes after its fix. make check passed every step through ansible syntax, including tf-test, tf-policy-verify, shellcheck, the template render check and snapshots; liveness-profile-check did not run because the workstation has no Xray binary. With real sops and sing-box on PATH, test-unit ran 9282 passed and 2 failed (test_disposable_promotion, identical on base 25ed8d5e). vpnd-lint, vpnd-test (338) and vpnd-parity-check passed at fd174a03; bats passed. ansible-lint passed for site.yml and the amneziawg role. An independent review found one critical defect (top-level fact names under inject_facts_as_vars false) and three lower ones; all were fixed and the fixes re-reviewed. Molecule and native Linux lanes were not run locally. Local gaps (liveness-profile-check without Xray, Molecule, native lanes, and the 2 base-identical test_disposable_promotion failures) passed in PR and main CI.
remote_ci: passed
remote_ci_evidence: Source PR #347 CI run 39543684353 passed all 92 jobs on 5807bec413e1fdc26f96bb4f3846fb25cd7e9663 and run 39549714130 passed on c1c5828bcfcc50c45b49ff335c461f0bb3d8c806, including the 9 required contexts, pytest groups 1-4 with make liveness-profile-check on real pinned Xray and sing-box, all Molecule default, failure and full-stack scenarios, native runtime integration, native transport and four-transport acceptance, terraform test and conftest for all providers, and vpnd test and package lanes on Linux and macOS. Main CI run 39557145005 attempt 1 passed all 92 jobs on rebase merge 86d76430707a0e6febedaf4c7c8c19351b224d36, whose tree matches the PR head. Molecule amneziawg downloaded, checksum-verified and extracted Go 1.27.1 on vpn-awg-debian13, and its idempotence run reported the toolchain tasks unchanged.
dry_run: not_applicable
dry_run_evidence: Source repair only; no deployment controller run against private inventory.
staging: not_applicable
staging_evidence: No staging rollout is included.
live: not_applicable
live_evidence: No provider, host, credential or production operation is included.
client: not_applicable
client_evidence: No client payload, bundle or recipient contract changes.
artifact: passed
artifact_evidence: nginx 1.24 nginx -t accepts the redirect server directives. Debian 13 and Ubuntu 24.04 distro go.env both set GOTOOLCHAIN=auto, Ubuntu ships Go 1.22.2 and the pinned amneziawg-go go.mod requires go 1.22.3. The Go 1.27.1 linux amd64 and arm64 digests match the go.dev release listing.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRF-REVIEW | OPS-1792514260026468 | test_green_apply_and_deploy_wait_for_a_typed_review; vpnd review, terminal and signal regressions | passed |
| REQ-DRF-BLUEENV | OPS-1792514260874788 | test_blue_env_selection.py (21 real Make runs); watcher promote command assertion | passed |
| REQ-DRF-HOSTENV | OPS-1792514261666762 | test_selection_outside_env_refuses_before_secrets_and_transport (10 cases) | passed |
| REQ-DRF-DESTROY | OPS-1792514262478677 | test_destroy_refuses_without_a_quoted_hostname_to_confirm; test_interactive_destroy_removes_its_saved_plan_on_every_exit | passed |
| REQ-DRF-RUNBOOK | OPS-1792514263378823 | test_redeploy_recipe_* (19 cases running the printed blocks) | passed |
| REQ-DRF-GOTOOL | OPS-1792514264261067 | test_amneziawg_go_toolchain.py (repository Ansible config); test_amneziawg_host_resolver.py | passed |
| REQ-DRF-IMAGE | OPS-1792514265195751 | make tf-test with new rejection runs; test_host_os_admission.py (repository Ansible config) | passed |
| REQ-DRF-BEARERLOG | OPS-1792514266159002 | test_nginx_xhttp_bearer_logs.py; snapshot; nginx -t | passed |
| All | OPS-1792514267045582 | Local gates above; PR #347 CI run 39543684353 (Molecule, native lanes, liveness parser check) | passed |
