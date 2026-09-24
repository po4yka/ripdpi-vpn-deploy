---
name: conventional-commit
description: Commit message format for this repo, where release-please derives versions from Conventional Commits. Use when writing a commit message or choosing a commit type, scope, or breaking-change marker. Not for PR descriptions or OpenSpec/task documents.
---

# Conventional Commits (vpn-deploy)

release-please reads commit subjects on `main` to pick the version bump and write `CHANGELOG.md`. A wrong type means a wrong release, so choose it deliberately.

```
<type>(<scope>): <imperative subject, under 70 chars, no trailing period>

<optional body: why the change was made; the diff shows what>

<optional footer: BREAKING CHANGE: ..., Closes <TASK-ID>>
```

## Type and release effect

`.github/release-please-config.json` defines which types are visible. Visible types produce a release; hidden ones never do.

| Type | Release effect | Use for |
|---|---|---|
| `feat` | minor | New role, transport profile, `vpnd` subcommand, provider, AWG cohort, operator capability |
| `fix` | patch | Bug fix in a role, template, script, or doc |
| `perf` | patch | Throughput, cold-start, or build-time improvement only |
| `docs` | patch | Documentation, including `CLAUDE.md`/`AGENTS.md` knowledge-layer changes |
| `test` | patch | Molecule scenarios, pytest, bats, validators |
| `refactor` | patch | Restructure with no behaviour change |
| `revert` | patch | Reverts a prior commit |
| `chore` / `ci` / `build` | none (hidden) | Tooling, task-board bookkeeping, dependencies; `.github/workflows/**`; Makefile/toolchain |

`feat!`/`fix!` or a `BREAKING CHANGE:` footer bumps the major version. The breaking surface here is the operator interface: Make targets, `vpnd` CLI flags, `group_vars` keys, the secrets schema, and Terraform output keys.

## Scope

Name the area touched, singular: a role directory (`xray`, `nginx-xhttp`, `amneziawg`), a layer (`ansible`, `terraform`, `vpnd`, `scripts`, `secrets`, `tests`, `ci`), or an established subsystem scope (`tasks`, `observability`, `liveness`, `deps`, `agents`). Omit the scope rather than inventing a vague one.

## Rules

- No `Co-Authored-By:` trailers and no mention of AI assistants or their vendors in the message (see `AGENTS.md`). The commit-msg hook installed by `make install-hooks` rejects the trailer.
- Imperative mood (`add`, `fix`, `drop`), no emoji.
- One logical change per commit; split unrelated work.
- Never edit `CHANGELOG.md` or the `# x-release-please-version` line in `vpnd/Cargo.toml` by hand.

Release mechanics (release PR, tags, binary handoff) are in `docs/RELEASE-PLEASE.md`.
