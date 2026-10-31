## Context

One active branch ruleset combines integrity and CI. The classic-protection workflow and runbook still describe admin enforcement. Release publication already uses drafts.

## Goals / Non-Goals

- Goal: implement the seven approved repository improvements with a narrow owner CI exception.
- Non-goal: fleet deployment, VPN secret changes, new credentials, or automatic merges.

## Decisions

- Store API-shaped rules and merge settings in one JSON configuration. Use the public numeric owner identity and verify it against the selected repository before mutation.
- Remove the obsolete administrative workflow. Use local authenticated operator access, without an administration token in Actions.
- Use a stdlib Python script with the authenticated `gh api` boundary. Default to a plan; require `--apply` for writes. Read before each run and verify after writes. Preserve unrelated rulesets and refuse classic protection.
- Create integrity protection before changing the existing `main` ruleset into `main-ci`. Do not delete a ruleset during migration.
- Require the complete CI aggregate plus both CodeQL contexts, bound to the existing GitHub Actions integration.
- Keep title validation inside read-only PR CI. Handle title-edit events and make its result part of the aggregate. Never use privileged PR execution.
- Keep release tag creation open to the current release workflow. Reject updates and deletion with no bypass actors. Enable immutable future releases only after local tests and a reviewed remote plan.
- Add dependency ecosystems without changing package versions or lockfiles.

## Contracts and ownership

- Primary owns `.github/`, the policy script, its tests, matching CI tests, CONTRIBUTING, and relevant runbooks.
- No Terraform, Ansible, SOPS, or vpnd runtime contract changes.
- No parallel writers; shared task files are updated only through taskctl.

## Risks / Trade-offs

- GitHub writes are not transactional. Install integrity protection first; fail on error and re-plan from actual remote state before retry.
- Immutable published assets cannot be replaced. Recovery uses a new version. Draft retries remain supported.
- Ruleset edits affect every PR. Read back the exact bypass actor, mode, check sources, tag rules, and merge settings.
- Whole-PR CI on a title edit costs runner time but avoids stale or independently replaceable aggregate results.

## Migration Plan

Validate planning, implement and test offline, run the required local gate, review the diff, then apply the exact reviewed policy to the authorized repository. Read it back and confirm an empty second plan. Commit and open a PR; do not merge it. A ruleset rollback requires an explicit policy edit and apply. Published immutable releases require a new version.
