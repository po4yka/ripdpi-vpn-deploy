## Context

OpenSSH first-obtained-value semantics across lexicographically ordered `sshd_config.d` fragments make the current five-directive overlap between cloud-init and baseline drop-ins a silent-shadow trap. The audit flagged it alongside fragment-isolated validation and unpinned algorithms. Port ownership already lives solely in the cloud-init file and must stay there: it is read before first-boot reload in the socket-activation chain.

## Goals / Non-Goals

- Goal: single-owner directives, effective-config validation, pinned algorithms, zero lockout regressions.
- Non-goal: reworking the cloud-init marker/wait chain or the socket-activation ordering (owned elsewhere); managing crypto-policies system-wide.

## Decisions

- Keep Port in the 10- file: it participates in the first-boot listen path; moving it would entangle this change with the bootstrap chain.
- Duplicate detection as a pre-write Ansible task parsing both files rather than a grep convention: fail-closed and molecule-testable.
- Algorithm allowlist sized to the two pinned distros rather than a minimal common set: avoids breaking images whose compiled-in sets differ.
- Effective-config check implemented as post-write parse diff of managed keys: no dependency on external tools beyond stock sshd.

## Contracts and ownership

- terraform/shared/cloud-init.yaml.tftpl: reduced drop-in; template-only change, no variable contract change.
- ansible/roles/baseline: template + new check task + validation step.
- ansible/playbooks/verify.yml: additive assertions.

## Risks / Trade-offs

- Lockout during rehearsal → mitigated by scratch-node rehearsal gate before fleet rollout.
- Over-tight algorithm lists can reject legacy clients → list derived from pinned images' compiled-in sets; verified via molecule matrix.
- Editing cloud-init.yaml.tftpl affects new nodes only. Existing nodes with the old bootstrap-owned X11Forwarding directive fail the duplicate guard; recreate them from the new template before rollout. Baseline never silently edits bootstrap-owned configuration.

## Migration Plan

- Forward: fresh nodes use the single-owner layout. Legacy nodes with bootstrap-owned X11Forwarding require recreation (or a separate reviewed migration) before baseline convergence; there is no compatibility path. Add checks and pins only after the candidate validates.
- Rollback: revert commits; drop-ins regenerate to prior state.
- Gates: molecule matrix both distros, lockout rehearsal, `make ci-fast`, `make validate`.
