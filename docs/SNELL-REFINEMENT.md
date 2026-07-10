# Snell refinement evaluation

Snell is a RESEARCH-tier, staging-only transport candidate. It is disabled in every shipped profile, excluded from the main automatic selector, and never participates in protocol-liveness rotation decisions. The implementation compares the v4-compatible stream with Snell v6 default and unshaped traffic modes, both with fresh and reused connections.

## Deployment boundary

Enable `vpn.enable_snell` only on a non-production host that explicitly lists `snell` in `allow_research_roles`. Add TCP listeners 2443, 2444, and 2445 to that staging environment's typed `public_listeners` contract. The prerelease guard refuses `ENV=prod` while the role pins sing-box `v1.14.0-alpha.42`.

The optional same-node control endpoint requires nginx-xhttp and `snell.evaluation_enabled: true`. It serves fixed, uncompressed payload files under the secret `snell_secrets.evaluation_path_token`; access logging is disabled for that location.

## Running the matrix

Prepare a mode-0600 YAML file outside the repository with `probe_base_url`, optional `repetitions` and `timeout_seconds`, and the size ladder. Run `make snell-refinement BUNDLE=/secure/path/sing-box.json CONFIG=/secure/path/snell-refinement.yaml VANTAGE=tls-size-cliff-a` from the filtered client path being measured.

The report contains only the technical vantage ID, profile tags, timing/completion aggregates, timestamp, and configuration hash. The endpoint, PSKs, userkeys, server address, and organization/geography labels are never emitted or persisted.

## Interpretation and promotion

`blocked` requires fewer than two of three exact-size completions while the direct controls before and after each attempt pass. `throttled` requires successful transfers whose median duration reaches three times the same-size direct control. Failed controls make the result `unknown`; local runtime or authentication failures are errors rather than blocking evidence.

Promotion requires a stable upstream release, two technical vantages on three non-consecutive days, three independently rotated v6 PSKs, at least 95 percent exact completion through 32 KiB without the latency cliff, and evidence that Snell survives where an existing production transport is blocked or throttled. Promotion is a separate reviewed change that selects one variant and changes tier/selector policy; this evaluator never deploys, promotes, rotates, or edits routes.
