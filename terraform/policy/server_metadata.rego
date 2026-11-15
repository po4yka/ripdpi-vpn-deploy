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

# active_edge_firewall_stays_active
#
# A fresh UpCloud node starts with firewall = false (the provider firewall is
# stateless; see terraform/providers/upcloud/README.md) and promotion turns it
# on. A later plan built from an unchanged tfvars file would turn it off again
# in place and expose every port at the edge, so that transition is refused.
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_server"
  rc.change.before.firewall == true
  rc.change.after.firewall == false

  msg := sprintf(
    "resource %q: plan turns the active provider firewall off; set enable_provider_firewall = true",
    [rc.address],
  )
}

# existing_server_gets_its_edge_firewall
#
# The rule above matches only the change from on to off, so a node that is
# never promoted would pass. A plan that changes resources while an existing
# UpCloud server keeps firewall = false is refused. Three plans stay allowed:
# the plan that creates or replaces the server, a plan that still creates the
# server's firewall rules (an interrupted first apply is being finished), and a
# plan with no resource change (recovery uses an empty plan to prove
# convergence, and nothing is applied).
changes_resources {
  action := input.resource_changes[_].change.actions[_]
  not {"no-op", "read"}[action]
}

creates_upcloud_firewall_rules {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  rc.change.actions[_] == "create"
}

creates(rc) {
  rc.change.actions[_] == "create"
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_server"
  not creates(rc)
  rc.change.after.firewall == false
  not rc.change.before.firewall == true
  changes_resources
  not creates_upcloud_firewall_rules

  msg := sprintf(
    "resource %q: plan changes a node that keeps the provider firewall off; promote the node first (set enable_provider_firewall = true; see terraform/providers/upcloud/README.md)",
    [rc.address],
  )
}

# every_server_has_an_edge_firewall
#
# hcloud_server, vultr_instance and scaleway_instance_server attach the
# provider firewall on the server resource. On creation the reference is not
# known yet: the plan then lists the attribute under after_unknown, which
# counts as attached.
firewall_attachment := {
  "hcloud_server": "firewall_ids",
  "vultr_instance": "firewall_group_id",
  "scaleway_instance_server": "security_group_id",
}

empty_values := {null, ""}

empty_attachment(value) {
  empty_values[value]
}

# after_unknown holds false for an attribute that is known.
empty_attachment(value) {
  value == false
}

empty_attachment(value) {
  is_array(value)
  count([item | item := value[_]; not empty_values[item]]) == 0
}

deny[msg] {
  rc := input.resource_changes[_]
  attribute := firewall_attachment[rc.type]
  rc.change.after != null
  empty_attachment(object.get(rc.change.after, attribute, null))
  empty_attachment(object.get(object.get(rc.change, "after_unknown", {}), attribute, null))

  msg := sprintf(
    "resource %q (%s): server has no provider firewall (%s is empty)",
    [rc.address, rc.type, attribute],
  )
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  rc.change.after.inbound_default_policy == "accept"

  msg := sprintf(
    "resource %q: inbound_default_policy must be drop, not accept",
    [rc.address],
  )
}
