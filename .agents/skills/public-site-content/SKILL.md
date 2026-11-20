---
name: public-site-content
description: Write the theme and article backlog of one operator-owned public site and build a bundle that passes the uniqueness check. Use when an operator asks for site content, more articles, a new site identity or a live page for the REALITY self-steal or nginx-xhttp site; deploying the bundle uses vpn-deploy.
---

# Write an operator-owned public site

Produce one site that exists under no other name: its text, markup, style sheets and images are written for this operator and this subject. The work is local. It uses no credential and contacts no host; a deploy of the result is a separate request.

## Inputs

Read `brief.md` and `identity.yml` in the identity directory that the operator names. `make public-site-new` creates them; [the how-to](../../../docs/how-to/public-site.md) gives the command and the directory contract. If the directory does not exist, ask for the origin, site name and subject, then create it with that command. The subject must fit the domain name: a visitor who reads the name must not be surprised by the content.

## Write the theme

Write every file under `theme/` yourself, for this site only.

- The brief lists the required templates, the template variables and the served file types. Add the pages an ordinary site of this kind has (about page, archive, feed, sitemap, robots file).
- Choose the page structure, class names, typography, colors and URL scheme (`article_path` in `identity.yml`) for this subject. Do not start from the repository's bundled site, from the test fixture, or from another bundle of the same operator: the check refuses shared text and files, and a shared page structure is a fingerprint that it does not measure.
- Load every resource from the site itself. Do not add analytics, fonts or scripts from another host, a `<base>` element or a meta refresh.
- An article page may link to its neighbors. A list of every article on every article page stores each page again for each generation and can exceed the archive limit.

## Write the articles

Write one Markdown file for each article in `articles/`, in publication order (`001-…`, `002-…`). The brief gives the number that covers one year.

- Each article has concrete, checkable material on the subject: worked examples, measurements, procedures, comparisons. Vary length and form; a series of same-sized essays reads as generated.
- State only facts that you can support. Do not invent people, organizations, contact details, quotations, sources or events, and do not present an example as a report of something that happened.
- Do not write a date in an article or refer to "today": the schedule assigns each publication time, and an article can appear months after it was written.
- Keep the terms that the brief forbids out of every file, including file names.
- Apply these rules to every article, not only the first ones.

## Live page (only on request)

A live page lists titles and links from public feeds and is refreshed on the node. Add it only when the operator asks. Choose feeds that belong to the subject, write the `section`, `item` and `updated` markup for this theme, and put the two marker comments from the brief into the page. The check refuses the repository's default feeds and markup.

## Build and check

Run these from the repository root, with the pinned toolchain (`mise exec --`):

1. `make public-site-build PUBLIC_SITE_DIR=<identity directory>` writes `<identity directory>/bundle`.
2. `make public-site-check PUBLIC_SITE_DIR=<identity directory> PUBLIC_SITE_URL=<origin>`, with `PUBLIC_SITE_PEERS="<other bundle> …"` when the operator has other bundles.
3. `make public-site-status PUBLIC_SITE_DIR=<identity directory>`.

Correct the cause of each refusal in the theme or the articles and repeat. Do not remove a check, weaken the brief's rules, or change text only until the similarity number passes: a refused page is rewritten.

## Stop and report

Stop when the build and the check exit 0. Report the bundle path, the number of articles, the days of unpublished material from the status command, and anything the operator must still decide (for example the start date or cadence in `identity.yml`). Say plainly that the check measures shared content, not the quality of the writing, so the operator still reads the site before a deploy. Do not set deployment variables, commit the identity directory or deploy.
