---
name: repo-task-board
description: Use when creating, updating, triaging, or completing repository tasks stored as Obsidian Tasks Markdown lines with #task, #status/*, #repo/RIPDPI-VPN-DEPLOY, and #area/* tags. Use for docs/tasks/*.md, Kanban board maintenance, backlog grooming, and agent-ready implementation planning. Mirrored from the RIPDPI client repo on 2026-05-22 by the `ripdpi-improvements` skill; lifecycle conventions and canonical schema match the RIPDPI version verbatim except for the `#repo/` tag and the `area:` enum.
---

# Repository Task Board — RIPDPI-VPN-DEPLOY

This repository uses Obsidian Tasks-compatible Markdown checkboxes as the canonical task system. The infrastructure was mirrored from the RIPDPI client repo on 2026-05-22 to maintain uniform task surfaces across both repos.

## Canonical task line

```md
- [ ] #task <imperative task title> #repo/RIPDPI-VPN-DEPLOY #area/<area> #status/<status> <priority>
```

## Allowed statuses

- `#status/backlog`
- `#status/todo`
- `#status/doing`
- `#status/review`
- `#status/blocked`
- `#status/done`
- `#status/dropped`

## Priority markers

- `🔺` critical  ·  `⏫` high  ·  `🔼` medium  ·  `🔽` low

## Allowed areas

- `ansible` — Ansible roles, group_vars, playbooks
- `terraform` — Terraform providers, modules, shared cloud-init contract
- `vpnd` — vpnd Rust CLI code under `vpnd/src/`
- `xray-config` — Xray server config templates and pin (`ansible/roles/xray/defaults/main.yml`, `docs/XRAY-RELEASE-LINE.md`)
- `ci` — GitHub Actions workflows under `.github/workflows/`
- `sbom` — `sbom/` output, `scripts/emit-sbom.py`, Trivy config
- `scripts` — Operator tooling under `scripts/`
- `secrets` — Secrets schema, `secrets/prod.secrets.example.yaml`, `scripts/validate-secrets.py`
- `docs` — Architecture docs, ADRs, runbooks, GOAL-* specs
- `epic` — Strategic epic (parent of multiple tasks)

## Canonical files

- `docs/tasks/issues/<slug>.md` — **source of truth** — one note per task/epic (YAML frontmatter + canonical `- [ ]` line + spec)
- `docs/tasks/active.md` — query view for `#status/doing` and `#status/review`
- `docs/tasks/backlog.md` — query view for `#status/backlog`
- `docs/tasks/blocked.md` — query view for `#status/blocked`
- `docs/tasks/epics.md` — query view for `#area/epic`
- `docs/tasks/dashboard.md` — Obsidian Tasks query hub
- `docs/tasks/board.md` — Kanban board (visual layer; source of truth is `issues/`)

## Per-task notes

Each task or epic lives in `docs/tasks/issues/<slug>.md`. This is the source of truth.

```yaml
---
title: Imperative task title
type: task            # task | epic
status: doing         # backlog | todo | doing | review | blocked | done | dropped
area: ansible         # ansible | terraform | vpnd | xray-config | ci | sbom |
                      # scripts | secrets | docs | epic
priority: high        # critical | high | medium | low
owner: Role name
parent: epic-slug     # slug of parent epic, or null
blocks: []            # list of task slugs this task blocks
blocked_by: []        # list of task slugs blocking this task
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Epic notes (`type: epic`) use `#area/epic` on the canonical line and include `## Goal / ## Why now / ## Key decisions / ## Scope / ## Ship definition` sections. Child tasks reference their parent via `parent: <epic-slug>`.

Tasks created by the `ripdpi-improvements` skill MAY include two extension fields not in the base schema:

- `source_wiki_pages:` — list of wikilinks to the censorship-bypass vault pages that motivated the task.
- `linked_task:` — relative path to a sibling task file in the other repo (for cross-repo proposals where both client and server work is required).

Lifecycle: create via Templater (or by the `ripdpi-improvements` skill) → update `status:` + `#status/*` tag on transition → delete file on close (git history is the audit trail). Do NOT add task lines to `docs/tasks/active.md`, `docs/tasks/backlog.md`, `docs/tasks/blocked.md`, or `docs/tasks/epics.md` — those are query-only views.

## Rules

1. Preserve valid Obsidian Tasks syntax.
2. Never create duplicate task lines for the same work.
3. Prefer editing the existing `issues/<slug>.md` note over creating a new one.
4. Keep task titles imperative and implementation-oriented.
5. Exactly one `#status/*` tag per task; remove the previous one when transitioning.
6. Add `#blocked` alongside `#status/blocked`; add a blocking reason in the body.
7. When completing: change `[ ]` to `[x]`, set `#status/done`, add `✅ YYYY-MM-DD`, then delete the file.
8. The vpn-deploy CHANGELOG.md is release-please managed — do NOT edit it by hand; tasks must use Conventional Commits in PRs so release-please picks them up.
9. Do not change unrelated prose, code, or other sections.

## Task creation workflow

1. Search `docs/tasks/issues/` for similar tasks (the slug should be self-explanatory).
2. If a similar task exists, update it instead of duplicating.
3. Create a new file `docs/tasks/issues/<slug>.md` with the canonical frontmatter + task line + body sections.
4. Tasks created by `ripdpi-improvements` follow this schema with the two extension fields above.

## Implementation workflow

1. Find candidate: `#task #repo/RIPDPI-VPN-DEPLOY #status/todo` or `#status/backlog`, no `#blocked`.
2. Update `status: doing` in frontmatter and `#status/doing` in the canonical line. Update `updated:`.
3. Implement, run tests per vpn-deploy CLAUDE.md verification rules (`make ci-fast`, role-specific molecule scenario, etc.).
4. Update `status: review` and `#status/review`.
5. Add a `## Work log` section to the note: changed files, test run, remaining risk.
6. Mark `#status/done` only when all acceptance checks pass, then delete the file.

## Cross-repo coordination

Tasks with `linked_task:` set have a sibling in the RIPDPI Android client repo (`~/GitRep/RIPDPI/docs/tasks/issues/<slug>.md`). When closing such a task:

1. Update both files simultaneously when status transitions.
2. Do not close one side without verifying the other has shipped or is explicitly out-of-scope.
3. If the sibling task is dropped, drop this one too (or convert to standalone with a body note explaining why).
