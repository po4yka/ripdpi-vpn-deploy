## Context

PR 282 already contains the P1/P2 role corrections at a978be0a. Implement the
remaining audit improvements I07-I15 and F43 on that dedicated branch. The
current observability contract remains schema 2, staging-only and on rollout
hold; source repairs to retained recovery code do not reauthorize old deployment.

## Goals / Non-Goals

- Goal: bounded safe recipient history, independent device access, reliable
  activation/notification intent, complete metric counting and private gates.
- Goal: positive runtime proof and per-ID reconciliation of I01-I15/F43.
- Non-goal: providers, Terraform/cloud-init mutations, live credential actions,
  fleet rollout, real vendor registration or full unpublished DNS morphology.

## Decisions

- Bootstrap-only b1 tokens embed issuance epoch plus strong random bytes. A
  configurable bounded maximum lifetime is independent of mutable mirror expiry.
  Use one durable monotonic retired-before watermark before marker collection
  and an explicit marker-count ceiling. The watermark is based on the absolute
  supported 30-day lifetime, independent of current policy
  or a newer short-lived marker's expiry. Retain unexpired proof; shorter-policy
  records can occupy bounded admission capacity until that safe horizon. Cheap
  invalid/unknown/consumed request checks precede history traversal.
  Shared private locking orders admission,
  consumption and GC. Never collect fresh authority to satisfy capacity. Bound
  audit bytes/archives with private rename/create rotation and a persistent timer.
  Reject the legacy bootstrap format; subscription bearer identities are unchanged.
- Extend the existing per-nginx-unit transaction and geodata lock with durable
  desired/activated receipts. Hash canonical managed state, not private run paths.
  Persist a versioned owned phase journal and complete prior/desired authority
  before mutation. Recover interrupted known journals under the same lock by
  validated restoration/reactivation of prior authority, then normal convergence;
  alternatively roll forward only an exactly matching complete desired target.
  Reject foreign/malformed/unknown journals without deletion. Pending/missing
  activated fingerprints also force unchanged retry adoption, including Naive.
  Record activation only after adoption; test real process death before/between
  replacements, before/after activation and during recovery.
- Replace self-steal shared staging with memory-only TLS validation (same hostname,
  key matching and seven-day lifetime policy), and integrate immutable pair/pointer/
  vhost/removal under the existing nginx lock. No second publication authority.
- Replace Naive username/password scalars with clients[] containing name, username
  and independent strong password. Empty lists after last-device revocation omit
  forwarding completely and retain only the decoy site; never fake credentials
  or an unauthenticated default. Validate uniqueness before host mutation. Root
  integrates encrypted issuance/revocation and one-device credential readout with existing
  locking/registry patterns; no plaintext secret arguments or compatibility path.
  Both controller CI installers pin the reviewed stable SOPS 3.13.3 release and
  checksum, whose stdin update interface is exercised with real encrypted tests.
  Native JSON configuration avoids Caddyfile token escaping and environment
  interpolation entirely; the plugin's byte-slice authentication records preserve
  every allowed printable ASCII password. Exact native Caddy proves two clients, one revoked client, then
  last-client revocation with a healthy HTTP/2 decoy, including quote/backslash edges.
- Policy truncation recovery is already present at the baseline; add permanent
  regressions, without rewriting the correct implementation. Tailing observes
  same-inode size/offset and replacement identity. Reset
  only at actual truncation/replacement boundaries, keeping bounded parsing/state.
  Honeypot records total/minute observations before its log cap and separately
  exports suppressed logs; worker admission drops remain a distinct metric.
- Validate one normalized literal private host:port before monitoring mutation;
  loopback or explicitly approved local Tailnet addresses only. Reject argument
  injection, hostnames, wildcards and public addresses. Sender/verification consume
  that same endpoint even when installation and sender calls occur separately.
- Store recovery notification intent separately from healthy incident state. Retry
  on a bounded schedule through fresh pulses/restart and clear only after success;
  retain credential redaction, replay and generation/rollback invariants.
  Delivery is at-least-once across an ambiguous external acknowledgement; only
  known matching success retires intent and stale completion cannot discard it.
- Default Lynis reporting stays non-blocking. Opt-in requires enabled available
  successful scanning and a unique fresh validated machine report with no warning[]
  records. Stale/malformed/missing reports cannot assert clean acceptance. Check
  mode explicitly distinguishes prediction from a scan receipt.
- F43 uses stateful test boundaries around actual WARP role success/failure/recovery,
  removing the invented counter/manual increment. This is role reconvergence proof,
  not an automatic vendor retry handler or live Cloudflare acceptance.

## Contracts and ownership

- Terraform and cloud-init are unchanged; no new public listener or production
  dependency. Ansible owns runtime, SOPS owns encrypted device/grant material.
- Host worker: subscription-host, reality-self-steal, honeypot, monitoring,
  security_audit and WARP recovery fixture; directly related tests/role notes.
- Runtime worker: nginx transaction/geodata activation, Naive role/native auth,
  policy-ratelimit and observability_deadman; related tests/notes. Host self-steal
  consumes the shared transaction; changes to that interface are coordinated.
- Primary: secret schema/examples, scripts/vpnd and shared endpoint consumers,
  fixtures, snapshots, CI, docs and task/spec lifecycle. Workers request shared
  changes, never stage/commit, and preserve concurrent edits and P1/P2 source.

## Risks / Trade-offs

- Replay after GC -> intrinsic issuance lifetime plus durable watermark before
  deleting records; explicit unsafe-state/capacity refusal rather than lost proof.
- Interrupted activation -> resource lock, durable pending identity and post-adoption
  receipt, with unchanged retry and rollback tests.
- Credential contract break -> update all callers/fixtures; fail old format explicitly.
- Private listener mismatch -> normalize once and share the exact endpoint with sender.
- Scanner presentation drift -> parse fresh machine report and exercise actual supported
  package output; retain conservative failed/unavailable outcomes.
- Test fixtures -> use real parsers, systemd/filesystem and local sockets where required;
  never infer provider, external client or human acceptance from local success.

## Migration Plan

Update encrypted document structure through the reviewed scripts when separately
authorized, issuing fresh bootstrap grants and per-device Naive credentials. Old
bootstrap formats/scalar pairs are rejected; no old-caller fallback is retained.
Retained consumption/replay state is migrated only by proved owned retirement.
Deployment/rollback remains a separate scope with private inputs and current
acceptance gates. Validate focused boundaries, relevant Molecule, native positive
and interrupted/interleaved behavior, 150+ reviewed snapshots, schema/coverage/
profile/listener checks, full build-gated make check, independent review and
all exact-source hosted checks before completing the PR extension.

## Review correction contracts

- Register descriptor ownership immediately and close on every exceptional exit; retain no-follow inode/ancestor gates. Runtime log/state consumers use owner-only 0600 where no separate group reader is required. Xray files begin private, then receive only the validated dedicated writer/group contract; the capability-bounded policy reader receives that exact supplementary group rather than unrestricted DAC privileges.
- Explicitly require TLS 1.2 or newer in runtime probes and native test clients; certificate and identity checks remain intact.
- Tests use named file-type-aware Jinja rendering. HTML/XML inputs escape markup; shell, JSON and unit inputs retain format-specific quoting without HTML entity corruption. No CodeQL exclusion or alert suppression is introduced.
- Selected Naive readout writes an explicitly requested new private 0600 artifact in an owner-controlled non-writable directory. Standard output contains only categorical operation metadata and the artifact path; caller contract requires OUTPUT for naive-readout. No stdout compatibility path or plaintext credential argv is retained.
