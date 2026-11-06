---
id: ANS-1793776705651907
title: Publish a refreshed open-model news page on the public site
kind: feature
status: review
area: ansible
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1793776705651907-public-site-model-news
created: 2026-11-04
updated: 2026-11-07
related_tasks: []
---

## Goal

The bundled public site serves a periodically refreshed `/news.html` with open-model repositories and headlines from pinned public sources, plus new dated notes, a topic archive, a glossary and a primary-source model tracker that match the site's Chinese-model theme.

## Acceptance criteria

- A hardened `model-news.timer` renders `/news.html` from the pinned sources with escaped titles and links only, drops transport vocabulary, refuses DTDs and non-HTTPS links, and keeps the last page when every source fails.
- `nginx_xhttp_model_news_enabled: false` removes the units, state, user, navigation link and sitemap entry.
- Three new notes, the archive, glossary and tracker render, appear in the update log, Atom feed and sitemap, and every tracker row cites its model repository.
- `tests/unit/test_model_news.py`, `tests/unit/test_public_site_contract.py`, `make snapshot-check` and ansible-lint pass; Molecule and staging evidence are recorded in `verification.md`.
