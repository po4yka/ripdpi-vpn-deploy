# Change: Publish a refreshed open-model news page and expand the public site

Task ID: `ANS-1793776705651907`

## Why

The bundled public site served by `nginx-xhttp` has three articles and no change since July 2026. Its subject (model evaluation in general) does not match the domain theme (Chinese language models), and nothing on it changes between deployments. A small, honest source of fresh content and a larger set of real pages make the site read as a maintained reference instead of a static placeholder.

## What Changes

- A node-local systemd timer fetches a pinned list of public HTTPS sources (Hugging Face model listings for selected Chinese model organizations and one RSS headline feed) and renders `/news.html`. The page holds only titles, source names, dates and links; upstream text is never republished.
- Entries that contain transport vocabulary are dropped, so the public site stays free of those terms even with third-party content.
- A failed refresh keeps the previous page. A fresh host serves an empty-state page until the first refresh succeeds.
- The feature is a role default toggle, `nginx_xhttp_model_news_enabled` (default `true`), overridable from group or host vars. When it is `false`, the role removes the timer, the state and the navigation link.
- New static content: three notes about open-weight Chinese models, an archive page grouped by topic, a glossary, and a model tracker built only from primary-source facts. The update log, Atom feed, sitemap and home page record this publication.
- Host egress gains periodic outbound HTTPS requests to `huggingface.co` and the headline feed host.

## Capabilities

### New Capabilities

- `ansible/public-site-model-news`: refreshed news page, its sources, filtering, failure handling and toggle.

### Modified Capabilities

- None. `security/traffic-metadata-and-decoy-identity` keeps its requirements; operator-owned production trees still replace the bundled pages.

## Impact

- Ansible role `nginx-xhttp`: new script, systemd service and timer, nginx location for `/news.html`, new bundled pages, defaults, and removal on disable.
- Host egress: outbound TCP/443 to the pinned sources every six hours, inside the existing strict egress policy.
- No Terraform, secrets, vpnd or client contract change.
