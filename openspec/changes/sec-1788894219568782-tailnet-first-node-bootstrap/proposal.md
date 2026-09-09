# Change: Bootstrap restricted Tailnet access before dual-path deployment

Task ID: `SEC-1788894219568782`

## Why

On a fresh node, the deployment controller requires a distinct management
address and performs readiness over that transport before the site playbook
can install and enroll Tailnet. The documented first enrollment through deploy
therefore cannot establish its own prerequisite. The separate SSH recovery
installer does not enroll Tailnet. An authorized staging run cannot safely
proceed by inventing socket contexts or invoking Ansible outside the controller.

The staging runbook also places the cleanup manifest after guest convergence
and provider firewall promotion, while disposable promotion requires that
manifest before deployment. The supported first-node sequence must resolve
both dependencies before resources are created.

## What Changes

- Add an explicit one-node bootstrap command using pinned public SSH, durable
  recovery, a restricted guest firewall foundation, and fresh proof of both
  public and Tailnet SSH before confirmation.
- Keep the ordinary deploy controller's dual-path and protocol proof gates.
  Bootstrap establishes access only; it does not publish a deployed manifest
  or declare any VPN profile accepted.
- Keep enrollment and firewall changes unconfirmed until external path proof;
  controller loss, reboot, timeout, and failure restore the previous state.
  Boot recovery restores firewall before networking and revokes enrollment
  after tailscaled, using two phases of the same durable transaction.
- BREAKING: first Tailnet enrollment must use the bootstrap command; ordinary
  deploy becomes verification-only for Tailnet and rejects enrollment keys.
  Update every documented and tested caller; no alternate enrollment path.
- Establish the cleanup manifest before guest writes. Reissue it from the
  exact refreshed state after an authorized same-node firewall transition;
  stale manifests continue to refuse, with previous evidence retained.
- BREAKING: both provider cleanup guards register manifest generations and
  destruction reservations in one resource-bound controller journal. Reissue
  becomes an explicit operation using the registered previous manifest; copied
  paths cannot bypass pending cleanup. Update manifest versions and callers.

## Capabilities

### New Capabilities

- `security/tailnet-first-node-bootstrap`: bounded public-path enrollment,
  durable recovery, external confirmation, and handoff to ordinary deployment.

### Modified Capabilities

- `security/upcloud-stateless-return-path`: stage cleanup ownership before
  guest convergence and bind a new manifest after same-node firewall promotion.

## Impact

- Make/controller boundary, Tailnet transaction and Ansible role, firewall
  bootstrap/rollback, SSH recovery readiness, deploy credential handling,
  staging manifest sequence, operator documentation, and runtime tests.
- Terraform remains the owner of provider resources; bootstrap does not change
  provider firewall policy, create nodes, or edit Tailnet ACLs.
- Reuse pinned packages and existing recovery primitives. No new production
  dependency, secret schema field, or vpnd interface is planned.
