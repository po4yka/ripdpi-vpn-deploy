## Context

The UpCloud root owns rule definitions but leaves the optional/computed server firewall flag unspecified. Populated rules therefore do not prove provider enforcement.

## Goals / Non-Goals

- Goal: require active firewall enforcement and catch omission through the existing mock-provider test seam.
- Non-goal: change SSH CIDRs, listeners, SSH ports, credentials, other providers, or guest configuration; perform live recovery from this delegated worktree.

## Decisions

- Set `firewall = true` directly on the server resource; do not add a disable toggle.
- Model DNS replies separately from public listeners: only approved resolver IPv4 addresses, both TCP and UDP source port 53, the Terraform-derived primary public IPv4 destination, and the guest ephemeral port range. Never copy a live node address into source.
- Reject empty, malformed, or duplicate resolver inputs and invalid port bounds. Emit replies before both terminal deny rules and test the complete rule shape, including custom inputs and optional secondary IPv4.
- Server activation precedes the dependent firewall-rules resource. Do not introduce a dependency cycle or pretend a targeted rules apply avoids the server update. For an existing disabled firewall, install and verify the approved reply rules before a separately authorized activation. Source integration is not permission to apply.
- Extend the existing server test file. Use a mocked server default of false with a mock-only apply assertion, so omission fails deterministically rather than relying on a generated boolean or an unknown plan value.
- Capture RED before the source edit, then run the entire UpCloud mock-provider suite. Record the test seam before implementation.
- Add a short provider-local pitfall explaining that rules and activation are separate controls.

## Contracts and ownership

- Owned implementation paths: UpCloud `main.tf`, `firewall.tf`, `variables.tf`, existing native tests, generated README, and `CLAUDE.md`. The implementation agent also extends `tests/unit/test_listener_contract.py` to evaluate the actual primary-address selector with distinct addresses; native provider mocks cannot assign distinct computed values to repeated interface blocks. The primary agent owns the pinned Terraform installation in the pytest CI job, task state, shared files, commits and integration; independent review is read-only.
- Terraform owns provider activation. Ansible, cloud-init, SOPS, and vpnd contracts remain unchanged. No dependency is added.
- The primary agent owns provider/browser operations, shared board integration, and any subsequent commit or push.

## Risks / Trade-offs

- Enabling old rules can lock out the current operator: install the separately approved narrow CIDR before activation.
- Targeted plans include dependencies: detach rescue media, restore normal boot, and reject any server replacement or unrelated resource change.
- Mock tests prove configuration, not live enforcement: keep source and live evidence separate.

## Migration Plan

After a new implementation request, run the regression RED, set the explicit flag, then run all UpCloud mock tests, `terraform fmt -check`, `terraform validate`, `make validate`, and strict task/OpenSpec validation. No live Terraform plan or apply is delegated. The operator first installs approved rules, then reviews a separate activation-only plan, and verifies provider status, preserved SSH host identity, SSH login, and authenticated transport connectivity. Failed verification leaves the task open; use authorized console recovery without widening the allowlist. No compatibility break or node recreation is required.
