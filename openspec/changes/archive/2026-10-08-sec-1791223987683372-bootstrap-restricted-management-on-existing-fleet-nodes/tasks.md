# SEC-1791223987683372: Bootstrap restricted management on existing fleet nodes

## Objective

Deliver real restricted existing-node enrollment with correct lifecycle
classification, bounded console ingress, policy conversion and autonomous
rollback. Refusal-only behavior leaves the feature and parent incomplete.

## Ownership

The primary writer owns the bootstrap/inventory/controller and firewall adapter
changes, their Ansible wiring, relevant tests/docs and this task's artifacts in
the dedicated worktree. Provider/state/inventory/ingress/enrollment operations
use one serialized lane. Reviews are read-only. Preserve foreign work and rules.
No source result substitutes for protected-source staging or live evidence.

## Execution

- [x] SEC-1791224948871987 Separate Terraform workspace selection from bootstrap lifecycle classification and update every caller #feature !crit @item:SEC-1791223987683372
- SEC-1791224949334227 DROPPED: Render a source-bound expiring console SSH ingress lease with safe shared runtime directories #feature !crit @item:SEC-1791223987683372
- SEC-1791224949790667 DROPPED: Adopt reviewed managed firewall policy through the durable bootstrap transaction #feature !crit @item:SEC-1791223987683372
- SEC-1791224950240563 DROPPED: Prove rollback refusal reboot controller loss and real public Tailnet paths in native tests #feature !crit @item:SEC-1791223987683372
- SEC-1791224950691731 DROPPED: Verify protected-source staging and existing-node bootstrap with invocation cleanup #feature !crit @item:SEC-1791223987683372

## Verification

- Local: targeted inventory/bootstrap/lease/firewall/rollback tests; snapshots,
  task/OpenSpec validation and machine-gated `make check`.
- Native: real namespace/kernel policy, cold startup permissions, expiry,
  controller loss, reboot and original-policy recovery; no fixture as live proof.
- Remote CI: terminal required checks on the exact protected source.
- Dry-run/staging: canonical preflight, guarded isolated existing-policy
  enrollment, both real management paths and provider-confirmed cleanup.
  Repeat check mode after convergence with the recovery timer already loaded;
  missing service facts must not classify an installed timer as absent.
- Live/client: exact existing-node bootstrap and preserved VPN listeners;
  ordinary deployment and authenticated client proof remain parent gates.
- Artifact: exact identity/source/approval/lease/confirmation and retirement
  evidence; keep every missing gate required or blocked.
