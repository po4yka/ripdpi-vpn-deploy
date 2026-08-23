# Design

## Boundaries

- Only vpnd Rust sources and tests change. Subscription URL shape (https://host/sub/token) is unchanged; recipient pages keep their template.

## Decisions

- Empty-token rejection lives inside validate_token so stdin and token-file sources share one gate.
- The (unset) fallback becomes a hard error naming which secrets key was missing (subscription.server_name vs nginx_xhttp.server_name).
- write_private gains OpenOptions .mode(0o600), replaces an existing stale temp instead of failing on AlreadyExists, and cleans up its own temp on write failure; qr::write_svg routes through the same helper.

## Rollback

Single-commit revert restores prior behavior; previously written bundles keep working because URL shapes are unchanged.

## Validation

Focused cargo test runs over tests/share_bundle.rs and tests/share_command.rs plus new cases: empty token via stdin and file, unset host, stale-temp recovery, file modes of every bundle artifact; cargo clippy -D warnings.
