# TST-1786299293097217: Complete recurring AmneziaWG live acceptance

## Objective

Produce one complete current-revision AWG acceptance path from disposable
provisioning through real client traffic, recovery, redacted evidence, and cleanup.

## Ownership

Own the existing AWG real-VPS executor, sentinel/evidence integration, focused
tests, and operator scheduling. Serialize shared evidence and secrets contracts.

## Execution

- [ ] TST-1786299379836822 Extend the acceptance manifest with exact-source, freshness, recovery, and teardown outcomes #feature !high @item:TST-1786299293097217
- [ ] TST-1786299379854550 Prove negative keys, partial evidence, unavailable infrastructure, and cleanup fail closed #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379836822
- [ ] TST-1786299379871208 Run one isolated current-revision client and server acceptance plus one recurring observation #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379854550
- [ ] DOC-1786299379888954 Record redacted exact-SHA evidence and the remaining external limitations #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379871208

## Offline implementation note

The deploy-side v4 source candidate creates a fresh root-private nonce request
per invocation and fails closed unless it consumes a canonical Ed25519-signed,
nonce/invocation-bound handoff supplying a fresh correlated RIPDPI acceptance
with exact source, APK and report digests plus every traffic/recovery/cleanup
outcome.
Standalone `amneziawg-go` provenance is recorded separately as engine identity.
Launcher preflight and runtime `INFRA_UNAVAILABLE` outcomes retain an existing
`latest.json`; a replacement PASS must be later and use distinct invocation,
report and correlation identities. These offline safeguards do not supply the
client signer/relay, client artifact, provider inputs, disposable VPS, or either
live observation, so no execution step is closed here.

## Verification

Run task contracts and focused offline tests before the isolated live and recurring gates.
