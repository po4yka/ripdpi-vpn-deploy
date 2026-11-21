## Purpose

Each operator publishes a public site whose text, assets and structure exist under no other name, and whose content advances on a schedule without a deploy, so that the site of one node gives no evidence about another node and shows ordinary maintenance activity.

## ADDED Requirements

### Requirement: REQ-SITE-IDENTITY — Private identity for each operator

`make public-site-new` MUST create one identity file from an operator-supplied canonical HTTPS origin and subject, with a seed from the operating system random source, a start date and a publication cadence. It MUST refuse to replace an existing identity file, MUST use no network, and MUST write only below the output directory that the operator names.

#### Scenario: Second run on the same directory

- **WHEN** the output directory already holds an identity file
- **THEN** the command exits non-zero and the file is unchanged.

#### Scenario: Unsafe origin

- **WHEN** the origin is not an absolute lowercase HTTPS origin, or includes `:443`
- **THEN** the command exits non-zero and writes nothing.

### Requirement: REQ-SITE-BUILD — Deterministic bundle from operator content

`make public-site-build` MUST produce a bundle with a complete static site in `site/` (at least `index.html` and `404.html`), an archive of future generations and a schedule. The same identity, theme and articles MUST give a byte-identical bundle. The build MUST refuse a symbolic link or non-regular file in its inputs, a canonical, feed or sitemap URL that differs from the identity origin, and an article without a title.

#### Scenario: Repeated build

- **WHEN** the build runs twice on unchanged inputs
- **THEN** every file of the two bundles has the same SHA-256 digest.

#### Scenario: Symbolic link in the theme

- **WHEN** the theme directory contains a symbolic link
- **THEN** the build exits non-zero and writes no bundle.

### Requirement: REQ-SITE-SCHEDULE — Dates follow real publications

The schedule MUST be a function of the identity seed, start date and cadence only. No scheduled time MUST be earlier than the start date. Each interval MUST be between 0.5 and 1.5 times the cadence. Each generation after the initial one MUST add exactly one article. The date that a page, the feed and the sitemap show for an article MUST be its scheduled time, and no date MUST advance without a new article.

#### Scenario: Schedule bounds

- **WHEN** a schedule is built for 40 articles with a cadence of 9 days
- **THEN** every interval is between 4.5 and 13.5 days and the first time equals the start date.

#### Scenario: Generation without new content

- **WHEN** two consecutive generations are compared
- **THEN** the later one contains one article more, and its feed has one entry more with a later date.

### Requirement: REQ-SITE-UNIQUE — Admission refuses shared content

`make public-site-check` MUST refuse a bundle when a page shares more than the configured part of its word sequences with the bundled site or with another bundle that the operator names, when a file is byte-identical to one of their files, or when its live-data sources or markup equal the bundled ones.

#### Scenario: Bundled pages under another hostname

- **WHEN** the bundle is the bundled site rendered with a different origin
- **THEN** the check exits non-zero and names the similar pages.

#### Scenario: Independent content

- **WHEN** the bundle is the independent test fixture
- **THEN** the check exits zero.

#### Scenario: Reused style sheet

- **WHEN** the bundle contains the bundled `site.css` unchanged
- **THEN** the check exits non-zero and names the file.

### Requirement: REQ-SITE-CONTAINED — Admission refuses outside resources and forbidden terms

`make public-site-check` MUST refuse a bundle when a page loads a resource from another host or redirects its loads, or when any served file or path contains a term that the public site contract forbids.

#### Scenario: Script from another host

- **WHEN** a page loads a script from a host other than the site origin
- **THEN** the check exits non-zero and names the page and the URL.

#### Scenario: Forbidden term in another script form

- **WHEN** a page contains a forbidden term in full-width characters
- **THEN** the check exits non-zero and names the page and the term.

### Requirement: REQ-SITE-PREFLIGHT — Production deploys run the admission first

A deploy and a dry run to a production host MUST run the same check on the controller for every site bundle that an enabled vhost role serves, and MUST refuse before any task changes the host.

#### Scenario: Production deploy with a refused bundle

- **WHEN** a production host's site variable names a bundle that the check refuses
- **THEN** the deploy and the dry run fail in preflight, and no task has changed the host.

### Requirement: REQ-SITE-PUBLISH — Scheduled publication without a deploy

The node publisher MUST serve the latest generation whose scheduled time is not later than the current time, and MUST replace the served generation atomically. The served generation MUST depend only on the bundle and the clock. The publisher MUST use no network. An article of a later generation MUST NOT be reachable by any URL. When no later generation exists, the publisher MUST keep the last one and exit zero.

#### Scenario: Scheduled time passes

- **WHEN** the clock passes the scheduled time of generation 5 and the timer runs
- **THEN** the site serves the article, index, feed and sitemap of generation 5, and `Last-Modified` of the new article equals its scheduled time.

#### Scenario: Recreated node

- **WHEN** the same bundle is deployed to a new node
- **THEN** the served pages and their dates are byte-identical to those of the previous node at the same time.

#### Scenario: Request for an unpublished article

- **WHEN** a client requests the path of an article from a later generation
- **THEN** the response is the site 404 page.

### Requirement: REQ-SITE-ISOLATION — Unprivileged publisher

The publisher service MUST run as a dedicated system user with no capabilities, a read-only system view, no network address families, and write access only to its state directory. It MUST refuse an archive member that is not a regular file or directory below the extraction root.

#### Scenario: Unit hardening

- **WHEN** the service unit is rendered
- **THEN** it sets a dedicated `User`, an empty `CapabilityBoundingSet`, `ProtectSystem=strict`, `NoNewPrivileges=true`, `PrivateNetwork=true`, and `ReadWritePaths` limited to the state directory.

#### Scenario: Archive member outside the root

- **WHEN** the archive contains a member with `..` in its path or a link member
- **THEN** the publisher exits non-zero and the served generation is unchanged.

### Requirement: REQ-SITE-ROLLBACK — Publication follows the accepted vhost

Published state MUST be keyed by the digest of the bundle archive. A rollback of the nginx transaction MUST serve the generation of the previous bundle. State of a replaced bundle MUST be removed only after the deploy has committed. A bundle without an archive MUST be served as a static site. A disabled vhost role MUST remove the publisher units, state and user when no other enabled role uses them.

#### Scenario: Failed activation after a new bundle

- **WHEN** a deploy with a new bundle fails after publication and the ingress transaction restores the previous vhost
- **THEN** the site serves the previous bundle's current generation.

#### Scenario: Static bundle

- **WHEN** the bundle holds only `site/`
- **THEN** the vhost serves that tree and no publisher unit exists on the host.

#### Scenario: Two roles with one bundle

- **WHEN** `nginx-xhttp` and `reality-self-steal` name the same bundle
- **THEN** one publisher instance exists and both vhosts serve the same bytes.

### Requirement: REQ-SITE-LIVE — Live-data page for operator bundles

A bundle MAY declare a live-data page with its own sources. The refresh MUST keep every source, content, vocabulary, failure and isolation guard of the model news requirements, MUST fill only the markers of the page shell from the served generation, and MUST exist on a production host only when the bundle declares sources.

#### Scenario: Bundle with declared sources

- **WHEN** a production bundle declares a live-data page and two HTTPS feeds
- **THEN** the page is served with escaped titles and links from those feeds only.

#### Scenario: Bundle without sources

- **WHEN** a bundle declares no live-data page
- **THEN** no refresh unit exists and the page path answers with the site 404.

### Requirement: REQ-SITE-RUNWAY — Remaining material is visible

`make public-site-status` MUST print the number of unpublished generations and the days until the last scheduled time, without network access. A deploy dry run MUST warn when fewer than 30 days remain.

#### Scenario: Short runway

- **WHEN** the last scheduled time is 12 days after the current time
- **THEN** the status prints 12 days and the dry run prints a warning that names the bundle.

### Requirement: REQ-SITE-LAYOUT — Bundle directory contract

`nginx_xhttp_public_site_dir` and `reality_self_steal_public_site_dir` MUST name a bundle directory. A directory without `site/index.html` and `site/404.html` MUST be refused before the role changes the host. The repository MUST NOT provide a command that renders the bundled pages into an operator tree.

#### Scenario: Old tree layout

- **WHEN** the variable names a directory with `index.html` at its top level and no `site/` directory
- **THEN** the role fails before any host change with a message that names the expected layout.

#### Scenario: Removed render target

- **WHEN** an operator runs `make public-site-render`
- **THEN** Make reports that the target does not exist.
