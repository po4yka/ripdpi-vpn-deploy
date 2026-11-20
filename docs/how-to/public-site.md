# Build and maintain an operator-owned public site

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-11-20

## Purpose and scope

A production node serves a site that only its operator has. This page shows how to create the site identity, write its content, build and check the bundle, deploy it, and add articles later. It covers the REALITY self-steal site and the nginx-xhttp site.

The repository supplies the tools and the node-side publisher, and no production text, theme or asset. The bundled pages under `ansible/roles/` are a fixture for non-production hosts: they are public, so a copy of them under another hostname links a node to every other copy, and a production deploy refuses it.

Not covered: the amount of traffic that a small site can explain, the age of the domain and its certificate history.

## What a bundle is

`make public-site-build` writes one directory, the bundle:

| Path | Content |
|---|---|
| `site/` | The complete static site at its first publication (at least `index.html` and `404.html`) |
| `backlog.tar.gz` | Every later generation of the site; generation `n` adds the `n`-th scheduled article |
| `schedule.json` | The publication time of each generation |
| `live.json` | Optional: one page that the node refreshes from public feeds |

A directory that holds only `site/` is a valid static bundle, so an existing personal site can be served without the other files.

The schedule depends only on `identity.yml`. The node compares it with its clock every 15 minutes and serves the latest generation whose time has passed. A recreated node therefore shows the same pages with the same dates, and no deploy is necessary when an article is due.

## 1. Create the identity

Keep the identity directory in the local operator kit, outside Git, and record it in the kit catalog ([local operator kit](local-operator-kit.md)). It links the domain to the operator.

```bash
mise exec -- make public-site-new \
  PUBLIC_SITE_DIR="$PWD/secrets/local/sites/<site>" \
  PUBLIC_SITE_URL="https://<hostname>" \
  PUBLIC_SITE_NAME="<site name>" \
  PUBLIC_SITE_SUBJECT="<what the site is about>"
```

The command writes `identity.yml` and `brief.md` and creates empty `theme/` and `articles/` directories. It refuses a directory that already holds an identity. The origin is a lowercase `https` origin without a path and without `:443`. Choose a subject that fits the domain name.

`identity.yml`:

| Key | Meaning |
|---|---|
| `origin`, `name`, `subject` | The canonical origin, the site name and its subject |
| `seed` | Random value that selects the publication times; never copy it to another site |
| `start` | Date of the first publication. Do not set it earlier than the domain's first certificate |
| `cadence_days` | Mean interval between articles; each interval is between half and one and a half times this value |
| `initial_articles` | Number of articles in the first publication |
| `article_path` | URL scheme of articles, for example `notes/{slug}.html` |
| `live` | Optional live page: `page`, `sources`, `markup` (see `brief.md`) |

Do not change `seed`, `start` or `cadence_days` after the first deploy: the dates of published articles would change.

## 2. Write the content

`brief.md` states the theme contract: the required templates, the template variables, the served file types and the terms that must not appear. Write the theme and the articles by hand, or ask a coding agent to use the `public-site-content` skill with your own model access. The repository code makes no model call.

Articles are Markdown files in `articles/`, published in file name order. They carry no date. Read what an agent wrote before you deploy it: the check measures shared content, not the quality of the text.

## 3. Build and check

```bash
mise exec -- make public-site-build PUBLIC_SITE_DIR="$PWD/secrets/local/sites/<site>"
```

```bash
mise exec -- make public-site-check PUBLIC_SITE_DIR="$PWD/secrets/local/sites/<site>" PUBLIC_SITE_URL="https://<hostname>"
```

```bash
mise exec -- make public-site-status PUBLIC_SITE_DIR="$PWD/secrets/local/sites/<site>"
```

The bundle is `<identity directory>/bundle`; set `PUBLIC_SITE_BUNDLE` to use another path. When you have more than one bundle, add `PUBLIC_SITE_PEERS="<bundle> <bundle>"` to the check so that it also compares them with each other.

The check refuses, and names, each file that:

- shares more than 10 percent of its 8-word sequences with the bundled site or a peer bundle, or is byte-identical to one of their files;
- loads a resource from another host, uses `<base>` or a meta refresh, or has a canonical, feed or sitemap URL outside the origin;
- contains a term that the public site contract forbids, or has a file type that the check cannot read;
- declares a live page with the bundled feeds or markup, with a peer's markup, or without the two markers.

The check protects you from an accidental copy. It is not a defence against content that hides a copy on purpose.

The build refuses an archive above 4 MiB. The usual cause is a list of every article on every article page, which stores each page again for each generation.

## 4. Deploy

Set the variables in the private extra-vars file that already holds `public_site_canonical_url` ([deploy profiles](../reference/deploy-profiles.md)):

```yaml
reality_self_steal_public_site_dir: "/absolute/path/to/secrets/local/sites/<site>/bundle"
nginx_xhttp_public_site_dir: "/absolute/path/to/secrets/local/sites/<site>/bundle"
```

One hostname on both roles names one bundle. Two hostnames need two bundles, and the deploy compares them as peers.

Then follow [the deploy runbook](deploy.md): dry run first, deploy after review. Both use cloud credentials and SSH, so they need the authorization that the runbook describes. On a production host the dry run and the deploy run the same check before any task changes the host, and the dry run warns when fewer than 30 days of unpublished articles remain.

After a deploy, on the node:

```bash
systemctl list-timers 'public-site-*'
```

```bash
journalctl -u public-site-publish.service -n 20
```

`/var/lib/public-site/<digest>/current` is the served generation. A request for an article that is not yet due answers with the site's 404 page.

## 5. Add articles

Add files with higher numbers to `articles/`, then build, check and deploy again. The generations that are already published keep their dates, because the schedule depends only on the identity. A change of the theme or of an earlier article changes the bundle; the node then serves the same generation number with the new pages.

When the last article is published the site stops changing. The publisher never repeats or invents an entry.

## Troubleshooting

| Symptom | Cause and action |
|---|---|
| The deploy refuses "must name a site bundle" | The variable names a tree with its pages at the top level. Point it at a directory with `site/`, or build a bundle |
| The preflight refuses a page as "also in the bundled site" | The page copies bundled text. Rewrite it; do not edit it until the number passes |
| `public-site-publish.service` failed | Read its journal. A refused archive keeps the previous generation; build and deploy the bundle again |
| The live page shows no entries | The first refresh runs about five minutes after a deploy. Then read `journalctl -u 'public-site-live@*'`; a source outage keeps the previous page |
| The site answers with a plain 404 for every path | The state directory was removed. The timer rebuilds it within its interval; `systemctl start public-site-publish.service` does it at once |
