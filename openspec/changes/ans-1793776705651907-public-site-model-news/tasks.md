# ANS-1793776705651907: Publish a refreshed open-model news page on the public site

## Objective

The bundled public site serves a refreshed `/news.html` from pinned public sources and gains three notes, a topic archive, a glossary and a primary-source model tracker, with a toggle that removes the news surface completely.

## Ownership

`ansible/roles/nginx-xhttp/` (defaults, `files/model-news/`, `tasks/model-news*.yml`, `tasks/enable.yml`, `tasks/disable.yml`, `templates/model-news*`, `templates/site.conf.j2`, `templates/public-site/`, `files/public-site/assets/site.css`, `molecule/default/verify.yml`, `CLAUDE.md`), `tests/unit/test_model_news.py`, `tests/unit/test_public_site_contract.py`, and the role's snapshot goldens. One writer; no shared-file lane with other changes.

## Execution

- [x] ANS-1793777317745592 Add the model news refresh script, hardened units, nginx location, toggle and removal path with unit tests #feature @item:ANS-1793776705651907
- [x] ANS-1793778072080811 Add notes on open-weight Chinese models, the topic archive, glossary and primary-source model tracker #feature @item:ANS-1793776705651907
- [x] ANS-1793779686673516 Record the publication in updates, feed, sitemap and home page, refresh snapshots and pass the role gates #feature @item:ANS-1793776705651907

## Verification

- Local: `pytest tests/unit/test_model_news.py tests/unit/test_public_site_contract.py`, `make snapshot-check`, `scripts/check-secrets-coverage.py`, `scripts/check-templates-render.py`, `ansible-lint roles/nginx-xhttp`.
- CI: the nginx-xhttp Molecule scenario (the pinned image has no arm64 manifest for local runs).
- Dry-run and staging: `make dry-run` then a staging deploy, followed by `systemctl status model-news.timer`, `systemd-analyze security model-news.service`, and a request for `/news.html` after the first refresh.
