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
| `chore:` | Tooling, dependencies (Dependabot uses this automatically). |
| `ci:` | CI workflow changes (`.github/workflows/*`). |
| `build:` | Build-time change (rarely applicable here). |
| `revert:` | Reverts a prior commit. |

`feat!` / `fix!` (or a `BREAKING CHANGE:` trailer) bumps the major version.

## First-time setup

After cloning, install cloud-init first (`cloud-init` package on Ubuntu; use an Ubuntu VM/environment on macOS), then run the repository bootstrap:

```bash
make bootstrap-dev
```

This installs the portable mise-pinned tools serially, hashed Python requirements, pre-commit hooks, and the Rust 1.88.0 MSRV toolchain, then runs the exhaustive CI-parity preflight. Cloud-init remains a manual system dependency and must be available before bootstrap; do not skip its schema gate.

## Local pre-flight

Before `git push`:

```bash
make validate            # gitleaks, terraform fmt + validate, ansible-lint, syntax-check
mise exec -- make check-prereqs CI_PARITY=1
mise exec -- make ci-fast
pre-commit run --all-files
```

## CI gates

Every PR runs the matrix in `.github/workflows/ci.yml` (12+ jobs):

- gitleaks
- terraform fmt + validate (matrix: upcloud / hetzner / vultr)
- cloud-init schema
- ansible-lint + syntax-check
- molecule (matrix: 9 roles)
- shellcheck, secrets-coverage, templates-render
- yamllint
- codeql (Python + Actions)

Plus informational (non-blocking):

- markdown-link-check (when `*.md` changed)
- scorecard (weekly)

See `docs/TESTING.md` for the full coverage matrix and which roles have
justified molecule skips.

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
- Docker / K8s on the data plane — see brain-note rationale.
- Auto-deploy from `main` — operator-driven by design.

PRs in these directions will be closed with a pointer to the rationale.
