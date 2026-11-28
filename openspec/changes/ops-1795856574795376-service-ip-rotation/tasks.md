# OPS-1795856574795376

## Objective

An existing node moves its client traffic to a new movable provider IPv4 and retires the old one without server replacement, while SSH, Tailnet and device credentials stay unchanged.

## Ownership

Terraform provider roots and policy, inventory rendering and its consumers, the `baseline` role, vpnd inventory limits, docs. One writer.

## Verification

Local: `make tf-test`, `make tf-policy-verify`, the touched unit test modules and `make test-unit`, `make snapshot-check`, `make docs-check`, then `make check`. CI: Molecule `baseline` and `tailnet-management`. Staging and client: moved to `OPS-1795867688528839`, one attach, refresh and retire cycle on a disposable node with a refreshed client.

## Execution

- [x] OPS-1795857751222463 Attach movable service IPv4 generations in every provider root and record the service outputs, with mock-provider tests #feature !high @item:OPS-1795856574795376
- [x] OPS-1795857809017056 Split client and host addresses in inventory and their consumers, refusing inconsistent outputs, with tests #feature !high @item:OPS-1795856574795376
- [x] OPS-1795857932939870 Limit the secondary-IP plan policy to the honeypot address with a policy test #feature !high @item:OPS-1795856574795376
- [x] OPS-1795858000920970 Document the attach, move and retire runbook and update folder notes #feature !high @item:OPS-1795856574795376
- [x] OPS-1795858050569373 Own service address guest /32s in the baseline role with Molecule retirement coverage #feature !high @item:OPS-1795856574795376
- [x] OPS-1795858101968177 Move dry-run, staging and client acceptance to OPS-1795867688528839 with a shared evidence mapping #feature !high @item:OPS-1795856574795376
