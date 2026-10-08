# Change: Bootstrap restricted management on existing fleet nodes

Task ID: `SEC-1791223987683372`

## Why

Existing fleet nodes cannot enter the accepted dual-path deployment flow.
The current inventory names a Terraform workspace such as `p0-upcloud`, while
bootstrap accepts only `prod` or a disposable workspace. A repository-managed
firewall without the new Tailnet fragment is also refused. Dynamic operator
egress can prevent the public SSH path needed to migrate that policy.

The observed console recovery restored strict public SSH and installed the
exact SSH recovery foundation. It also exposed why ad hoc recovery is unsafe:
creating shared systemd runtime directories under a private umask prevented
the unprivileged network daemon from starting. A source-bound temporary ingress
capability must preserve the operating system directory contract and expire.

## What Changes

- BREAKING: bootstrap requests bind both the Terraform workspace and the
  canonical build environment emitted by inventory; all callers are updated.
- A credential-free Make renderer prepares one bounded, source-bound console
  ingress lease for an exact existing node. It changes only RAM state and one
  exact-source SSH allowance, without passwords, keys or public administration.
- Bootstrap can convert an explicitly reviewed repository-managed firewall to
  the canonical Tailnet layout within its existing durable transaction. It
  preserves VPN listeners and restores the original policy after failure.
- Missing ownership, policy drift, foreign tables, unsafe paths, expired leases
  and disguised disposable environments refuse before access changes.
- Positive acceptance requires real pinned public and Tailnet SSH/SFTP plus
  unchanged SSH policy, resolver and routes. Refusal-only behavior cannot close
  this task or its parent.

## Capabilities

### New Capabilities

- `security/existing-fleet-bootstrap`: restricted enrollment of existing managed
  nodes, including expiring console ingress and policy conversion.

### Modified Capabilities

- `security/tailnet-first-node-bootstrap`: workspace/build-environment binding
  and rollback-safe adoption of reviewed managed policy.

## Impact

- The canonical Make bootstrap surface, inventory renderer and bootstrap input
  contract; every staging harness and test producer of that contract.
- Firewall-owned bootstrap snapshot, apply, confirmation and recovery helpers,
  their Ansible installation and operator documentation.
- No provider resource replacement, production dependency, credential sharing,
  authentication weakening or removal of dual-path deployment gates.
- Protected source, local/native regression checks, guarded real staging and
  existing-node acceptance remain separate required evidence. New paid staging
  resources require their own concrete authorization before creation.
