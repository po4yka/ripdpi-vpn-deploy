# role: subscription-host — static-payload subscription delivery

## Design decisions

**Bounded bootstrap history** — bootstrap grants use `b1_<10-digit-issued-epoch>_<43-character-random>`; legacy bootstrap formats are refused. Intrinsic maximum lifetime is independent of restored expiry metadata. Private request/maintenance locking serializes admission, consume and GC. The durable monotonic retired-before fence commits before removing expired markers, so restoring old payloads, increasing the configured lifetime or rolling the clock backward cannot revive retired URIs. Capacity never discards fresh consumption authority. Compaction uses the conservative 30-day maximum supported lifetime, independently of the currently selected shorter policy or an expired marker; expired short-lived records remain until that replay-proof horizon retires their issuance. Cheap format/fence and direct known/consumed checks precede full history scanning, so rejected guesses do not trigger O(history) GC. Ordinary subscription tokens retain their existing format. Legacy empty markers remain conservative consumed authority; migration does not guess their issuance and may require explicit reviewed retirement when they occupy capacity. Missing lock/fence is provisioned only for a genuinely new payload namespace without an installed bootstrap runtime. Retained or partially initialized state refuses missing authority instead of resetting replay proof; recovery/migration must restore or establish separately reviewed authority.

**Audit bounds** — append uses private no-follow files and a separate writer lock, rotates by configured bytes/archive count, and trims oversized historical files to complete trailing records. Policy contractions reconcile all fourteen supported archive names under the same writer lock, validate the whole set before writes, and remove only safe owned excess archives. A persistent five-minute maintenance timer collects retired markers and reconciles audit size bounds; disable retires that timer while preserving replay authority.

**Independent TLS ownership** — `subscription.cert_pem` and `subscription.key_pem` are required independently of XHTTP. The memory-only preflight proves key match, current validity and the effective delivery hostname before complete nginx transaction publication under `/etc/nginx/tls/subscription-host/`. An existing check-mode host performs the same preflight; a fresh missing validator requires its package installation plan.

**Bearer failures retain only categorical diagnostics** — bearer locations suppress URI-bearing nginx error records and use an explicit format containing only HTTP status, upstream status and limit outcome. No URI, header, address or token field enters this log; native stopped-upstream and rate-limit tests check every nginx log.


**v1 = nginx vhost with static payloads** — `/sub/<token>` returns the
client's sing-box JSON; `/bootstrap/<token>` is a one-time provisioning URL.
Revocation + rate-limit (v1.2) is a thin Lua module on top.

**Can run on a separate VPS** — `vpn_subscription_only: true` deploys *only*
this role + nginx + firewall on a host. Isolates compromise blast radius
from the proxy host. See `docs/SUBSCRIPTION-HOST-SEPARATION.md`.

**Audit log** — successful and rejected token fetches retain JSONL route, timestamp, hash prefix, source IP and byte count. Owner-only files and bounded rotation protect this local metadata; the payload and plaintext token are excluded. See `scripts/sub-reads.sh`.

**Revocation is provisioned authority** — startup never creates a missing deny
list. Startup and each request require a readable regular single-link 0600 file
owned by the service account, reject symlinks and malformed entries, and fail
closed if authority is lost. Convergence owns initial authority publication.
Token-bearing share directory and bundle operations set both `no_log` and
`diff: false`, including loops and verbose callbacks.

## What's done well

- **Token store is local-only** — never leaves the host. Bootstrap tokens
  are one-shot (consumed on read); subscription tokens persist with optional
  TTL.
- **Tokens are hashed-at-rest** — SHA-256 hex digest. The inbound URL token is a high-entropy opaque random value (128–384 bit); a plain hash is adequate and avoids KDF overhead on the hot path.
- **Share-bundle ingest is zero-trust on nginx** — `tasks/share-bundles.yml`
  copies operator-built bundles (`ansible.builtin.copy`) to `/var/www/subscription-host/share/<token>/`
  with `access_log off` on the location; the raw token never appears in any
  nginx log line.

## Pitfalls

- **Fresh check mode plans units without installing them** — read the actual
  systemd load state and require the exact template's planned change before
  deferring an absent bootstrap service's activation and restart. Loaded units
  retain normal service checks; unknown or failed discovery refuses.
- **Reverse proxy in front breaks rate-limit** — if you put a CDN between
  the recipient and the subscription host, the rate-limit keys on the wrong
  IP. Either disable rate-limit or set `set_real_ip_from` correctly.
- **Bootstrap URL leak via referrer** — never embed in an HTML page that
  links to external sites. The role's templates set `Referrer-Policy: no-referrer`.
- **Log format must be machine-stable** — `sub-reads.sh` parses with `jq`;
  changing the access log format silently breaks the audit pipeline.
- **`vpn_subscription_only` host has NO proxy** — don't co-locate. The
  whole point is blast-radius separation.
- **Expiry instants preserve explicit offsets** — normalize new issuance to UTC, treat legacy naive timestamps as UTC, keep numeric epoch sidecars compatible, fail closed on invalid metadata, and expire exactly when `now >= expires`.
- **Keep response headers at server scope** — every delivery route inherits
  the same no-store and security baseline. Any child `add_header` suppresses
  that entire inherited set on supported nginx versions. Hide the backend
  copies of Cache-Control, Referrer-Policy, and X-Robots-Tag at nginx so
  successful responses and errors expose one authoritative public value.
- **Mirror exclusions follow `revoked_file`** — changing its basename or
  nesting it inside the payload root must not let `rsync --delete` remove it.
- **Restic restores must expose `DEST/sub` directly** — the mirror refuses a
  missing or symlinked root `sub/` before recursive ownership or mode repair,
  so unexpected snapshot nesting cannot leave stale payloads served silently.
  The snapshot must be created with the payload tree as its root — run
  `restic backup` from the payload-tree parent with relative paths (e.g.
  `restic backup sub bootstrap`) so the snapshot root holds `sub/` (mandatory)
  and `bootstrap/` (optional; auto-created) directly. `restic restore latest
  --target <stage>` then reproduces that root at the stage root; the mirror's
  `restic_snapshot_path` is only a restore `--include` filter over
  snapshot-internal paths and cannot flatten a hierarchy. A snapshot taken
  from an absolute host path (e.g. `/var/lib/vpn-subscription`) restores as
  `<stage>/var/lib/...` and fails closed as an unexpected root entry.
- **Mirror routes share one generation pointer** — `sub/` and `bootstrap/`
  are validated, hardened and fsynced beneath one private immutable generation
  before the single current-pointer rename. A prior generation is retained for
  in-flight readers. The publisher lock serializes pull through cleanup; once
  the generation root exists, a missing pointer fails closed instead of serving
  stale legacy payload. Direct deployments create neither mirror artifact.
