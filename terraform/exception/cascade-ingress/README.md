# Inert cascade-ingress Terraform root

This provider-neutral root exists only to establish isolated state, literal acknowledgement, attestation-gated planning, and the fixed inventory output contract. It cannot create a server and is unreachable through the normal Terraform/deploy wrapper.

Run Terraform init/validate directly inside this root for static review. `plan.sh` is the single-purpose plan boundary and requires the acknowledgement literal plus a fresh attestation; the root independently invokes the same checker so direct Terraform execution cannot bypass attestation. `apply.sh` verifies attestation and then always blocks until a future evidence-backed governance commit adds a concrete provider adapter.
