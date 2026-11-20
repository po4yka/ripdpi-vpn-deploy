# role: public-site — scheduled publication of an operator site bundle

## Design decisions

**The node selects, the controller renders** — `make public-site-build` renders every generation of the site (generation `n` holds the first `n` scheduled articles) into `backlog.tar.gz`. `files/public_site_publish.py` compares `schedule.json` with the clock, extracts generations `0..n` over each other and swaps the `current` link. The served bytes and file times depend only on the bundle and the clock, so a recreated node shows the same pages with the same dates. No template engine, model key or network access exists on the node.

**State is keyed by the archive digest** — `/etc/public-site/<sha256>/` holds the delivered archive and schedule, `/var/lib/public-site/<sha256>/current` the served generation. A vhost names the digest path, so the role publishes before the vhost activates and a vhost rollback points at the previous digest, which is still present. The role never removes state itself, because it runs before the vhost roles and an active or restored vhost still names the previous digest. It sets `_public_site_remove_after_commit` (`retire` or `absent`), and the caller runs that task file with `tasks_from` after its vhost activation has succeeded, or after the commit inside a protected ingress transaction.

**No operator toggle** — `site.yml` runs the role first in its tasks, before any vhost is rendered, with the bundle directories of the enabled vhost roles; it runs the removal after the protected ingress commit. The role acts when a bundle has an archive. `public_site_bundle_dirs` receives those directories; an empty list, or bundles without `backlog.tar.gz`, removes the units, state and user. The role exports `public_site_published` (bundle directory to digest) for the vhost roles.

**Unpublished generations stay private** — the archive is `root:public-site` 0640 below a 0750 directory, and the state directory is `public-site:www-data` 2750 with `UMask=0027`, so nginx reads only the extracted generation. The publisher keeps one generation directory and removes the earlier one after the switch.

**A live page is a second unit with its own directory** — a bundle may declare one top-level page (`live.json`: page, sources, markup). Each bundle has its own instance `public-site-live@<digest>.timer`, so an outage of one bundle's sources does not stop another bundle's page. The instance runs the same refresher as the bundled news page (`../nginx-xhttp/files/model-news/refresh_model_news.py`, one script and one set of guards) with the page shell from the served generation, and writes `/var/lib/public-site-live/<digest>/<page>`. The unit files hold no text from a bundle: the instance name is the digest and the script reads the page name from `live.json` and refuses anything but a file name. `live-retire.yml` removes the instances, pages and unit files that no bundle declares, and like `retire.yml` it runs only after the vhost activation. It needs the network, so it is not the publisher unit: `ReadWritePaths` is only the live directory, and the publisher's state stays read-only for it. A vhost serves the page from the live directory and falls back to the generation's shell until the first refresh, so the deploy seeds nothing and waits for no source. The role exports `public_site_live` (bundle directory to digest and page). The bundle supplies the markup and the sources, because one source list or one markup on many nodes gives them one identical page; `public-site-check` refuses the bundled ones.

## What's done well

- The unit has no network (`PrivateNetwork=true`, `RestrictAddressFamilies=none`), no capabilities, and writes only `/var/lib/public-site`.
- The publisher verifies that the archive digest equals its directory name and refuses the whole archive for one member that is not a regular file below `generations/<n>/`. A refused bundle keeps its served generation and does not stop the other bundles.
- The deploy starts the installed unit once and then requires a served generation for each bundle that it names, so a failed sandboxed run stops the deploy before a vhost names an absent generation. A refused bundle that only waits for removal fails the unit but not the deploy.
- Every run removes all generation directories except the served one, so an interrupted run leaves no unpublished article readable.

## Pitfalls

- With managed TLS the TCP/80 server belongs to the public-tls owner, which is not part of the ingress rollback. After a failed deploy it can name the new digest while the HTTPS vhost names the previous one; both exist on the host, and the next deploy renders it again.

- A vhost reads only the served generation: there is no second lookup in the transaction tree. If the state directory is lost, the site answers 404 until the timer rebuilds it, within its interval.
- The archive is gzip with a fixed header time. Another zlib build can give other bytes for the same input, and then a new digest; the node then receives the bundle again and serves the same pages.

- The start of the oneshot unit reports no change on purpose: its result is a function of the clock. Do not turn it into a handler; the generation must exist before the vhost roles run.
- Generation 0 is served before its scheduled time, because the vhost already serves the same pages from `site/`.
- Do not add a clock or generation override to the publisher for tests; `tests/unit/test_public_site_publisher.py` controls `schedule.json` instead.
- `RandomizedDelaySec` and `Persistent=true` matter: a fleet must not switch in the same second, and a node that was down publishes when it returns.
