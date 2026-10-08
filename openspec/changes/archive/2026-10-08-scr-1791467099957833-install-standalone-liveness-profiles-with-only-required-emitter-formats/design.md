## Context

The emitter correctly rejects unsupported standalone formats. The profile builder already reads each document only for its associated required profile; unused inputs may be absent.

## Goals / Non-Goals

- Goal: install standalone and mixed sentinels from only the required canonical emitter inputs.
- Non-goal: change server runtime, schemas, engine versions or protocol configuration.

## Decisions

- Select sing-box when REALITY or Hysteria2 is required; select RIPDPI when XHTTP is required.
- Pass None for unused documents, preserving existing rejection when a required document is absent or invalid.
- Propagate each required emitter failure; retain decryption, native parsers, target identity and generation receipt checks.

## Contracts and ownership

- Own scripts/install_liveness_sentinel.py and its focused orchestration tests.
- Update scripts/DESIGN-NOTES.md, tests/CLAUDE.md and docs/PROTOCOL-LIVENESS.md for the observable selection rule.
- Terraform, cloud-init, Ansible server roles, vpnd flags and SOPS schema retain their current interfaces.

## Risks / Trade-offs

- Missing a required format would fail profile construction; parameterized standalone and mixed tests cover selection and failure before remote writes.
- Unit fixtures do not prove live authentication; real standalone P1 onboarding and XHTTP traffic remain required for completion.

## Migration Plan

Deploy the committed installer through normal source gates. No stored-data migration or compatibility layer is needed. A regression is reverted through a normal committed source change; existing committed sentinel generations remain reconciled by the same receipt logic.
