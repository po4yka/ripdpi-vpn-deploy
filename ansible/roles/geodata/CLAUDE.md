# role: geodata — Xray routing data files

## Design decisions

**SHA256-pinned dat file download** — `geosite.dat` and `geoip.dat` are
fetched from pinned release URLs with exact SHA256 checksums asserted.
`/latest/` URLs are rejected by a pre-flight assert; you must pin to a
concrete release artifact before enabling `vpn.enable_geodata`.

**Daily SIGHUP reload to xray** — a systemd timer fires at 04:00 UTC
(+30 min random jitter) and runs `vpn-geodata-refresh.sh`, which re-downloads
and re-verifies the files, then sends `SIGHUP` to `xray.service` so routing
tables reload without a full restart.

## What's done well

- **Fail-closed on checksum mismatch** — `get_url` with `checksum:` refuses
  to place a corrupted or tampered file; the old dat stays in place.
- **SIGHUP tolerates xray not running** — the handler ignores "not loaded /
  not found" errors so geodata-only converges don't fail on nodes where xray
  is temporarily stopped.

## Pitfalls

- **Pin must be updated on every upstream dat release** — stale SHA256 pins
  mean `get_url` will not update the file even when the URL changes. Bump
  `geodata.geosite_sha256` and `geodata.geoip_sha256` together with the URL.
- **SIGHUP reload requires Xray v26.4.x+** — older Xray versions silently
  no-op the reload. Operators on older Xray should disable this role until
  they upgrade.
- **Timer fires even when dat files are unchanged** — idempotent but wastes
  bandwidth. Consider mirroring to a local cache if bandwidth is constrained.
