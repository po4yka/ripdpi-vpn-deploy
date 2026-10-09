package terraform.policy.admin_port

# no_admin_port_exposed_to_world
#
# Deny any firewall rule that allows the effective SSH port (var.ssh_port)
# or TCP/3389 from 0.0.0.0/0 or ::/0. SSH must be restricted to
# var.allowed_ssh_cidrs.
#
# Provider-specific attribute mappings:
#
#   upcloud_firewall_rules — nested firewall_rule blocks:
#     protocol, destination_port_start, source_address_start/end, action
#
#   hcloud_firewall — nested rule blocks:
#     protocol, port, source_ips, direction
#
#   vultr_firewall_rule — top-level resource:
#     protocol, port, subnet/subnet_size (0 = any)
#
#   scaleway_instance_security_group — nested inbound_rule blocks:
#     protocol, port, ip_range, action

# Every provider root declares ssh_port with a default, so plan JSON always
# carries it; a missing value leaves these deny rules undefined (fail-open is
# impossible for plans produced by this repository's roots).
ssh_port := sprintf("%v", [input.variables.ssh_port.value])

admin_ports := {ssh_port, "3389"}

# panel_port rules removed: no admin panel is deployed in this stack (see
# docs/CDN-DECISION.md and the hard rules in the root AGENTS.md). The
# input.variables.panel_port path does not exist in any provider root, so
# deny rules referencing it silently never fired — removing them keeps the
# policy honest.

# Helper: is this a "world" source for upcloud (address range covers all IPs)?
upcloud_is_world(rule) {
  rule.source_address_start == "0.0.0.0"
  rule.source_address_end == "255.255.255.255"
}

upcloud_is_world(rule) {
  rule.source_address_start == "::"
  rule.source_address_end == "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
}

# Unspecified source endpoints mean any source at this provider edge.
upcloud_is_world(rule) {
  object.get(rule, "source_address_start", "") == ""
  object.get(rule, "source_address_end", "") == ""
}

# upcloud_firewall_rules — deny world-open TCP/22 or TCP/3389
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  rule := rc.change.after.firewall_rule[_]
  rule.action == "accept"
  rule.direction == "in"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  upcloud_is_world(rule)
  port := admin_ports[_]
  data.terraform.policy.ports.interval_covers(object.get(rule, "destination_port_start", ""), object.get(rule, "destination_port_end", object.get(rule, "destination_port_start", "")), port)

  msg := sprintf(
    "resource %q: firewall rule allows TCP/%s from world; SSH must be restricted to allowed_ssh_cidrs",
    [rc.address, port],
  )
}

# scaleway_instance_security_group — deny world-open TCP/22 or TCP/3389
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  rule := rc.change.after.inbound_rule[_]
  rule.action == "accept"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  data.terraform.policy.ports.world_cidr(object.get(rule, "ip_range", null))
  port := admin_ports[_]
  data.terraform.policy.ports.scaleway_covers(rule, port)

  msg := sprintf(
    "resource %q: Scaleway security-group rule allows TCP/%s from world; SSH must be restricted to allowed_ssh_cidrs",
    [rc.address, port],
  )
}

# hcloud_firewall — deny world-open TCP/22 or TCP/3389
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "hcloud_firewall"
  rule := rc.change.after.rule[_]
  rule.direction == "in"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  hcloud_is_world(rule)
  port := admin_ports[_]
  data.terraform.policy.ports.covers(object.get(rule, "port", null), port)

  msg := sprintf(
    "resource %q: hcloud firewall rule allows TCP/%s from world; SSH must be restricted to allowed_ssh_cidrs",
    [rc.address, port],
  )
}

# vultr_firewall_rule — subnet_size=0 means any source
vultr_is_world(rc) {
  rc.change.after.subnet_size == 0
}

# vultr_firewall_rule — deny world-open TCP/22 or TCP/3389
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "vultr_firewall_rule"
  data.terraform.policy.ports.tcp_protocol(object.get(rc.change.after, "protocol", null))
  vultr_is_world(rc)
  port := admin_ports[_]
  data.terraform.policy.ports.covers(object.get(rc.change.after, "port", null), port)

  msg := sprintf(
    "resource %q: vultr firewall rule allows TCP/%s from world; SSH must be restricted to allowed_ssh_cidrs",
    [rc.address, port],
  )
}


hcloud_is_world(rule) {
  data.terraform.policy.ports.world_cidr(rule.source_ips[_])
}

hcloud_is_world(rule) {
  count(object.get(rule, "source_ips", [])) == 0
}

hcloud_is_world(rule) {
  object.get(rule, "source_ips", null) == null
}
