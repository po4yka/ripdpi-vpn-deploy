---
id: DOC-1792603004056378
title: "Documentation rewrite: Diátaxis tree, neutral vocabulary, public README"
kind: chore
status: doing
area: docs
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-21
updated: 2026-10-21
spec_reason: docs-only
related_tasks: []
---

## Goal

A reader who opens the repository for the first time (operator, contributor or coding agent) finds every page from one index, knows each page's type and tier, and never meets a geographic, carrier or censorship-apparatus label in a name, heading, table cell or diagram. The README is a short human entry point; agent rules stay in AGENTS.md; generated references mirror the Makefile and the vpnd parser; guards keep the tree from drifting.

## Acceptance criteria

- `docs/` is organised as tutorials, how-to, reference, explanation, decisions, research and archive; `docs/README.md` lists every page; every page opens with the status line defined in `docs/STYLE.md`; `tests/unit/test_docs_index.py` passes.
- README is at most 130 lines, every link resolves, and the only rule text shared with `AGENTS.md` is the five hard-rule bullets.
- No geographic, carrier, regulator or censorship-apparatus label remains in file names, headings, table cells or diagram labels of README and `docs/`; prose describes behaviour.
- Runbook procedures and guarded shell blocks are unchanged; `tests/unit/test_operator_verb_scope.py` and `tests/unit/test_restore_workflow_contract.py` pass.
- `vpnd ai-docs` walks the tree; `docs/llms.txt`, `docs/reference/make-targets.md` and `docs/reference/vpnd-commands.md` equal `make docs-reference` output; `make docs-check` is part of `make check` and passes.
- `make check` passes locally; the pull request's hosted checks pass; an independent reviewer reads the full patch against these criteria.
