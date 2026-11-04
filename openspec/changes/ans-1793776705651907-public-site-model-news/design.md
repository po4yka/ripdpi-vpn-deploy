## Context

`nginx-xhttp` publishes the bundled public site through its compensated nginx transaction (`tasks/transaction.yml`). Every page is a Jinja template rendered on the controller, so nothing on the site changes between deployments. The bundled tree is refused on `env: prod` hosts, which publish an operator-owned tree instead. The `cdn-front` role already runs a node-local daily timer that fetches an upstream list over HTTPS, which is the precedent for periodic outbound fetches from a node. Strict host egress already admits TCP/443. See `proposal.md` for motivation.

## Goals / Non-Goals

- Goal: `/news.html` shows recent open-model repositories and headlines without operator action, and stays correct when sources fail.
- Goal: more real, dated pages: three notes, an archive by topic, a glossary, and a model tracker with primary-source citations.
- Non-goal: client-side JavaScript, third-party embeds, or any CSP change.
- Non-goal: republishing article text, summaries or images from upstream sources.
- Non-goal: changing the operator-owned production tree contract. The news page carries the bundled identity, so a host with `nginx_xhttp_public_site_dir` set never serves it: the location, units and state are absent there, and identical bundled content cannot cluster production nodes.

## Decisions

- Render on the node with a systemd timer, not on the controller at deploy time. Deploy-time rendering would only refresh on deploy. Rejected client-side fetching because the CSP forbids it and it would expose visitors to third parties.
- The fresh page lives outside the transaction-owned tree, in `/var/lib/model-news/news.html`, served by `location = /news.html { root /var/lib/model-news; }` on both HTTPS vhosts. A timer that wrote into `/var/www/public-site` would create drift against the publication receipts.
- The page chrome (head, navigation, footer, canonical metadata) stays in Jinja: the role renders `news.html.j2` to `/etc/model-news/news-shell.html` with two HTML comment markers, and the script only fills the markers. The same shell, unfilled, seeds the first page.
- Sources are data in role defaults (`nginx_xhttp_model_news_sources`): Hugging Face model listings for ten organizations, named by `org` only so the script builds one fixed listing URL (`/api/models?author=<org>&sort=createdAt&direction=-1&limit=10`), under "New open-weight repositories", and the `aigc.news` RSS feed under "Headlines". Hub listings are a primary record of a release; no lab publishes a current feed of its own (checked 2026-11-04).
- Python standard library only (`urllib`, `xml.etree`, `xml.parsers.expat`, `json`, `html`); no new package on the node. An expat pre-pass refuses any DTD in any encoding before the tree parse. A redirect handler refuses non-HTTPS targets, and a wall-clock deadline bounds each body. The User-Agent is a generic feed-reader name without the site name, so third-party logs do not link nodes to the site.
- Cadence: `OnActiveSec=5min`, then `OnUnitActiveSec=6h`, each with up to 30 minutes of `RandomizedDelaySec`, so a fleet does not poll in step and a new host fills the page within an hour without the deploy waiting on third parties. The role seeds the page before the nginx transaction reloads, so the new location never returns 404.
- Run as a dedicated `model-news` system user with `StateDirectory=model-news` (mode 0755 so nginx can read), an empty capability set and `ProtectSystem=strict`. Rejected `DynamicUser=` because its state lives under `/var/lib/private`, which nginx cannot traverse.

## Contracts and ownership

- Role `nginx-xhttp`: `files/model-news/refresh_model_news.py`, `templates/model-news.service.j2`, `templates/model-news.timer.j2`, `templates/model-news-sources.json.j2`, `templates/public-site/news.html.j2`, `templates/site.conf.j2` (one location per HTTPS vhost), `tasks/model-news.yml`, `tasks/model-news-absent.yml`, defaults for the toggle and sources.
- New bundled pages under `templates/public-site/`: three notes, `notes/index.html` (archive), `glossary.html`, `models.html`; `updates.html`, `feed.xml`, `sitemap.xml` and `index.html` record them.
- Role defaults: `nginx_xhttp_model_news_enabled` and `nginx_xhttp_model_news_sources`; inventory may override both.
- Tests: `tests/unit/test_model_news.py` runs the script against fake upstream responses; `tests/unit/test_public_site_contract.py` covers the new pages, the navigation link and the unit hardening; snapshot goldens cover every new template.

## Risks / Trade-offs

- Periodic outbound requests from a node to two public hosts → small, jittered, every six hours, and the same class of traffic as the existing prefix and geodata refresh.
- Upstream headline wording is outside repository review → only titles and links are shown, every value is escaped, and the forbidden-term filter enforces the public site vocabulary rule.
- A source changes format or disappears → per-source failures are skipped; total failure keeps the last page and fails the unit visibly.
- Third-party terms of use → titles and links only, each linking back to its origin.

## Migration Plan

Forward: an ordinary deploy installs the units and the seed page; the timer fills the page within an hour. If the protected ingress transaction rolls back after the seed, the units and state remain but nginx no longer serves the page; the next deploy reconciles both. Rollback: set `nginx_xhttp_model_news_enabled: false` and deploy, which removes the units, state and link; or revert the change. No data migration and no compatibility break. Gates: `make snapshot-check`, the two unit test files, `make molecule-test ROLE=nginx-xhttp`, then a dry-run and deploy on staging before any production toggle.
