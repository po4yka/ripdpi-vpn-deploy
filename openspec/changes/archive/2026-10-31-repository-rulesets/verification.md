---
task_id: CIC-1792911952227614
change: repository-rulesets
commit_sha: bdde127d49c620987ed1146113a5b180613d72de
local: passed
local_evidence: Targeted policy, title, dependency, aggregate, and CI selection checks passed. The full build-gated make -k -j 4 check ran all targets; it initially reported the ambient sing-box version mismatch, 24 portable failures, and one vpnd failure. With the pinned sing-box 1.14.3 and two workers, 16 failed portable cases and the vpnd case passed. After the owner authorized stopping a pre-existing orphan pytest Xray fixture on port 18181, the remaining eight cases passed. The original run also passed 10378 portable cases, 45 subtests, 453 vpnd cases, and every other gate component. No assertion, timeout, or source implementation changed between that run and its focused reruns. No full-gate exit-zero is claimed; the make -k component rerun rule applies. Actionlint, Zizmor, YAML lint, OpenSpec, task validation, docs links, and commit hooks passed.
remote_ci: passed
remote_ci_evidence: "Pull request 396 was squash-merged as bdde127d49c620987ed1146113a5b180613d72de on 2026-10-25; the main push run 40174238688 on that exact commit succeeded with every job and the required-checks aggregate green, including PR title, task-contract and the protective-workflow tests."
dry_run: not_applicable
dry_run_evidence: No infrastructure deployment.
staging: not_applicable
staging_evidence: No infrastructure deployment.
live: passed
live_evidence: The authenticated configuration command applied and read back all five reviewed operations on 2026-10-25. Active rulesets are main-ci 25812581, main-integrity 25813558, and release-tags 25813559. The only CI bypass is the owner User actor in pull_request mode; integrity and tag bypass lists are empty. Immutable releases, squash-only PR-title commits, and branch deletion are enabled. The old branch-protection workflow 274140908 is disabled_manually. A second Make policy preview returned an empty JSON list.
client: not_applicable
client_evidence: No client behavior change.
artifact: passed
artifact_evidence: The checked-in JSON policy matches live readback, and generated references and documentation links passed. PR 396 contains the source changes; no merge or new release was performed.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RPOL-LAYERS | CIC-1792912060113090 | Policy regression tests and authenticated readback of all three rulesets | passed |
| REQ-RPOL-APPLY | CIC-1792912060113090 | Migration, refusal, partial-failure, and idempotence tests; live second plan is empty | passed |
| REQ-RPOL-RELEASE | CIC-1792912060113090 | Tag update/deletion rules and immutable-release API readback; existing draft publication order retained | passed |
| REQ-RPOL-MERGE | CIC-1792912060113090 | Merge-setting readback, PR title tests, actual PR title check success, aggregate failure tests | passed |
| REQ-RPOL-DEPS | CIC-1792912060113090 | Nine ecosystem/directory pairs, cooldown/grouping/prefix contract tests, YAML and Zizmor validation | passed |

## Scope

Source behavior is verified at the recorded implementation revision. This evidence update does not change executable behavior. Final hosted CI is pending, so the task remains in review and is not closed or archived. Future Dependabot runs use the new configuration after the PR is merged. Live settings were applied separately under the owner's explicit request.
