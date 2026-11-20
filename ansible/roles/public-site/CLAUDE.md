# role: public-site — scheduled publication of an operator site bundle

## Design decisions

**The node selects, the controller renders** — `make public-site-build` renders every generation of the site (generation `n` holds the first `n` scheduled articles) into `backlog.tar`. `files/public_site_publish.py` compares `schedule.json` with the clock, extracts generations `0..n` over each other and swaps the `current` link. The served bytes and file times depend only on the bundle and the clock, so a recreated node shows the same pages with the same dates. No template engine, model key or network access exists on the node.

**State is keyed by the archive digest** — `/etc/public-site/<sha256>/` holds the delivered archive and schedule, `/var/lib/public-site/<sha256>/current` the served generation. A vhost names the digest path, so the role publishes before the vhost activates and a vhost rollback points at the previous digest, which is still present. The role never removes state itself, because it runs before the vhost roles and an active or restored vhost still names the previous digest. It sets `_public_site_remove_after_commit` (`retire` or `absent`), and the caller runs that task file with `tasks_from` after its vhost activation has succeeded, or after the commit inside a protected ingress transaction.

**No operator toggle** — the role runs when an enabled vhost role names a bundle that has an archive. `public_site_bundle_dirs` receives those directories; an empty list, or bundles without `backlog.tar`, removes the units, state and user. The role exports `public_site_published` (bundle directory to digest) for the vhost roles.

**Unpublished generations stay private** — the archive is `root:public-site` 0640 below a 0750 directory, and the state directory is `public-site:www-data` 2750 with `UMask=0027`, so nginx reads only the extracted generation. The publisher keeps one generation directory and removes the earlier one after the switch.

## What's done well

- The unit has no network (`PrivateNetwork=true`, `RestrictAddressFamilies=none`), no capabilities, and writes only `/var/lib/public-site`.
- The publisher verifies that the archive digest equals its directory name and refuses the whole archive for one member that is not a regular file below `generations/<n>/`. A refused bundle keeps its served generation and does not stop the other bundles.
- The deploy starts the installed unit once, so a failure of the sandboxed run stops the deploy before a vhost names an absent generation. The unit fails for any refused bundle, including one that waits for removal.
- Every run removes all generation directories except the served one, so an interrupted run leaves no unpublished article readable.

## Pitfalls

- The start of the oneshot unit reports no change on purpose: its result is a function of the clock. Do not turn it into a handler; the generation must exist before the vhost roles run.
- Generation 0 is served before its scheduled time, because the vhost already serves the same pages from `site/`.
- Do not add a clock or generation override to the publisher for tests; `tests/unit/test_public_site_publisher.py` controls `schedule.json` instead.
- `RandomizedDelaySec` and `Persistent=true` matter: a fleet must not switch in the same second, and a node that was down publishes when it returns.
