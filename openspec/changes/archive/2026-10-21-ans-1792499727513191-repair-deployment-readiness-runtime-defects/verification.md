---
task_id: ANS-1792499727513191
change: ans-1792499727513191-repair-deployment-readiness-runtime-defects
commit_sha: 86d76430707a0e6febedaf4c7c8c19351b224d36
local: passed
local_evidence: Each new regression fails on the parent and passes after its fix. make check passed every step through ansible syntax, including the template render check (165), snapshots, terraform tests and shellcheck. liveness-profile-check did not run: the workstation has no Xray binary. test-unit ran 9131 passed; all 76 failures were SOPS/sing-box mise-shim cases, and 74 passed with real binaries; the other 2 fail identically on base 25ed8d5e. vpnd-lint, vpnd-test (322), vpnd-parity-check and bats passed. Independent review found one native fixture defect, fixed in 6ec346d3. AmneziaWG Molecule fails at the same consumer task on base and head in local Docker; firewall Molecule has no arm64 image here. Local gaps (liveness-profile-check without Xray, Molecule, native lanes, and the 2 base-identical test_disposable_promotion failures) passed in PR and main CI.
remote_ci: passed
remote_ci_evidence: Source PR #347 CI run 39543684353 passed all 92 jobs on 5807bec413e1fdc26f96bb4f3846fb25cd7e9663 and run 39549714130 passed on c1c5828bcfcc50c45b49ff335c461f0bb3d8c806, including the 9 required contexts, pytest groups 1-4 with make liveness-profile-check on real pinned Xray and sing-box, all Molecule default, failure and full-stack scenarios, native runtime integration, native transport and four-transport acceptance, terraform test and conftest for all providers, and vpnd test and package lanes on Linux and macOS. Main CI run 39557145005 attempt 1 passed all 92 jobs on rebase merge 86d76430707a0e6febedaf4c7c8c19351b224d36, whose tree matches the PR head. Molecule amneziawg, firewall, xray and watchdog passed in CI.
dry_run: not_applicable
dry_run_evidence: Source repair only; no deployment controller or private inventory operation.
staging: not_applicable
staging_evidence: No staging rollout is included.
live: not_applicable
live_evidence: No provider, host, credential or production operation is included.
client: not_applicable
client_evidence: No client payload, bundle or recipient contract changes.
artifact: passed
artifact_evidence: nft -c accepts the rendered ruleset on Debian 13 nftables 1.1.3. A Debian 13 apt simulation shows resolvconf removes systemd-resolved and libnss-resolve.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRR-ROTATE | ANS-1792500035125072 | test_every_protected_profile_rotates_xray_through_guarded_recovery | passed |
| REQ-DRR-RESOLVER | ANS-1792500035840245 | test_amneziawg_host_resolver.py; Debian 13 apt simulation | passed |
| REQ-DRR-AWGDEST | ANS-1792500036500839 | test_awg_forwarding_refuses_canonical_private_destinations; nft -c | passed |
| REQ-DRR-WATCHDOG | ANS-1792500037164561 | test_invalid_nginx/xray_config regressions (57 watchdog tests) | passed |
| REQ-DRR-HYSTERIA | ANS-1792500037843465 | test_hysteria_version_pin.py (6 cases, real Ansible) | passed |
| All | ANS-1792500038523299 | Local gates above; PR #347 CI run 39543684353 (Molecule, native lanes, liveness parser check) | passed |
