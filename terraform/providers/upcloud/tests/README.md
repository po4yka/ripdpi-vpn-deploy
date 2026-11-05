# Native Terraform tests

These `*.tftest.hcl` files exercise the module without contacting UpCloud. `mock_provider "upcloud" {}` short-circuits every API call, so the assertions evaluate against the plan graph alone.

## Run

```bash
make tf-test
# or:
cd terraform/providers/upcloud && terraform init -backend=false && terraform test
```

Requires Terraform **1.6+** (native test framework). Local boxes on older versions can run the rest of the CI but will skip this layer.

## What this covers

`firewall.tftest.hcl` — for every variable combination that affects the rule set, the resulting `firewall_rule` block list must include the expected ports and omit the forbidden ones. Catches:

  * REALITY TCP/443 dropped on a refactor
  * UDP/443 leaking when `enable_hysteria = false`
  * SSH accepting `0.0.0.0/0` (fail-closed contract)
  * XHTTP port duplication when it collides with REALITY:443
  * Default-deny rule dropped (silent accept-any regression)
  * `nginx_xhttp_public_port` validation rejecting out-of-range values

`server.tftest.hcl` — cloud-init enablement, single public NIC by default, secondary public NIC only when `additional_public_ip = true`, `storage_template` must be UUID-shaped.

## What this does NOT cover

  * Whether UpCloud accepts the rule set (API contract drift)
  * Real cloud-init behaviour on the image
  * Apply-time provider quirks

Those live in the `real-vps-deploy` workflow.
