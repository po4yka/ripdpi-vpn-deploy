---
name: conventional-commit
description: Conventional Commits for vpn-deploy — drives release-please versioning. Defines allowed types, repo-specific scopes, and forbidden trailers. Use when authoring any commit message in this repo. vpn-deploy project variant.
---

# Conventional Commits (vpn-deploy)

release-please reads commit messages on `main` and produces the version bump + CHANGELOG.
Get the format right or the changelog gets corrupted.

## Format

```
<type>(<scope>): <imperative subject under 70 chars>

<optional body explaining WHY, wrapped at 72 cols>

<optional footer: BREAKING CHANGE: ..., Refs #123, etc.>
```

## Types

| Type | Bump | Use for |
|---|---|---|
| `feat` | minor | New role, new vpnd subcommand, new provider, new cohort |
| `fix` | patch | Bug fix; failing molecule scenario; runtime regression |
| `docs` | none | README, CLAUDE.md, AGENTS.md, docs/** |
| `refactor` | none | Code change with no behaviour change |
| `perf` | patch | Throughput / cold-start / build time |
| `test` | none | Adding or fixing tests only |
| `build` | none | Makefile, CI workflows, dependency pins, tooling |
| `ci` | none | `.github/workflows/**`, pre-commit config |
| `chore` | none | Housekeeping that doesn't fit elsewhere |
| `revert` | varies | Mirrors the reverted commit's type |

`feat!` or `BREAKING CHANGE:` footer triggers a **major** bump. Use sparingly; this repo's
breaking surface is the operator interface (Makefile targets, vpnd CLI, group_vars keys,
secrets schema).

## Repo scopes

Pick from this list; one scope per commit:

- Protocols: `xray`, `hysteria`, `amneziawg`, `naive`, `nginx-xhttp`, `cdn-front`
- Infrastructure: `baseline`, `firewall`, `policy-ratelimit`, `geodata`, `warp-outbound`,
  `honeypot`, `watchdog`, `backup`, `subscription-host`, `monitoring`
- Layers: `terraform`, `ansible`, `vpnd`, `make`, `scripts`, `secrets`, `tests`, `docs`
- Cross-cutting: `release`, `ci`

`molecule` is the test-runner scope when adding scenarios. `agents` for AGENTS.md /
CLAUDE.md changes.

## Recent examples from this repo

```
docs(readme): add Mermaid diagrams for layers and cohort→transport map
docs(agents): add AGENTS.md cross-tool counterpart to CLAUDE.md
docs(readme): tighten Deploy profiles to match house voice
docs(readme): surface cohort group_vars for partial deploys
fix(molecule): drop invalid select('length') from xray verify fail_msg
```

## Hard rules

- **No `Co-Authored-By:` trailers.** Per global user policy and root project `CLAUDE.md`.
- **No mention of Claude, Claude Code, or Anthropic** anywhere in the message.
- **No emoji** in subject or body. (Project-wide rule: "No emoji in code, logs, or documentation.")
- **Imperative mood**: "add", "fix", "drop" — not "added", "fixes", "dropping".
- **Subject under 70 chars**, no trailing period.
- **Body explains WHY** — the "what" is in the diff.
- **One logical change per commit.** Split rebase rather than ship a mixed bag.

## Pre-commit gates

Local validation lives in `make validate` — ansible-lint, gitleaks, terraform fmt + validate.
For Terraform or Ansible changes, run `make validate` **before** the commit. Hooks will
catch you on the way out otherwise.

## When in doubt

```
chore(repo): <subject>
```

is always safe (no bump, no changelog entry). Better than a `feat:` that triggers a wrong
version bump.

## See also

- Root `CLAUDE.md` "Versioning" section
- `.github/release-please-config.json` and `.github/release-please-manifest.json`
- `.github/workflows/release-please.yml`
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
