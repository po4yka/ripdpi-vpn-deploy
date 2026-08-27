# role: subscription-host — static-payload subscription delivery

## Design decisions

**v1 = nginx vhost with static payloads** — `/sub/<token>` returns the
client's sing-box JSON; `/bootstrap/<token>` is a one-time provisioning URL.
Revocation + rate-limit (v1.2) is a thin Lua module on top.

**Can run on a separate VPS** — `vpn_subscription_only: true` deploys *only*
this role + nginx + firewall on a host. Isolates compromise blast radius
from the proxy host. See `docs/SUBSCRIPTION-HOST-SEPARATION.md`.

**Audit log** — every read is recorded (route, ts, token-hash, source ASN).
Decryptable only with the audit-log key. See `scripts/sub-reads.sh`.

## What's done well

- **Token store is local-only** — never leaves the host. Bootstrap tokens
  are one-shot (consumed on read); subscription tokens persist with optional
  TTL.
- **Tokens are hashed-at-rest** — SHA-256 hex digest. The inbound URL token is a high-entropy opaque random value (128–384 bit); a plain hash is adequate and avoids KDF overhead on the hot path.
- **Share-bundle ingest is zero-trust on nginx** — `tasks/share-bundles.yml`
  rsync's operator-built bundles to `/var/www/subscription-host/share/<token>/`
  with `access_log off` on the location; the raw token never appears in any
  nginx log line.

## Pitfalls

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
