## Purpose

Interrupted protected-site commits never leave ingress and egress serving different accepted generations; the next run completes or restores both as one boundary.

## ADDED Requirements

### Requirement: REQ-OPS-ORP-COMMIT-ATOMIC — Recover an interrupted protected commit as one boundary

When a deploy is interrupted at any point between the start of protected ingress commit and the completion of egress finish, the next run MUST either complete both commits or restore both ingress and egress to the previously accepted generation, and MUST NOT leave them at different generations.

#### Scenario: Interrupted after ingress commit

- **WHEN** a deploy is killed after the ingress site commit and before egress finish
- **THEN** the next run leaves ingress and egress at the same accepted generation

#### Scenario: Interrupted before ingress commit

- **WHEN** a deploy is killed before the ingress site commit
- **THEN** the next run restores both to the previously accepted generation
