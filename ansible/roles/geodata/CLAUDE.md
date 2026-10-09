# role: geodata — Xray routing data files

## Design decisions

**SHA256-pinned dat file download** — `geosite.dat` and `geoip.dat` are
fetched from pinned release URLs with exact SHA256 checksums asserted.
`/latest/` URLs are rejected by a pre-flight assert; you must pin to a
concrete release artifact before enabling `vpn.enable_geodata`.

**Controlled daily activation** — a systemd timer fires at 04:00 UTC
(+30 min random jitter) and runs `vpn-geodata-refresh.sh`, which re-downloads
and re-verifies the files. Active Xray is restarted and must be active before
the refresh succeeds; no inferred version threshold authorizes unsupported HUP.

**Geodata is one verified pair** — convergence and the timer use the same
publisher. Both pinned files verify before either current file changes; ordinary
activation failure restores prior bytes/modes and reactivates the complete old
pair. Failed rollback retains a private pending pair and blocks reuse. Disabling
stops scheduling while retaining these recovery and data files.

## What's done well

- **Fail-closed on checksum mismatch** — the paired publisher checks both SHA256 digests and refuses
  to place a corrupted or tampered file; the old dat stays in place.
- **Inactive Xray is tolerated** — the activation helper exits cleanly on
  geodata-only nodes where `xray.service` is not currently running.

## Pitfalls

- **One publisher at a time** — a root-owned no-follow lock serializes convergence and timer work. Rooted directories and single-link regular current files are checked before metadata or byte writes.


- **The timer uses curl, not Ansible get_url** — the role installs curl
  explicitly before scheduling refreshes; convergence and timer use the same curl-backed publisher.

- **Pin must be updated on every upstream dat release** — stale SHA256 pins
  mean the publisher will not update the file even when the URL changes. Bump
  `geodata.geosite_sha256` and `geodata.geoip_sha256` together with the URL.
- **Active Xray restarts during refresh** — no supported hot-reload contract
  is assumed, so active connections can briefly reset.
- **Timer fires even when dat files are unchanged** — idempotent but wastes
  bandwidth. Consider mirroring to a local cache if bandwidth is constrained.
- **A fresh check-mode host has no geodata directory or timer yet** — require
  their planned creation and check the pinned URLs with read-only HEAD requests.
  Defer downloads and activation only until real convergence can write their
  destinations and verify both SHA256 pins.
