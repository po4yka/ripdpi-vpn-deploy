---
name: rust-best-practices
description: Idiomatic Rust for the vpnd convenience CLI — clippy gates, error strategy, snapshot tests, no panics outside tests. vpn-deploy project variant of the Apollo handbook.
---

# Rust Best Practices (vpn-deploy)

Applies to `vpnd/src/**`. The crate is a small async CLI; rules below are tighter than a
generic Rust library because this binary runs against production secrets and infrastructure.

## Project context

- One binary crate: `vpnd/`. No library split (yet). Workspace single member.
- Error strategy: `anyhow::Result<T>` end-to-end. No custom error enum unless we expose a
  library boundary.
- Tests: unit + `cargo insta` snapshots for rendered output. Snapshots live in
  `vpnd/tests/snapshots/`. Run `cargo insta review` before committing.
- CI: `cargo check`, `cargo test`, `cargo clippy --all-targets --all-features -- -D warnings`.
- Version pin moves through release-please — do not bump `Cargo.toml` by hand.

## Hard rules

- **No `unwrap()` / `expect()` outside `#[cfg(test)]`.** Use `?` with `.context(...)`.
- **No `panic!` / `todo!()` / `unimplemented!()` in shipped paths.**
- **No `println!` for user output** — go through the `Context`'s stdout handle so snapshot
  tests can capture it deterministically.
- **No new dependencies without a vendoring reason** — this is a small CLI; pulling in
  `reqwest` or `sqlx` is almost never justified.
- **Pinned Rust edition + MSRV** in `Cargo.toml`. Pre-releases through staging only (root
  `CLAUDE.md` rule).

## Borrowing & ownership

- Prefer `&str` over `String` in function params. Use `Cow<'_, str>` only when ownership is
  genuinely ambiguous.
- Subcommand args are `Clap`-derived structs — pass by reference (`args: &FooArgs`) to
  `run()` handlers.

## Error handling

```rust
use anyhow::{Context, Result, bail};

pub async fn run(ctx: &Context, args: &DeployArgs) -> Result<()> {
    let inventory = render_inventory(&args.profile)
        .await
        .with_context(|| format!("rendering inventory for profile {}", args.profile))?;

    if inventory.hosts.is_empty() {
        bail!("inventory has no hosts for profile {}", args.profile);
    }
    Ok(())
}
```

Always include the operator-facing nouns in `with_context` — profile name, host, file path.

## Clippy

These lints are CI-fatal:

- `clippy::unwrap_used` — see hard rule above
- `clippy::expect_used` — same
- `clippy::panic` — same
- `clippy::large_enum_variant` — `Command` enum should box heavy variants
- `clippy::redundant_clone` — `&str` first, `.clone()` only with reason

Use `#[expect(clippy::lint, reason = "...")]` instead of `#[allow]`. Justifications are required.

## Tests

- Name tests by behaviour: `deploys_only_listed_hosts`, not `test_deploy`.
- One assertion per test where practical.
- Snapshot tests for rendered output (`recipient.html`, subscription content, deploy summary).
  Snapshots are reviewed manually before commit; never run `cargo insta accept` blindly.
- No real network, no real subprocess in unit tests. Use `tempfile` for fixtures.

## Documentation

- `///` doc comments on public items in `lib.rs` if a lib crate is added.
- `//` comments only for *why* — invariants, workarounds. Don't restate what the code does.
- No `TODO` without a tracked issue: `// TODO(#42): ...`.

## See also

- `vpnd/CLAUDE.md` — design decisions, what's done well, pitfalls
- `[[rust-async-patterns]]` — tokio + error handling for vpnd specifically
- Upstream reference chapters in `~/.agents/skills/rust-best-practices/references/`
