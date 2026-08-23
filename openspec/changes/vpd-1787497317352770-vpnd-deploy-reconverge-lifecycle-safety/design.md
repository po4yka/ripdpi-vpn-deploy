# Design

## Boundaries

- Rust-only change in vpnd/. Make targets and ansible inventory semantics unchanged; the CLI contract for --limit inputs tightens.

## Decisions

- Failure cleanup: wrap step loops so Err from any step triggers a best-effort cleanup invocation before returning the original error; explain mode skips cleanup execution like other steps.
- Limit validation uses strict IPv4 parsing (std::net::Ipv4Addr) — no pattern metacharacters can survive.
- Host resolution reuses Registry::get with env/provider match identical to reconverge's existing logic, extracted into a shared helper.
- Summary rows render fixed placeholders instead of paths.

## Rollback

Single-commit revert restores prior behavior including the fleet-widening footgun; acceptable because the tightened behavior is strictly safer.

## Validation

Unit tests: failure-injection asserting cleanup runs after a failed middle step; ipv4 rejection table (all, prod:*, 999.1.1.1); unknown-host errors for doctor/probe; summary snapshot showing placeholders. cargo clippy -D warnings.
