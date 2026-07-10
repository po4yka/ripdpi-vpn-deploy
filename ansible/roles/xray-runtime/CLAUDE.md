# role: xray-runtime

## Design decisions

This role owns installation of the SHA256-pinned Xray release and the `/usr/local/bin/xray` symlink. It owns no listener, configuration, user, or systemd service, so both the core Xray role and research probe targets can reuse one runtime.

## What's done well

- Release selection remains driven by the existing SOPS `xray.version` and architecture checksums.
- Installation is idempotent and validates the resulting binary before exposing the symlink.

## Pitfalls

- Do not add transport configuration or service restarts here; callers own those lifecycles.
- Keep both the prebuilt archive and explicit source-build paths here; adding an installation path to a caller would recreate pin drift.
