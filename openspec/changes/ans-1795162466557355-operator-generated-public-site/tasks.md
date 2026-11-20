# ANS-1795162466557355: Generate a unique self-updating public site for each operator

## Objective

An operator creates a private site identity, builds a bundle from content that only that operator has, and deploys it. A production deploy refuses a bundle that shares content with the bundled site or with another bundle. The node publishes the next article at its scheduled time without a deploy, and a recreated node shows the same pages and dates.

## Ownership

`scripts/public_site.py`, `Makefile` (four new targets, removal of `public-site-render`), `ansible/roles/public-site/` (new), `ansible/roles/nginx-xhttp/` and `ansible/roles/reality-self-steal/` (bundle admission, site publication tasks, vhost templates, folder notes), `ansible/playbooks/site.yml`, `ansible/playbooks/tasks/transport-ingress-begin.yml`, `ansible/playbooks/render-public-site.yml` (removed), `ansible/role-tiers.yml`, `.agents/skills/public-site-content/`, `docs/how-to/` and `docs/reference/deploy-profiles.md`, `tests/unit/test_public_site_bundle.py` (new), `tests/unit/test_public_site_contract.py`, `tests/unit/test_model_news.py`, and the snapshot goldens of the touched roles. One writer. `Makefile`, `site.yml` and `transport-ingress-begin.yml` are shared files: serialize with `XRY-1794729068388916` and `ANS-1793776705651907`, which are in review and touch the same site contract.

## Execution

- [x] ANS-1795162712291937 Add scripts/public_site.py (new, build, check, status) with Make targets and calibrated similarity tests; remove public-site-render #feature @item:ANS-1795162466557355
- [x] ANS-1795162729645051 Add the public-site role: archive delivery, digest-keyed publisher, hardened units, retirement and Molecule scenario #feature @item:ANS-1795162466557355
- [ ] ANS-1795162748588038 Move both vhost roles to the bundle layout with generation-first locations, production check preflight and runway warning #feature @item:ANS-1795162466557355
- [ ] ANS-1795162761685232 Move the live-data refresher into public-site with per-bundle shell and sources #feature @item:ANS-1795162466557355
- [ ] ANS-1795162774451454 Add the public-site-content skill, operator how-to, folder notes and refreshed snapshots; pass make check #feature @item:ANS-1795162466557355
- [ ] ANS-1795162792314476 Record dry-run and staging evidence for publication, rollback and node recreation #feature @item:ANS-1795162466557355

## Verification

- Local: `python3 -m pytest tests/unit/test_public_site_bundle.py tests/unit/test_public_site_contract.py tests/unit/test_model_news.py`, `make snapshot-check`, `make shellcheck`, `make docs-check`, then `make check` once before handoff.
- CI: Molecule scenarios `public-site`, `nginx-xhttp`, `reality-self-steal` and full-stack (the pinned Molecule image has no arm64 manifest for a local run).
- Dry-run: `make dry-run` on a staging node with a generated bundle; one more dry run with the bundled pages under another origin must fail in preflight.
- Staging: deploy a bundle whose schedule has a time a few minutes ahead; after the timer runs, request the new article, feed and sitemap; request an article of a later generation and expect the site 404; `systemd-analyze security` for both units; force an activation failure and confirm the previous bundle is served; recreate the node and compare page digests.
- Live: one production node migrated under separate authorization, with deploy, verify, security-verify and smoke-test.
- Client and artifact: not applicable. No client, bundle contract or release artifact changes.
