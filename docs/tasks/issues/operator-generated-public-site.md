---
id: ANS-1795162466557355
title: Generate a unique self-updating public site for each operator
kind: feature
status: backlog
area: ansible
priority: medium
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795162466557355-operator-generated-public-site
created: 2026-11-20
updated: 2026-11-20
related_tasks: []
---

## Goal

Each operator publishes a public site (REALITY self-steal and nginx-xhttp) whose text, theme and assets come from no shared source, and the node publishes new articles on a schedule without a deploy.

## Acceptance criteria

- `make public-site-new`, `public-site-build`, `public-site-check` and `public-site-status` create, build, admit and report a site bundle on the controller without network access.
- The check refuses the bundled pages under another origin, a reused bundled asset and a bundle similar to a named peer; a production deploy and dry run refuse the same bundle in preflight.
- A hardened node timer serves the generation that the schedule selects; an unpublished article answers with the site 404; a recreated node serves byte-identical pages.
- A vhost rollback serves the previous bundle; a bundle without an archive is a static site with no publisher unit.
- `make public-site-render` is removed and both site variables name a bundle directory.
- Unit tests, snapshots and the three Molecule scenarios pass; dry-run and staging evidence is recorded in `verification.md`.
