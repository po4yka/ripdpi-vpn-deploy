## Context

The audit found thirteen source defects. The current checkout is based on integrated main a14c339c. The approved scope is source repair, regression tests, documentation, PR and merge. External deployment and private operator inputs remain outside this change.

## Goals / Non-Goals

- Goal: close every confirmed finding with a regression and an explicit requirement-to-evidence mapping.
- Non-goal: optional upstream version upgrades, broader monitoring features, peer production changes or real infrastructure operations.

## Decisions

- Keep hardware migration additive. Resolve one existing hardware identity, preserve all existing recipients, use explicit SOPS configuration and stage each encrypted update before publication. Report failed migration rather than claiming success.
- Describe ordinary restic password wrapping separately from compromise re-key. A replacement uses a distinct local and remote generation; retirement follows successful recovery proof.
- Publish state ciphertext through a private sibling and an atomic no-replace hard link after successful encryption. Timestamp collisions preserve the prior snapshot.
- Authenticated HTTP rejects redirects. Notification URLs require HTTPS. Tests may use an explicit injected transport; production admission is unchanged by tests.
- Subscription delivery uses one versioned atomic envelope containing exact payload bytes and metadata, published by the installed service CLI. Readers retain legacy payload/sidecar support; current issuers require the installed publisher and fail safely on older hosts. The atomic document is preferred over legacy files. Mirror generations preserve this representation. Publisher admission retains service-user ownership, no-follow checks, fixed names and bounded input.
- Inherit the two Hysteria repairs and their regressions from integrated PR #328. Preserve the schema wire shape. Add semantic bundle checks with categorical diagnostics. Refuse unsupported RIPDPI Hysteria port hopping rather than silently stripping fields.
- The contract comparison includes both JSON examples. Synchronize their four synthetic key literals through `po4yka/RIPDPI#TST-1792309202117414` and merge the client fixture copy first. Client CI has no reverse main-branch comparison, so this sequence has no circular dependency.
- Keep malformed legacy expiry metadata in the existing expiry-unavailable audit category. Unsafe route and file authority stays state-unavailable; neither failure serves the payload. Test route modes match the role's exact 0700 policy.
- Strip both CR and LF from inventory base64 encoding. A CRLF encoder must not split the typed build-environment label into multiple host lines. Parser admission remains strict.
- Alert environment uses the same configured authority as finite-silence. Telegram parses bounded JSON flood errors and refuses premature retry when wait exceeds the request budget.
- SSH adds the supported OpenSSH 9.0 hybrid with classical fallback and removes finite-field DH. Renderer, ownership controller, source bundle and effective verifier must change together. No live convergence is performed.

## Contracts and ownership

- Secrets/backup worker: scripts/setup-yubikey-age.sh, scripts/backup-tf-state.sh, new narrowly scoped helpers, docs/AGE-RECOVERY.md, docs/SECRETS.md, docs/RUNBOOK-rotate.md and matching tests.
- HTTP/alerts worker: scripts/monitor-protocol-liveness.py, scripts/check-vultr-control-plane.py, scripts/check-amneziawg-arm64-upstream.py, a shared origin helper if needed, observability_control_plane alert/relay files, role notes and matching tests.
- Subscription worker: scripts/issue_sub_token.py, scripts/client_payload.py, scripts/validate-bundle.py, subscription-host runtime/publisher/templates/role notes, subscription docs and matching tests. No contract JSON shape changes.
- Primary: SSH baseline template/controller/verifier and tests; all task/OpenSpec files; shared scripts/CLAUDE.md and tests/CLAUDE.md integration; snapshots, final review and PR lifecycle.
- Workers do not commit, change task state or edit shared root notes. They report proposed shared-note paragraphs for serialized integration.

## Risks / Trade-offs

- Incorrect SSH compatibility can remove access; retain the existing recovery transaction and qualify effective policy before any separately authorized deployment.
- New subscription publishers require role convergence before issuance; failure on an old host is explicit and occurs before remote publication.
- Hardware access depends on serial/slot and recipient union; stage changes and retain the old encrypted document on failed verification.
- Current native runtime checks require pinned binaries or Linux Docker; missing local capability is recorded and the unchanged hosted CI must supply its required evidence.

## Migration Plan

Merge source only. Existing subscription files remain readable; upgraded publishers atomically write the envelope. No secret, repository, state or hardware migration is executed by this PR. Rollback code retains old encrypted generations. Review the full diff, run focused regressions then make check, native CI and structured security review before protected merge.
