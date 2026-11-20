# Change: Generate a unique self-updating public site for each operator

Task ID: `ANS-1795162466557355`

## Why

A production node must serve an operator-owned site, but the only documented way to get one is `make public-site-render`. That target renders the bundled pages from this public repository with a different hostname. Each operator who follows the documentation publishes the same text, the same assets and the same page structure, so one search for a sentence from a bundled page finds every such node. The existing production refusal of the bundled site does not prevent this, because the rendered copy is an operator-owned tree.

The published site also does not change between deploys. On the reference fleet the newest `Last-Modified` value is the deploy date, the feed has two distinct dates, and the refreshed news page is off for every operator tree because it carries the bundled identity. A site that never changes and exists under many names is weak evidence of an ordinary web site.

## What Changes

- `make public-site-new` creates a private site identity for one operator: a random seed, the operator's canonical origin and subject, a start date and a publication cadence. The repository contains no production prose.
- `make public-site-build` turns the identity, an operator-owned theme and an operator-owned article backlog into a site bundle: a complete initial site, an archive of future generations and a publication schedule.
- `make public-site-check` refuses a bundle that is too similar to the bundled site or to another bundle of the same operator, that reuses a bundled asset, that references a third-party resource, or that contains transport vocabulary. A production deploy runs the same check before it changes the host.
- A node-local timer publishes the next generation when its scheduled time arrives. The published state is a pure function of the bundle and the clock, so a recreated node shows the same pages with the same dates. The publisher has no network access.
- The refreshed live-data page becomes available to operator bundles, with sources that the operator declares.
- `make public-site-status` reports how many days of unpublished material remain.
- An agent skill writes the theme and the article backlog from the identity brief with the operator's own model access.
- **BREAKING**: `nginx_xhttp_public_site_dir` and `reality_self_steal_public_site_dir` name a site bundle directory, whose static tree is in `site/`, instead of the tree itself.
- **BREAKING**: `make public-site-render` and `playbooks/render-public-site.yml` are removed.
- **BREAKING**: a production tree rendered from the bundled pages is refused. Each such node needs a generated bundle before its next deploy.

## Capabilities

### New Capabilities

- `ansible/operator-public-site`: identity creation, bundle build, uniqueness admission, scheduled node-local publication, live-data page for operator bundles, rollback and retirement.

### Modified Capabilities

- None. The existing production refusal of the bundled site stays; the new admission adds to it. The model news requirements of `ANS-1793776705651907` keep their guards and move with the refresher.

## Impact

- Ansible: new role `public-site`; vhost templates and site publication tasks of `nginx-xhttp` and `reality-self-steal`; `playbooks/tasks/transport-ingress-begin.yml` (declared paths); `playbooks/site.yml`; `role-tiers.yml`.
- Scripts and Make: new `scripts/public_site.py` and four targets; removal of `public-site-render`.
- Operator configuration: both site directory variables change meaning. The identity file belongs to the local operator kit and stays outside Git.
- Terraform, cloud-init, secrets schema, vpnd, client bundle contract: no change. No new public listener.
- Dependencies: none added. The build uses the pinned `jinja2` and `markdown-it-py`; the node publisher uses the Python standard library only.
- Not addressed: the ratio between site size and traffic volume, domain age, and certificate history. A site type that explains large flows, such as a mirror of open content, is a separate change.
