# role: xray-runtime

## Design decisions

This role owns installation of the SHA256-pinned Xray release and the `/usr/local/bin/xray` symlink. It owns no listener, configuration, user, or systemd service, so both the core Xray role and research probe targets can reuse one runtime.

The optional source path requires an exact checkout commit and distinct amd64
and arm64 source-built binary SHA256 values, then selects the native digest and
records it with the canonical Go recipe in the shared runtime-build receipt.
Its checkout path is keyed by that commit and never updated in place, while
compilation targets the private transaction stage; the helper publishes only
verified native bytes. The existing
`vpn.build_xray_from_source` boolean remains the selection input.

## What's done well

- Release selection remains driven by the existing SOPS `xray.version` and architecture checksums.
- Installation is idempotent and validates the resulting binary before exposing the symlink.

## Pitfalls

- Do not add transport configuration or service restarts here; callers own those lifecycles.
- Keep both the prebuilt archive and explicit source-build paths here; adding an installation path to a caller would recreate pin drift.
