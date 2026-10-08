# SEC-1791451917662060: Normalize the packaged image SSH fragment

## Objective

Complete strict first-boot SSH ownership on the supported image.

## Ownership

Primary owns `terraform/shared/bootstrap-sshd-ownership.py`, its nearest notes,
`tests/unit/test_cloud_init_marker.py` and this task's artifacts. Shared board
updates and live mutations are serialized.

## Execution

- [x] SEC-1791452040981214 Normalize the exact packaged fragment with rollback and refusal coverage #bug !crit @item:SEC-1791451917662060
- [x] SEC-1791452041489847 Observe local and hosted validation and strict live bootstrap completion #bug !crit @item:SEC-1791451917662060

## Verification

Focused cloud-init tests, `make check`, terminal hosted CI and real pinned SSH,
effective policy, marker and readiness. Full fleet protocol acceptance remains
the deployment objective and is not inferred from this narrow bootstrap fix.
