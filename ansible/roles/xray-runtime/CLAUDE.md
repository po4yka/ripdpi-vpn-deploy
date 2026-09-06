# role: xray-runtime

## Design decisions

This role selects the SHA256-pinned Xray archive or source build while the
shared `runtime-release` contracts own archive extraction, receipts, and
`current`/public/`previous` publication. It owns no listener, configuration,
user, or systemd service, so both the core Xray role and research probe targets
can reuse one runtime.

The optional source path requires an exact checkout commit and distinct amd64
and arm64 source-built binary SHA256 values, then selects the native digest and
records it with the canonical Go recipe in the shared runtime-build receipt.
Its checkout path is keyed by that commit and never updated in place, while
compilation targets the private transaction stage; the helper publishes only
verified native bytes. The existing
`vpn.build_xray_from_source` boolean remains the selection input.

When the separately pinned geodata role is disabled, this role publishes the
archive's bundled `geoip.dat` as a hash-pinned read-only runtime asset below
the Xray install root. The geodata role remains the sole owner of
`/usr/local/share/xray`; toggling it cannot collide with a fallback symlink.

## What's done well

- Release selection remains driven by the existing SOPS `xray.version` and architecture checksums.
- Archive installation is idempotent and validates the resulting binary through
  the shared runtime receipt before exposing the symlink.

## Pitfalls

- Do not add transport configuration or service restarts here; callers own those lifecycles.
- Keep both the prebuilt archive and explicit source-build paths here; adding an installation path to a caller would recreate pin drift.
- Capture binary and asset publication results separately; the final change
  signal must not be overwritten by the second shared-role include.
