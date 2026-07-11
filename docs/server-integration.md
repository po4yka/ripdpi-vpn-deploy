# Server integration notes

## Opaque subscription endpoint and cascade backing

A subscription bundle profile may be backed by an operator-side cascade deployment without changing the deploy-side subscription schema. This follows the existing opaque-single-endpoint precedent: the bundle exposes one client-facing endpoint and does not describe, select, or reveal the operator's internal ingress-to-egress topology.

The cascade classification decision is server-side and uniform per connection. The ingress must derive the destination from the connection it terminates, invoke the tri-state classifier, serve an RU-classified destination through the direct policy path, forward a foreign-classified destination through the egress leg, and refuse serving state when the dataset is unavailable. The design must not assume a client-provided route hint, tier bit, destination-class signal, or second endpoint because no such client-side signal exists.

Zero client configuration is the compatibility contract: changing whether an opaque endpoint is backed by a single node or an operator-side cascade must not require a client schema or code change. Any Android client-visible cascade tier, diagnostic label, or topology disclosure is explicitly out of scope for this deploy-repo work.

Live cascade backing remains unauthorized while `docs/RU-CASCADE-DECISION.md` is implementation-only. The current ingress role records the classifier interface but deliberately does not contain the per-connection client-termination adapter or any service-start behavior. This note records compatibility only; it does not enable a role, alter a family profile, authorize hosting, or imply a subscription schema change.
