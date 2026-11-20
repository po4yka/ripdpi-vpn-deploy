## Context

See `proposal.md` for motivation. Current state:

- `nginx-xhttp` and `reality-self-steal` each publish a controller-local tree through the serialized nginx transaction. The transaction-owned tree must not change between deploys, because publication receipts bind its bytes.
- The model news refresher already shows the pattern for content that changes: an unprivileged timer writes outside the transaction tree and an exact nginx location serves the result. Its units wait for the ingress commit, because no rollback restores them.
- `reality-self-steal` can run without `nginx-xhttp` (the P0 profiles), so a mechanism that only `nginx-xhttp` owns does not reach the most common self-steal host.
- Nodes are disposable. Anything that lives only on the node is lost at recreation.
- The controller has the pinned `jinja2` and `markdown-it-py`. A node has only the distribution `python3`.

## Goals / Non-Goals

- Goal: no production prose, theme or asset comes from this repository.
- Goal: content advances without a deploy, without a model key on the node and without node-local state that recreation loses.
- Goal: a testable admission gate replaces the judgement "looks unique".
- Non-goal: a model call from repository code. The operator's agent writes the content.
- Non-goal: site types that explain large traffic (mirrors, downloads). Separate change.
- Non-goal: domain age, certificate history, search indexing.
- Non-goal: compatibility with the old tree layout or with `public-site-render`.

## Decisions

- **The controller renders every generation; the node only selects one.** Generation `n` is the complete site with the first `n` scheduled articles. The node publisher compares `schedule.json` with the clock, builds the selected generation from the archive and swaps a `current` symlink. Rejected: rendering on the node (needs a template engine and parses more input on a public host) and a model call on the node (a key on a disposable host and a visible outbound pattern).
- **The schedule is a pure function of seed, start date and cadence.** The published state then needs no node-local history, a recreated node shows the same dates, and the build is reproducible. Rejected: a node-local "last published" counter, which recreation resets.
- **Generations travel as one archive outside the nginx transaction.** A per-file declaration of each generation would put several hundred paths into each ingress journal. `site/` (the initial generation) stays in the transaction as today and is the fallback when no generation is published. The publisher stores common files once and builds a generation with hard links.
- **Published state is keyed by the archive digest.** The vhost configuration, which the transaction owns, names `/var/lib/public-site/<digest>/current`. Publication therefore runs before activation, and a vhost rollback points at the previous digest, which is still present. Old digests are removed after the commit. This removes the wait-for-commit rule that the model news units need.
- **A new role `public-site` owns the publisher.** Both vhost roles consume it. It is dispatched by a derived predicate (an enabled vhost role names a bundle with an archive), not by a new operator toggle; `role-tiers.yml` classifies it as tactical. Rejected: placement in `nginx-xhttp`, which P0-only hosts do not run.
- **The theme is operator content.** The repository defines the theme contract (Jinja templates `base`, `index`, `article`, `archive`, plus assets) and keeps the bundled site as the non-production fixture. A fixed set of selectable themes in a public repository would be a fixed set of fingerprints.
- **Articles are Markdown with a small front matter block** (title, summary, topic), rendered with `markdown-it-py` with raw HTML disabled. Articles carry no date: the schedule assigns it.
- **Similarity is containment of 8-word sequences**, measured for each page against the reference text, after markup removal and case folding. Containment detects a hostname swap and a partial copy; a symmetric measure dilutes both. The initial limit is 10 percent. The first execution step calibrates it on three samples (bundled site with another origin: refuse; bundled site with one paragraph replaced on each page: refuse; independent fixture: accept) and records the measured values in the test.
- **The live-data refresher moves to `public-site` and becomes identity-neutral.** Shell path, sources and output path become inputs; the guards do not change. A production bundle must declare its own sources, because one default list on many nodes would produce identical pages.
- **Bundle layout breaks the variable contract.** A reserved subdirectory inside the published tree was rejected: each tree publisher would need a rule to skip it.
- **An agent skill `public-site-content` writes theme and backlog** from the brief that `public-site-new` emits. It uses the operator's own model access, runs `public-site-build` and `public-site-check`, and stops when the check passes.

## Contracts and ownership

- `scripts/public_site.py` — subcommands `new`, `build`, `check`, `status`. Reads and writes controller-local paths only. Make targets `public-site-new`, `public-site-build`, `public-site-check`, `public-site-status` pass `PUBLIC_SITE_URL`, `PUBLIC_SITE_DIR` and `PUBLIC_SITE_PEERS`.
- Identity directory (operator-owned, outside Git, listed in the local kit catalog): `identity.yml`, `brief.md`, `theme/`, `articles/`. Bundle directory: `site/`, `backlog.tar`, `schedule.json`, optional `live.json` (page path and sources).
- `ansible/roles/public-site/` — publisher script, service and timer, archive delivery to a root-owned directory that the publisher group reads, state under `/var/lib/public-site/<digest>/`, live-data refresher and its units, retirement.
- `ansible/roles/nginx-xhttp/`, `ansible/roles/reality-self-steal/` — bundle layout admission, `site/` publication, vhost location order (published generation first, transaction tree second, site 404 last), production preflight that runs the check.
- `ansible/playbooks/tasks/transport-ingress-begin.yml` — declares `site/` paths. `ansible/playbooks/site.yml` — role order and removal of replaced digests after commit.
- No change: Terraform roots, cloud-init, `secrets/schema.json`, vpnd, client bundle contract, provider listener contract.

## Risks / Trade-offs

- A model writes generic prose → the brief requires a subject that fits the domain name and concrete worked material; the check measures only similarity, so the operator still reviews the text.
- The publication times follow a public algorithm → only the seed selects them, and intervals have a wide range; the pattern "one article each one to two weeks" is common.
- The node clock is wrong → the publisher can publish early. The baseline role owns time sync; an early article is not a security failure.
- The backlog ends → the site stops changing. `public-site-status` and the dry-run warning report it; the publisher never repeats or invents an entry.
- Archive extraction on a public host → the archive comes from the controller, the service has no network and no privileges, and extraction uses the standard library data filter plus an explicit member check.
- The existing fleet serves bundled pages → its next production deploy is refused until a bundle exists. This is intended and is the migration gate.
- Traffic volume does not match a small site → not addressed here.

## Migration Plan

1. Land the controller tool and the check. No host behavior changes.
2. Land the role, the vhost wiring and the layout break together, with the bundled site moved to the new layout for non-production fixtures.
3. For each production node: create an identity, write content with the skill, build, check, set both site variables to the bundle, dry-run, deploy. Authorization for each node is separate from this change.
4. Rollback before step 3 is a revert. After step 3 a node rolls back by deploying its previous bundle; a revert of the code also requires the old tree layout in the variables.

Gates: `pytest tests/unit/test_public_site_bundle.py tests/unit/test_public_site_contract.py tests/unit/test_model_news.py`, `make snapshot-check`, `make molecule-test ROLE=public-site`, `make molecule-test ROLE=nginx-xhttp`, `make molecule-test ROLE=reality-self-steal`, `make check` once before handoff, then dry-run and staging deploy.
