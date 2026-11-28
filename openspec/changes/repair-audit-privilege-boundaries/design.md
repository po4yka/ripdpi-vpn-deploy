## Context

Extend the current subscription and transport boundaries. The existing static share route already serves retained pages across deployments.

## Goals / Non-Goals

Resolve the listed source defects and verify their normal entry points. Live convergence and credential rotation are separate operations.

## Decisions

- Give Realm its own TLS copies and revoke its former supplemental group on convergence.
- Keep the original request URI out of access logs for protected routes through redirects and log only public traffic there.
- Derive the AWG tag from the host selector and keep credential checks at each existing admission boundary.
- Keep the Make command pipeline and use its existing descriptor-bound secrets gate.

## Contracts and ownership

Ansible owns the services and hosted files. Terraform validates provider inputs. Operator scripts own key generation and export. vpnd delegates Make operations. CI owns the fixture dependency and parity checks.

## Risks / Trade-offs

Rejecting invalid inputs can stop an existing invocation. Realm reuses the existing TLS authority but requires a new copy on deployment.

## Migration Plan

Use private provider and service inputs that pass the updated validation. Enroll new devices through the canonical client command and regenerate bundles to get node-based AWG tags. Use a source revert for rollback. Run offline source checks and hosted CI before integration.
