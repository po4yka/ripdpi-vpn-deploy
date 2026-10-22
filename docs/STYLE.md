# Documentation style guide

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-10-21

This page defines how documentation in this repository is organised, named
and written. `tests/unit/test_docs_index.py` enforces the checkable rules.

## Tree

`docs/` follows the four Diátaxis types plus three supporting folders:

| Folder | Type | Reader need | Example |
|---|---|---|---|
| `tutorials/` | tutorial | learn by doing, start to finish | `tutorials/quickstart.md` |
| `how-to/` | how-to | complete one task against real infrastructure | `how-to/deploy.md` |
| `reference/` | reference | look up facts, tables, contracts | `reference/secrets.md` |
| `explanation/` | explanation | understand why the system is shaped this way | `explanation/threat-model.md` |
| `decisions/` | decision | read an accepted architecture decision record | `decisions/0001-cdn-not-filtered-path-baseline.md` |
| `research/` | research | read dated findings that are not normative | `research/android-client.md` |
| `archive/` | archive | read a historical audit or note kept for provenance | `archive/control-drift-audit-2026-07.md` |

`docs/tasks/` (portfolio), `docs/demo/` (recipient page demo) and
`docs/measurements/` (measurement templates and reports) keep their own
contracts and are outside this tree.

Placement test: a page that is mostly numbered steps against live
infrastructure is a how-to; a page that is mostly tables or contracts is
reference; a page that argues a choice and carries an acceptance status is
a decision; a page with a date in its name or a "historical snapshot"
banner is research or archive. A page that mixes types gets split, with the
how-to part keeping the shortest path to the commands.

## Index

`docs/README.md` lists every page under the tree with one line of purpose
and its tier. A page that is not in the index does not exist for readers;
the index test fails on an unlisted page.

## Status line

The first line after the H1 of every page is a status line:

```markdown
> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-10-21
```

- `Status` is one of `Current`, `Snapshot (YYYY-MM-DD)`, `Research`,
  `Archived`, or `Superseded by` followed by a Markdown link to the
  successor page.
- `Type` matches the folder.
- `Tier` is `CORE`, `TACTICAL`, `RESEARCH` or `—`, taken from
  [the tiering decision](decisions/0002-role-and-doc-tiering.md). Pages the
  decision does not classify use `—`.
- `Reviewed` is optional and records the last full read-through.

## Naming

- File names are lower-case kebab-case: `how-to/add-fallback.md`.
- Decision records are numbered: `decisions/NNNN-short-title.md`. Numbers
  are never reused. A superseded decision keeps its file and gains
  `Superseded by` in its status line.
- Dates appear in file names only under `research/` and `archive/`.
- No carrier, ISP, geographic, operator or censorship-apparatus labels in
  file names, headings, table cells, diagram labels or comments. This is a
  repository hard rule (see `AGENTS.md`). Describe the adversary by observed
  behaviour and name cohorts by technical signature.

| Avoid | Write |
|---|---|
| a country or region name as a qualifier | `filtered network`, `filtered-path baseline`, `filtered vantage` |
| a censorship-apparatus or regulator name | `active-probing DPI`, `policy enforcement point`, `flow classifier`, `the filter` |
| a carrier or ISP name | the cohort's technical signature, or `the access network` |
| `<region>-direct`, `geoip:<cc>` as labels | `domestic-direct`, `geoip-split`, `direct policy path` |

Pages under `archive/` keep their historical body text, including old slugs,
because they are provenance; their file names and headings still follow this
rule and the index test checks them.

Behavioural descriptions stay precise: SNI inspection, TLS-in-TLS detection,
active probing of suspected servers, UDP throttling, per-IP dual-role flow
classification.

## Runbook template

Runbooks are the how-to pages whose main procedure changes live infrastructure
or credentials: `deploy`, `rollback`, `rotate`, `restore`, `incident`,
`add-fallback`, `split-hop-pilot` and `idle-cycle-measurement`.
`tests/unit/test_docs_index.py` requires exactly these sections on that set, in
this order; sections that do not apply say so in one line rather than being
omitted. Other how-to pages (CI procedures, repository settings, measurement
matrices, kit layout) keep the sections their task needs and state
preconditions and authorization inline where a step touches live resources;
moving them onto this template is tracked as follow-up work in the task record.

```markdown
# <verb phrase>

> status line

## Purpose and scope
## Preconditions
## Authorization
## Steps
## Verification
## Rollback
## Evidence to record
```

`Authorization` names what the operator must have approved before the
steps run and links the decision boundaries in `AGENTS.md`. `Steps` are
numbered, one copy-paste command per step, with the environment named once.
A runbook that covers several procedures (deploy has re-deploy, Terraform
change and add-a-device; rotate has five scopes) keeps one H2 per procedure
in place of a single `Steps` section, between `Authorization` and
`Verification`; tests slice those sections by heading, so rename them with
care. `Evidence to record` lists what goes into the task record or
acceptance report.

## Decision record template

```markdown
# NNNN — <title>

> **Status:** Current · **Type:** decision · **Tier:** <tier>

Status: Accepted — YYYY-MM-DD

## Context
## Decision
## Consequences
## Alternatives considered
```

Decisions are immutable once accepted. Change course with a new numbered
record and mark the old one `Superseded by`. Records accepted before the
2026-10 rewrite keep their original section structure; only their status
line and file name were normalised.

## Writing

- English technical text follows ASD-STE100 Simplified Technical English:
  short sentences, one instruction per sentence, active voice, approved
  verbs, no synonyms for the same thing.
- Lead with the action or the fact. Put the reason after it.
- Commands go in fenced blocks with the shell named. Output that the reader
  must compare goes in a fenced block too.
- Link to the canonical page instead of restating it. Each fact has one
  home; `AGENTS.md` lists the source of truth for contracts.
- Never paste secrets, addresses, hostnames, client identifiers or
  decrypted material, not even redacted samples that keep their shape.
- Keep generated references generated: `reference/make-targets.md` and
  `reference/vpnd-commands.md` come from `make docs-reference`.

## Machine-readable index

`docs/llms.txt` is generated by `vpnd ai-docs` and committed. It follows the
`llms.txt` convention: an H1, a blockquote summary, one H2 section per
folder with one link per page, and an `## Optional` section for `archive/`.
Regenerate it whenever a page is added, moved or removed.
