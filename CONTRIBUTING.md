# Contributing

## Conventional Commits

Subjects follow [Conventional Commits](https://www.conventionalcommits.org/).
release-please reads them on every push to `main` to populate `CHANGELOG.md`
and tag releases.

| Prefix | When |
|---|---|
| `feat:` | New role, transport profile, script, runbook, or operator capability. |
| `fix:` | Bug fix in a role, template, script, or doc. |
| `docs:` | Documentation only — no code or config change. |
| `test:` | Molecule scenarios, validators, smoke tests. |
| `refactor:` | Code restructure with no behaviour change. |
| `perf:` | Performance-only change. |
| `chore:` | Tooling and dependency updates, including Renovate PRs. |
| `ci:` | CI workflow changes (`.github/workflows/*`). |
| `build:` | Build-time change (rarely applicable here). |
| `revert:` | Reverts a prior commit. |

`feat!` / `fix!` (or a `BREAKING CHANGE:` trailer) bumps the major version.

## First-time setup

After cloning, run this once to wire up the commit-time and commit-message
hooks:

```bash
make install-hooks
```

This installs the commit-time checks for shellcheck, secrets-coverage,
templates-render, placeholder-scan, gitleaks, terraform fmt, and ansible-lint,
plus the Conventional Commit message check. It does not install a push hook.

## Local pre-flight

Before opening a PR, run the canonical local gate:

```bash
make check
```

`make check` combines `validate` and the credential-free, portable `ci-fast`
bundle. Missing local tools fail closed. It intentionally excludes Molecule
containers, GitHub-native security services, and credentialed deploy jobs;
`docs/TESTING.md` records those local and remote boundaries. When an Ansible
role changes, also run its targeted scenario with
`make molecule-test ROLE=<name>`.

## CI gates

`.github/workflows/ci.yml` owns the required PR workflow. Its `required checks`
aggregator fails unless every required job succeeds.

`docs/TESTING.md` owns the human-readable coverage matrix, including default
Molecule scenarios, non-default scenarios, CI-only services, and
local-versus-remote boundaries. When CI coverage changes, update the workflow
and its canonical testing row together; `tests/unit/test_governance_counts.py`
checks that relationship.

See `docs/TESTING.md` for the complete matrix and per-role test coverage.

## Adding a new role / template / script

Each artefact type has a checklist in `docs/TESTING.md`. The short
versions:

- **New role** → toggle in `group_vars/all.yml`, schema in
  `secrets/prod.secrets.example.yaml`, molecule scenario or justified
  skip in `docs/TESTING.md`.
- **New template** → variables must resolve from secrets / group_vars /
  defaults; the validators enforce this at PR time.
- **New script** → top-of-file usage block, `bash -n` clean, shellcheck
  clean, listed in the Makefile if operator-facing.

## Reviews and merge

- `CODEOWNERS` enumerates reviewers (currently single-operator).
- Branch protection requires every CI gate to pass before merge — see
  `docs/BRANCH-PROTECTION.md` for the required-status-checks list and how
  the operator applies it.
- Squash-merge is preferred for clean release-please history.

## Versioning

release-please derives the version bump from Conventional Commits subjects
(see the table above). In practice:

| Change type | Bump |
|---|---|
| New role, new vpnd subcommand, new provider, new AWG cohort | **minor** — use `feat:` |
| Bug fix in a role, template, script, or doc | **patch** — use `fix:` |
| Runbook update, knowledge-layer addition (CLAUDE.md), snapshot refresh after intentional template change | **patch** — use `docs:` or `fix:` |
| Breaking API / secrets-schema / output-schema change | **major** — use `feat!:` or add `BREAKING CHANGE:` trailer |

`CHANGELOG.md` is generated automatically; do not edit it by hand.

## Knowledge layer

If your PR touches `ansible/roles/<X>/`, `terraform/providers/<X>/`,
`scripts/`, or `vpnd/src/`, also touch the corresponding `CLAUDE.md`
(Design decisions / Done well / Pitfalls). The CI warn-gate
(`claude-md-touch.yml`) surfaces omissions but does not block merge.

Step-by-step recipes for the four most common contribution types (new role,
new provider, new vpnd subcommand, new AWG cohort) are in the root
`CLAUDE.md` under "Change recipes".

## What not to PR

- `Cloudflare CDN as RU baseline` — see `docs/CDN-DECISION.md` ADR.
- A web admin panel (Marzban / Remnawave / 3x-ui) — architectural
  invariant.
- Calendar-based credential auto-rotation — rotation must be event-driven.
- Docker / K8s on the data plane — nodes are disposable and Ansible plus
  systemd own runtime state; no container orchestrator is part of the data plane.
- Auto-deploy from `main` — operator-driven by design.

PRs in these directions will be closed with a pointer to the rationale.
