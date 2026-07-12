package terraform.policy.server_metadata

# every_server_has_metadata_enabled
#
# Applies to: upcloud_server, hcloud_server, vultr_instance, scaleway_instance_server
# upcloud_server exposes metadata as a top-level boolean attribute.
# hcloud_server and vultr_instance do not surface a metadata attribute in
# the plan JSON (metadata is always enabled on those platforms); the rule
# therefore only fires when the attribute is explicitly present and false.

server_resource_types := {
  "upcloud_server",
  "hcloud_server",
  "vultr_instance",
  "scaleway_instance_server",
}

deny[msg] {
  rc := input.resource_changes[_]
  server_resource_types[rc.type]
  after := rc.change.after

  # attribute present and explicitly disabled
  after.metadata == false

  msg := sprintf(
    "resource %q (%s): metadata must be enabled (metadata = true)",
    [rc.address, rc.type],
  )
}
