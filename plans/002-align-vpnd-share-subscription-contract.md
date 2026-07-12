# Plan 002: Align `vpnd share` with the subscription server route contract

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` — unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- vpnd/src/commands/share.rs vpnd/tests/share_bundle.rs vpnd/tests/share_command.rs vpnd/tests/recipient_render.rs tests/unit/test_vpnd_share_subscription_contract.py`
> If any existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`vpnd share` currently generates two incompatible forms of the same subscription URL. Its displayed URL and generic URI QR use `/sub/<token>`, while the sing-box deep link and sing-box QR append `.json`; nginx and the loopback subscription service accept only the suffix-free route. The CLI also accepts any non-empty or empty length as long as every character is in the base64url alphabet, while both serving layers require 16–64 characters. As a result, generated recipient bundles can contain guaranteed-404 import links, and the current end-to-end Rust test uses a 14-character token the server rejects.

## Current state

- `vpnd/src/commands/share.rs` builds subscription URLs and validates token input.
- `vpnd/tests/share_bundle.rs` directly tests `build_sub_urls` and currently locks in `.json` for sing-box surfaces.
- `vpnd/tests/share_command.rs` exercises the complete share command with a private token file, but its token is shorter than the server minimum.
- `vpnd/tests/recipient_render.rs` contains a canonical recipient fixture whose sing-box link still uses `.json`.
- `ansible/roles/subscription-host/templates/subscription.conf.j2:29` and `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2:48` independently enforce the same route regex: `/sub/([A-Za-z0-9_-]{16,64})` with no suffix. These server files are evidence and must not be modified by this plan.
- Repository tests commonly use narrow source-contract checks under `tests/unit/` to keep cross-layer declarations synchronized; follow `tests/unit/test_vpnd_cargo_deny_contract.py` as the structural pattern.

Current excerpts:

```rust
// vpnd/src/commands/share.rs:23-30
pub fn build_sub_urls(base: &str, segment: &str) -> SubUrls {
    let subscription_url = format!("{base}/sub/{segment}");
    let singbox_deeplink = format!(
        "sing-box://import-remote-profile?url={}",
        urlencode(&format!("{base}/sub/{segment}.json"))
    );
    let qr_singbox = format!("{base}/sub/{segment}.json");
    let qr_uri = format!("{base}/sub/{segment}");
```

```rust
// vpnd/src/commands/share.rs:39-49
fn validate_token(token: &str) -> Result<()> {
    let valid = token
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-');
    if !valid {
        return Err(anyhow!(
            "token contains invalid characters — only base64url alphabet [A-Za-z0-9_-] is allowed"
        ));
    }
    Ok(())
}
```

```rust
// vpnd/tests/share_bundle.rs:198-215
assert_eq!(urls.subscription_url, "https://sub.example.com:8444/sub/abc123_XYZ-token");
assert_eq!(
    urls.singbox_deeplink,
    format!(
        "sing-box://import-remote-profile?url={}",
        share_urlencode("https://sub.example.com:8444/sub/abc123_XYZ-token.json")
    )
);
assert_eq!(urls.qr_singbox, "https://sub.example.com:8444/sub/abc123_XYZ-token.json");
assert_eq!(urls.qr_uri, "https://sub.example.com:8444/sub/abc123_XYZ-token");
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | `git diff --stat 7bdba37..HEAD -- vpnd/src/commands/share.rs vpnd/tests/share_bundle.rs vpnd/tests/share_command.rs vpnd/tests/recipient_render.rs tests/unit/test_vpnd_share_subscription_contract.py` | no output |
| Format | `mise exec -- cargo fmt --manifest-path vpnd/Cargo.toml -- --check` | exit 0 |
| Focused Rust tests | `mise exec -- cargo test --manifest-path vpnd/Cargo.toml --locked --test share_bundle --test share_command --test recipient_render` | all tests pass |
| Cross-layer contract test | `mise exec -- python3 -m pytest tests/unit/test_vpnd_share_subscription_contract.py -q` | all tests pass |
| Existing server behavior | `mise exec -- python3 -m pytest tests/unit/test_vpn_bootstrap.py -q` | all tests pass |
| Full Rust tests | `mise exec -- make vpnd-test` | exit 0, all Rust tests pass |
| Rust lint | `mise exec -- make vpnd-clippy` | exit 0, no warnings |
| Worktree check | `git status --short` | only in-scope files modified before commit; clean after commit |

## Scope

**In scope** (the only source/test files you should modify or create):

- `vpnd/src/commands/share.rs`
- `vpnd/tests/share_bundle.rs`
- `vpnd/tests/share_command.rs`
- `vpnd/tests/recipient_render.rs`
- `tests/unit/test_vpnd_share_subscription_contract.py` (create)

**Out of scope** (do not touch):

- Subscription-host nginx, Python service, defaults, role tasks, or Molecule scenarios; they already implement the intended contract.
- CLI argument definitions, completion snapshots, man pages, and token input mechanisms.
- Recipient HTML template layout or application cards.
- QR encoder implementation or output formats.
- `vpnd/README.md`, `vpnd/CLAUDE.md`, and broader subscription documentation; this plan corrects implementation and stale test fixtures without changing the established documented token-input design.
- Any dependency or lockfile change.

## Git workflow

- Branch: `codex/advisor-002-vpnd-share-contract`
- Make one focused Conventional Commit after all gates pass: `fix(vpnd): align share subscription routes`
- Stage only the five in-scope files.
- Do not push, merge, or open a PR.

## Steps

### Step 1: Build every share surface from one canonical route

In `vpnd/src/commands/share.rs`, keep the canonical route as `subscription_url = format!("{base}/sub/{segment}")`. Build the sing-box deep link by percent-encoding that exact `subscription_url`; do not independently reconstruct the route. Set both QR payload fields to the same suffix-free route while preserving the existing `SubUrls` fields and caller behavior.

The resulting invariants must be:

- `subscription_url == qr_singbox == qr_uri`.
- Decoding the `url=` value in `singbox_deeplink` yields `subscription_url` exactly.
- No generated subscription route contains `.json`.

Do not rename or remove `SubUrls` fields in this bug fix.

**Verify**: `mise exec -- cargo fmt --manifest-path vpnd/Cargo.toml -- --check` → exit 0.

### Step 2: Enforce the server's token grammar and bounds

In `vpnd/src/commands/share.rs`, define named constants for the server bounds (`16` and `64`) near the share URL code. Update `validate_token` so a token is accepted only when:

- Its length is between 16 and 64 inclusive.
- Every character is ASCII alphanumeric, `_`, or `-`.

Return one clear error that includes the 16–64 requirement and allowed alphabet. Add an internal `#[cfg(test)]` module in `share.rs` that directly covers:

- 15 characters: rejected.
- 16 characters: accepted.
- 64 characters: accepted.
- 65 characters: rejected.
- Empty token: rejected.
- A token of valid length containing a forbidden character: rejected.

Do not make `validate_token` public solely for testing.

**Verify**: `mise exec -- cargo test --manifest-path vpnd/Cargo.toml --locked commands::share::tests` → all six boundary cases pass.

### Step 3: Replace fixtures that encode the broken route

Update `vpnd/tests/share_bundle.rs` so the canonical `build_sub_urls` test asserts all three route fields are the same suffix-free `/sub/<token>` URL and the decoded deep-link target matches it. Replace short token fixtures in route-contract tests with valid 16–64 character base64url tokens where the test describes a server-usable token. Remove comments claiming the subscription-host expects `.json` or that a client-name fallback is supported; the production command requires an opaque token.

Update `vpnd/tests/share_command.rs` to use a valid token of at least 16 characters. Strengthen the page assertion so it verifies the suffix-free URL and suffix-free encoded sing-box target, and rejects the obsolete `.json` target.

Update the canonical fixture in `vpnd/tests/recipient_render.rs` to use the suffix-free encoded sing-box target. Do not change generic QR encoder tests solely because their arbitrary payload string happens to end in `.json`; change only fixtures presented as the share/subscription contract.

**Verify**: `mise exec -- cargo test --manifest-path vpnd/Cargo.toml --locked --test share_bundle --test share_command --test recipient_render` → all tests pass.

### Step 4: Add a cross-layer drift guard

Create `tests/unit/test_vpnd_share_subscription_contract.py` following the concise source-contract style in `tests/unit/test_vpnd_cargo_deny_contract.py`. The test must read:

- `vpnd/src/commands/share.rs`
- `ansible/roles/subscription-host/templates/subscription.conf.j2`
- `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2`

Assert that both server boundaries retain `[A-Za-z0-9_-]{16,64}`, the Rust source retains named 16/64 bounds, and the `build_sub_urls` function body does not contain `.json`. Limit extraction of the Rust check to the `build_sub_urls` function rather than banning `.json` across the entire file, because `config.singbox.json` is a legitimate output filename.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_vpnd_share_subscription_contract.py tests/unit/test_vpn_bootstrap.py -q` → all tests pass.

### Step 5: Run full Rust gates and commit

Run the full locked release test and clippy gates. Review the complete diff and `git diff --check`, stage only the five in-scope files, and commit.

**Verify**:

- `mise exec -- make vpnd-test` → exit 0.
- `mise exec -- make vpnd-clippy` → exit 0.
- `git diff --check` → exit 0.
- `git show --stat --oneline HEAD` lists only the five in-scope files.
- `git status --short` is empty after commit.

## Test plan

- Private Rust unit tests cover exact token length boundaries and invalid characters.
- `share_bundle.rs` proves every URL/QR/deep-link surface resolves to the same suffix-free server route.
- `share_command.rs` proves a real server-valid token produces a usable recipient page and no obsolete `.json` import target.
- `recipient_render.rs` keeps the canonical landing-page fixture aligned.
- The new Python contract test prevents Rust, nginx, and the Python service from silently diverging on route suffix or token bounds.
- Existing `test_vpn_bootstrap.py` remains the functional server-side proof for valid and invalid token lengths.

## Done criteria

- [ ] `build_sub_urls` constructs `/sub/<token>` once and all share surfaces use it without `.json`.
- [ ] `validate_token` enforces ASCII base64url characters and inclusive 16–64 length.
- [ ] Boundary tests cover 15, 16, 64, 65, empty, and forbidden-character inputs.
- [ ] End-to-end share fixtures use server-valid tokens.
- [ ] The cross-layer source-contract test covers Rust, nginx, and the Python service.
- [ ] Focused Rust and Python tests pass.
- [ ] `mise exec -- make vpnd-test` and `mise exec -- make vpnd-clippy` pass.
- [ ] Exactly the five in-scope files are present in the implementation commit.
- [ ] The implementation branch is clean after commit.

## STOP conditions

Stop and report instead of improvising if:

- An existing in-scope file no longer matches the excerpts or changed after `7bdba37`.
- Current sing-box clients demonstrably require a `.json` suffix despite the server rejecting it; provide the evidence instead of changing the server route.
- The fix requires changing nginx, the subscription service, CLI arguments, generated completions, dependencies, or lockfiles.
- Full Rust gates fail for an unrelated pre-existing reason.
- A verification command fails twice after one reasonable correction within scope.
- Any real token, decrypted secrets file, provider credential, network service, or generated recipient bundle outside test temp directories becomes necessary.

## Maintenance notes

- The subscription URL is a bearer-secret route, not a filename. Future client import formats must wrap or encode the canonical URL rather than add client-specific suffixes.
- Keep token bounds synchronized across Rust, nginx, and the Python service; the structural test exists because these layers cannot share a compiled constant.
- Reviewers should reject future tests that use client names or sub-16-character placeholders as if they were server-valid subscription tokens.
