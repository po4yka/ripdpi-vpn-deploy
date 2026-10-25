# Repository rules and merge policy

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-10-25

The source of truth is [repository-policy.json](../../.github/repository-policy.json).
The [configuration command](../../scripts/configure-repository.py), exposed through
Make, replaces the classic branch-protection workflow. Do not recreate a classic rule:
GitHub enforces it alongside rulesets and it can block the intended CI bypass.

## Protection layers

| Ruleset | Target | Requirements | Bypass |
|---|---|---|---|
| `main-integrity` | `main` | PR, squash only, linear history, resolved conversations, no force push or deletion | None |
| `main-ci` | `main` | Three required contexts and an up-to-date branch | Repository owner, PR only |
| `release-tags` | `vpnd-v*` tags | No updates or deletion | None |

The owner can explicitly bypass pending or failed CI from a PR. This exception
does not bypass integrity rules or permit direct pushes. Other users have no CI
bypass. Required approvals remain zero for this single-maintainer repository.
Code Owner approval and approval of the last push remain disabled. If another
maintainer joins, update the review policy before relying on independent review.

## Required status checks

| Workflow | Context | Expected source |
|---|---|---|
| `ci.yml` | `required checks` | GitHub Actions |
| `codeql.yml` | `codeql (python)` | GitHub Actions |
| `codeql.yml` | `codeql (actions)` | GitHub Actions |

The CI aggregate requires every selected job to pass. It rejects missing jobs,
failed selection, malformed plans, failures, cancellations, and unexpected skips.
Only planned, unselected jobs can be skipped. It includes secret checks,
validators, task contracts, PR-title validation, and protective workflows.
Do not add those child jobs as duplicate branch requirements. Update the JSON
configuration if an aggregate or CodeQL context is renamed. Keep the GitHub
Actions source binding; an identically named result from another app is not enough.

The PR title must use Conventional Commit syntax, for example
`ci: improve repository policy`. CI rechecks titles on PR edits. Dependabot uses
the `chore` prefix. Squash merging uses the PR title and body, and GitHub removes
merged head branches. Auto-merge remains available when requirements pass.

The aggregate enforces the existing behavior of its child checks. It does not
strengthen their contracts: `reproducible-build` still permits example placeholder
pins and treats Xray rebuild mismatches as advisory. Costly PR jobs follow the
complete dependency plan; unknown paths and shared configuration select full CI.
See [CI dependency selection](../reference/testing.md#ci-dependency-selection).

## Preview and apply

Use existing authenticated GitHub CLI access with repository administration
permission. The configuration command prints only public policy, never tokens.
It does not read the fleet, inventory, SOPS files, or local operator kit.

```bash
make repository-policy-plan
```

Review the printed operations and exact repository. With authorization to apply
that plan:

```bash
make repository-policy-apply
make repository-policy-plan
```

The second plan must be `[]`. The command verifies repository identity, owner
identity, admin access, and the absence of classic `main` protection before any
write. It preserves unrelated rulesets and refuses ambiguous managed names or
inherited rulesets. Before the first migration, disable the obsolete `branch-protection` workflow
with `gh workflow disable branch-protection.yml`. This prevents a manual run
from restoring classic protection while its source removal is in review.
The command creates integrity protection before converting the old
`main` ruleset to `main-ci`; no rule deletion is needed. It reads back every
managed setting after apply and fails if any drift remains.

Policy changes run from an authorized operator session with GitHub CLI access.
No administration token is stored in Actions for this feature. The default
`GITHUB_TOKEN` does not have repository administration permission. CI validates
the checked-in policy and its behavior at the API boundary; it does not modify
repository settings. Remove any obsolete protection credential separately only
when its owner has confirmed that no other consumer uses it.

## Releases and recovery

Future published releases are immutable. Release tag creation remains open to
the existing release workflow; tag updates and deletion are blocked. Build and
upload every asset while the release is a draft, then publish it. The current
release chain follows that order and refuses uploads to a published release.
Immutability does not retrofit earlier releases.

GitHub configuration writes are not atomic. If one fails, do not claim success:
run a new preview against actual remote state, inspect it, and apply only the
remaining authorized operations. To restore a previous ruleset or merge setting,
review that policy change and apply it explicitly. The command refuses to disable
release immutability. A published immutable asset correction requires a new version.

The optional `scorecard` and external link checks remain informational. They do
not block a merge due to transient external service failures.
