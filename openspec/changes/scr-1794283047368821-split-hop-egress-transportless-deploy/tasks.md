# SCR-1794283047368821: Deploy a split-hop egress node that publishes no client listener

## Objective

`make deploy` converges a split-hop egress node through a `no-public-listener` SSH promotion that the controller admits only for an explicit egress-only, listener-free host, and the UpCloud root provisions that node.

## Ownership

`scripts/no_listener_promotion.py`, `scripts/deploy-controller.py`, `scripts/sshd-baseline-controller.py`, `terraform/providers/upcloud/{variables,firewall}.tf` and `tests/server.tftest.hcl`, `tests/unit/test_deploy_controller.py`, `tests/unit/test_sshd_baseline_controller.py`, `docs/reference/protocol-liveness.md`, `docs/how-to/split-hop-pilot.md`, `terraform/providers/upcloud/README.md`. One writer lane.

## Execution

- [x] SCR-1794283738183240 Admit the no-public-listener promotion kind only for an explicit egress-only listener-free host #bug !high @item:SCR-1794283047368821
- [x] SCR-1794284337233359 Skip only the sentinel proof in the SSH baseline transaction for that kind #bug !high @item:SCR-1794283047368821
- [x] SCR-1794284920176736 Add the UpCloud split-hop-egress node purpose with Terraform tests #bug !high @item:SCR-1794283047368821
- [x] SCR-1794285469184380 Document the Node B inputs in the pilot runbook, liveness reference and UpCloud README #bug !high @item:SCR-1794283047368821

## Verification

- Local: `tests/unit/test_deploy_controller.py`, `tests/unit/test_sshd_baseline_controller.py`, UpCloud `terraform test`, `make docs-check`, `make check` (spans scripts, Terraform and docs).
- Remote CI on the PR and on `main`.
- Dry-run, staging, live and client evidence come from the split-hop Node B deployment under `ANS-1794231660855533`.
