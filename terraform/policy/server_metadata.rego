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
  some name
  matcher := {
    "admin_user": "^[a-z_][a-z0-9_-]{0,31}$",
    "server_name": "^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$",
  }[name]
  variable := input.variables[name]
  not valid_identity(name, matcher, object.get(variable, "value", null))
  msg := sprintf("plan input %s must name a valid provisioning identity", [name])
}

valid_identity("admin_user", matcher, value) {
  is_string(value)
  value != "root"
  regex.match(matcher, value)
}

valid_identity("server_name", matcher, value) {
  is_string(value)
  count(value) <= 253
  regex.match(matcher, value)
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

# server_is_not_deleted_by_an_ordinary_plan
#
# prevent_destroy stops Terraform from planning a server deletion. Only
# scripts/destroy.sh lifts it, with an override file that covers every
# environment of the provider root, and its destroy plan does not pass through
# this policy. A plan made while that override exists can replace the server,
# so a deletion or replacement that reaches this policy is refused.
deny[msg] {
  rc := input.resource_changes[_]
  server_resource_types[rc.type]
  rc.change.actions[_] == "delete"

  msg := sprintf(
    "resource %q: an ordinary plan deletes or replaces the server; use make destroy",
    [rc.address],
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

empty_values := {null, "", false}

empty_attachment(value) {
  empty_values[value]
}

empty_attachment(value) {
  is_array(value)
  count([item | item := value[_]; not empty_values[item]]) == 0
}

pending_attachment(value) {
  value == true
}

pending_attachment(value) {
  is_array(value)
  value[_] == true
}

has_pending_attachment(change, attribute) {
  unknown := object.get(change, "after_unknown", null)
  is_object(unknown)
  pending_attachment(object.get(unknown, attribute, false))
}

deny[msg] {
  rc := input.resource_changes[_]
  attribute := firewall_attachment[rc.type]
  rc.change.after != null
  empty_attachment(object.get(rc.change.after, attribute, null))
  not has_pending_attachment(rc.change, attribute)

  msg := sprintf(
    "resource %q (%s): server has no provider firewall (%s is empty)",
    [rc.address, rc.type, attribute],
  )
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  after := rc.change.after
  after != null
  object.get(after, "inbound_default_policy", null) != "drop"

  msg := sprintf(
    "resource %q: inbound_default_policy must be explicitly set to drop",
    [rc.address],
  )
}

# UpCloud evaluates inbound rules in order. Each family needs an
# unconditional final drop, before any separately scoped outbound rules.
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  after := rc.change.after
  after != null
  family := {"ipv4", "ipv6"}[_]
  not has_final_inbound_drop(object.get(after, "firewall_rule", []), family)
  msg := sprintf("resource %q: UpCloud requires a final unconditional inbound drop for %s", [rc.address, family])
}

has_final_inbound_drop(rules, family) {
  rule := rules[index]
  rule.direction == "in"
  drop_covers_family(rule, family)
  rule.action == "drop"
  {null, ""}[object.get(rule, "protocol", null)]
  not restricted_drop(rule)
  not later_inbound_rule(rules, index, family)
}

drop_covers_family(rule, _) {
  {null, ""}[object.get(rule, "family", null)]
}

drop_covers_family(rule, family) {
  lower(rule.family) == family
}

restricted_drop(rule) {
  field := {
    "source_address_start", "source_address_end", "destination_address_start", "destination_address_end",
    "source_port_start", "source_port_end", "destination_port_start", "destination_port_end",
    "icmp_type",
  }[_]
  not {null, ""}[object.get(rule, field, null)]
}

later_inbound_rule(rules, index, family) {
  rule := rules[later]
  later > index
  rule.direction == "in"
  lower(sprintf("%v", [object.get(rule, "family", null)])) != {"ipv4": "ipv6", "ipv6": "ipv4"}[family]
}
