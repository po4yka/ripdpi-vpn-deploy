package terraform.policy.egress_address

# retained_primary_ip_is_not_auto_deleted
#
# Provider API allowlists name the egress address (terraform/ops/egress-proxy).
# A primary IP with auto_delete = true is deleted together with its server, so
# a lost or replaced server would change the address and lock CI out.

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "hcloud_primary_ip"
  not rc.change.after.auto_delete == false

  msg := sprintf("resource %q: a retained primary IP must set auto_delete = false", [rc.address])
}
