# Design: Unbound staging client retirement

## Context

The normal disposable-liveness de-onboarding flow is intentionally bound to an
executor assignment. A failed or interrupted onboarding can leave a valid
`issued` client in SOPS while the binding, promotion, sentinel registry, and
executor profile never existed. Provider destruction can still be verified by
the canonical staging cleanup guard. The missing operation is an encrypted
identity recovery transaction, not a relaxed normal de-onboard.

## Decisions

- Implement a separate `retire-unbound-staging-client.py` controller. Normal
  de-onboarding keeps its stronger binding contract unchanged.
- Inputs are absolute owner-private regular files reached through no-follow
  traversal: original staging intent, cleanup manifest, verified absence,
  encrypted SOPS document, journal and terminal receipt. Promotion, executor
  binding, sentinel registry, liveness config and pending output paths are
  named explicitly and MUST be absent.
- Intent, cleanup manifest and absence evidence bind the same exact
  provider/environment/hostname and the cleanup manifest digest. Absence must
  be canonical schema two, provider resources absent, billing clear, and its
  state resource count zero. The destroyed state bytes must also match the
  digest and absolute path recorded by that exact cleanup manifest.
- The registry entry must be exact status `issued` and bind that same staging
  target. The client must appear exactly once in Xray, Hysteria, AmneziaWG,
  every matching Snell variant, and registry. Every Xray cohort reference to
  that client is removed in the same plan; duplicate or unknown cohort edges,
  missing entries, and partially removed collections refuse.
- Hold the canonical `.new-client.lock` project lock shared by onboarding,
  subscription issuance, normal de-onboarding, and this retirement, plus the
  retirement client lock, across validation, SOPS decrypt/edit/re-encrypt,
  ciphertext compare-and-replace, semantic reread, and receipt publication.
  Disposable onboarding snapshots the ciphertext but also binds the canonical
  original SOPS path, device, inode, and ciphertext digest during preparation.
  Finalization derives the project lock only from that bound path, reopens the
  source with no-follow semantics, and requires the same identity, digest, and
  snapshot bytes before any output publication. The authority scope binds that
  identity and a digest of the canonical lock path, so equal ciphertext from
  another project or a same-path replacement cannot reuse the assignment. No
  supported SOPS writer can interleave or revive a client retired after
  preparation.
- Parse decrypted YAML with duplicate-key rejection at every mapping depth.
  Ambiguous root sections, client entries, Xray collections, or Snell variant
  fields refuse before the journal or candidate is created.
- A mode-0600 schema-one journal records input/ciphertext digests and states
  `prepared`, `candidate`, `published`, then `verified`. Each transition is
  atomic and fsynced. Recovery accepts only the exact same immutable request.
  `prepared` with unchanged ciphertext and no orphan candidate retries;
  `candidate` validates the exact sibling inode and digest; `published`
  requires the exact expected post-image and completes semantic verification.
  Any other image, orphan candidate or journal-replacement temporary,
  premature receipt, or malformed journal fails closed with evidence retained.
- The SOPS edit happens in an owner-private sibling. The original ciphertext
  inode and digest are rechecked under lock immediately before atomic replace.
  Plaintext exists only in bounded process memory/stdin and is never printed.
- The terminal receipt records only categorical status and hashes. An exact
  terminal retry is idempotent and performs no SOPS write.
- The Make target captures all arguments before includes/eager expansion,
  accepts exactly one goal, rejects command-line credentials, clears Make
  overrides, and invokes the controller under `build-gate`.

## Recovery state machine

```text
absent journal + no terminal -> validate -> prepared
prepared + original ciphertext -> retry encrypted mutation
candidate + exact sibling + original ciphertext -> publish ciphertext
published + expected post-image -> semantic reread -> verified receipt
verified terminal + matching request -> unchanged success
anything foreign, partial, ambiguous or malformed -> refusal, retain evidence
```

## Non-goals

- No provider API calls, Terraform apply/destroy, executor deletion, Tailnet
  change, live SOPS file, profile cleanup, token revocation, or promotion.
- No tolerance for delivered/active/stale/revoked/burned clients.
- No compatibility fallback from this recovery path into normal de-onboarding.
