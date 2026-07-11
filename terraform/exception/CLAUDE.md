# terraform/exception — isolated jurisdiction-exception roots

## Design decisions

Exception roots never share state, wrappers, hosting-provider selection, or apply cycles with `terraform/providers/*`. They remain hosting-provider-neutral and inert until a separate governance decision supplies a concrete adapter. A local `external` checker provider is permitted only to enforce a gate inside the root.

## What's done well

- Normal `make plan`, `make apply`, and `scripts/terraform-env.sh` cannot address this tree.
- Every plan-adjacent entry point checks the expiring candidate-ASN attestation first, and the root independently runs the same checker.

## Pitfalls

- A valid plan is not activation authority. The single-purpose apply boundary always blocks while the cascade decision remains no-go for live infrastructure.
