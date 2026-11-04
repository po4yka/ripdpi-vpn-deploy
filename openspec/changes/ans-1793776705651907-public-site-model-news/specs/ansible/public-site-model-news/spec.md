## Purpose

The public site served by the nginx-xhttp role shows a periodically refreshed list of open-model news that comes only from pinned public sources, never republishes upstream text, never carries transport vocabulary, and never breaks the site when a source fails.

## ADDED Requirements

### Requirement: REQ-NEWS-SOURCES — Pinned HTTPS sources only

The refresh MUST fetch only the sources listed in the role configuration, MUST refuse any source, redirect target or entry link that is not HTTPS, MUST cap each response body at 2 MiB and 20 seconds, and MUST refuse a feed document that declares a DTD in any encoding.

#### Scenario: Source with a DTD

- **WHEN** a configured feed returns a document with a `<!DOCTYPE` or `<!ENTITY` declaration
- **THEN** that source is skipped and the other sources still render.

#### Scenario: Plain-HTTP entry link

- **WHEN** an entry links to an `http://` address
- **THEN** the entry does not appear on the page.

### Requirement: REQ-NEWS-CONTENT — Titles and links only, escaped

The page MUST show only an entry's title, source name, date and link, MUST HTML-escape every upstream value, MUST order each section newest first, MUST remove duplicate links, and MUST keep at most 30 entries per section.

#### Scenario: Markup in a title

- **WHEN** an upstream title contains `<script>`
- **THEN** the page shows the literal text and contains no script element from upstream.

### Requirement: REQ-NEWS-NEUTRAL — No transport vocabulary

The refresh MUST drop every entry whose title or link contains a term that the public site contract forbids (`vpn`, `proxy`, `xray`, `hysteria`, `amnezia`, `/admin`, `/metrics`, `/health`), compared after Unicode NFKC normalization and case folding.

#### Scenario: Forbidden term in a headline

- **WHEN** a headline contains "VPN"
- **THEN** the entry is not rendered.

### Requirement: REQ-NEWS-FAILURE — A failed refresh keeps the last page

The refresh MUST replace the page atomically, MUST keep the previous page when no source yields an entry, and MUST exit non-zero in that case so the systemd unit reports the failure. The role MUST seed an empty-state page that it never overwrites, so `/news.html` exists before the first refresh.

#### Scenario: All sources unreachable

- **WHEN** every source fails
- **THEN** the served page is byte-identical to the previous one and the service unit is in a failed state.

### Requirement: REQ-NEWS-TOGGLE — Toggle owns the whole surface

With `nginx_xhttp_model_news_enabled: true` on a host that serves the bundled site the role MUST install the script, the hardened service and the timer, serve `/news.html` and link it from the site navigation. With `false`, or with an operator-owned site, it MUST stop and remove the timer and service, remove the state directory, and render no navigation link to `/news.html`.

#### Scenario: Operator-owned site

- **WHEN** `nginx_xhttp_public_site_dir` is set
- **THEN** no vhost serves `/news.html` and no model news unit exists, because the page carries the bundled identity.

#### Scenario: Feature disabled

- **WHEN** the toggle is false
- **THEN** no page links to `/news.html` and no model news unit exists on the host.

### Requirement: REQ-NEWS-ISOLATION — Unprivileged, read-only refresh

The service MUST run as a dedicated system user with no capabilities, a read-only system view, and write access only to its state directory.

#### Scenario: Unit hardening

- **WHEN** the service unit is rendered
- **THEN** it sets a dedicated `User`, an empty `CapabilityBoundingSet`, `ProtectSystem=strict`, `NoNewPrivileges=true`, and `ReadWritePaths` limited to the state directory.
