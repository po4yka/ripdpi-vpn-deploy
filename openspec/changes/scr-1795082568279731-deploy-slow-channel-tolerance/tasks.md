# SCR-1795082568279731: Tolerate a slow operator channel during deploy

## Objective

Ansible tasks in a controller run survive a short stall of the operator channel, and a mutating deploy refuses before any host change when its Tailnet management route is lossy, slow or unmeasured.

## Ownership

`scripts/deploy-controller.py`, `tests/unit/test_deploy_controller.py`, a stub `tailscale` binary in `tests/stubs/bin/` if the tests need one, and `docs/how-to/deploy.md`. One writer.

## Execution

- [x] SCR-1795082805831806 Add keepalive and connection attempts to the multiplexed master and ansible_ssh_timeout to transport variables, with tests #feature !high @item:SCR-1795082568279731
- [x] SCR-1795082820949890 Add the deploy-mode Tailnet management-route gate with stub-binary tests #feature !high @item:SCR-1795082568279731
- [x] SCR-1795082836372885 Document the gate, refusal categories and timeouts in the deploy how-to; run docs-check and make check #feature !high @item:SCR-1795082568279731

## Verification

Local: `python3 -m pytest tests/unit/test_deploy_controller.py`, `make docs-check`, and `make check` once before handoff. Remote CI on the PR. Live: the next authorized deploy over a Tailnet route prints the route kind and median before the playbook starts. Dry-run, staging, client and artifact categories do not apply.
