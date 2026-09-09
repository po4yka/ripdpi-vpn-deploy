## Purpose

Keep exact-resource cleanup available throughout first-node bootstrap and
provider firewall promotion without weakening UUID or state-digest binding.

## MODIFIED Requirements

### Requirement: REQ-UPF-STAGING — Promotion and rollback use isolated live evidence

Before production adoption, an authorized isolated UpCloud node MUST prove
cloud-init package bootstrap, DNS, outbound TCP and UDP, strict SSH and required
public listeners with the provider firewall disabled and again after in-place
activation. Failure MUST stop promotion; rollback disables the provider
firewall through Terraform and rechecks SSH. Cleanup MUST delete only the exact
manifest-bound server, root storage and Terraform-owned rules, then verify
provider absence before the 47-hour hard deadline.

The initial UUID-bound cleanup manifest MUST be created from exact private
state immediately after provisioning and before any guest bootstrap or deploy
write, while the provider firewall remains disabled. Following an authorized
same-node firewall update or rollback, the operator MUST create a new manifest
at a new private path from the refreshed exact state and unchanged provider
identity before further guest writes or destruction. Previous manifests and
evidence MUST be retained; the new manifest MUST preserve creation-derived
deadlines. Stale manifests MUST continue refusing. Reissue MUST NOT occur with
an outstanding destruction reservation or started apply.

The UpCloud and Vultr guards MUST share a controller-owned resource journal
keyed by provider, authenticated account and server UUID. Manifest publication,
reservation, release, recovery and apply/absence receipts MUST use the same
exclusive lock. The durable reservation MUST survive between commands.
Initial creation MUST reject an already registered node; explicit reissue
MUST bind the registered previous generation and changed state at its original
path. Alternate artifact paths MUST NOT bypass these checks. An interrupted
publication or release MUST recover only its recorded request and artifact
identity. Unregistered legacy manifests MUST refuse. Separate controllers
without a shared authoritative journal MUST NOT operate on the same node.

#### Scenario: Alternate paths while destruction is pending

- **WHEN** another command selects a different manifest, state or evidence path for an already reserved node
- **THEN** neither reissue nor a second reservation is permitted, and the existing artifacts remain unchanged.

#### Scenario: Controller stops during journal publication or release

- **WHEN** a process stops after durable intent but before completion
- **THEN** the exact recorded operation can recover, another path refuses, and a started apply cannot be replayed.

#### Scenario: Post-activation network check fails

- **WHEN** any required outbound, listener or strict SSH probe fails after activation
- **THEN** production promotion is refused, the provider firewall is disabled on the same staging node, and exact-resource cleanup remains mandatory.

#### Scenario: Initial guest bootstrap fails

- **WHEN** a provisioned node fails bootstrap before firewall promotion
- **THEN** the initial manifest already binds its resources and permits the normal guarded cleanup sequence without bypassing the state digest.

#### Scenario: Provider firewall changes the state digest

- **WHEN** an authorized in-place activation or rollback updates only the same owned node
- **THEN** a fresh manifest binds the refreshed state with the original deadlines, while the previous manifest refuses destruction of the changed state.
