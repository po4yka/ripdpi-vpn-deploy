# role: geodata — Xray routing data files

## Design decisions

**SHA256-pinned dat file download** — `geosite.dat` and `geoip.dat` are
fetched from pinned release URLs with exact SHA256 checksums asserted.
`/latest/` URLs are rejected by a pre-flight assert; you must pin to a
concrete release artifact before enabling `vpn.enable_geodata`.

**Version-aware daily activation** — a systemd timer fires at 04:00 UTC
(+30 min random jitter) and runs `vpn-geodata-refresh.sh`, which re-downloads
and re-verifies the files. Xray v26.4+ receives `SIGHUP`; older or unknown
versions are restarted and must be active before the refresh succeeds.

## What's done well

- **Fail-closed on checksum mismatch** — `get_url` with `checksum:` refuses
  to place a corrupted or tampered file; the old dat stays in place.
- **Inactive Xray is tolerated** — the activation helper exits cleanly on
  geodata-only nodes where `xray.service` is not currently running.

## Pitfalls

- **The timer uses curl, not Ansible get_url** — the role installs curl
  explicitly before scheduling refreshes; Python downloads during converge
  do not prove the service's shell dependencies are available.

- **Pin must be updated on every upstream dat release** — stale SHA256 pins
  mean `get_url` will not update the file even when the URL changes. Bump
  `geodata.geosite_sha256` and `geodata.geoip_sha256` together with the URL.
- **Old Xray builds restart during refresh** — versions before v26.4 do not
  support safe geodata hot-reload, so active connections can briefly reset.
- **Timer fires even when dat files are unchanged** — idempotent but wastes
  bandwidth. Consider mirroring to a local cache if bandwidth is constrained.
