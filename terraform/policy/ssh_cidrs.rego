package terraform.policy.ssh_cidrs

# firewall_rules_pin_ssh_to_documented_cidrs
#
# SSH allow rules must reference a CIDR that appears in var.allowed_ssh_cidrs.
# Inline string literals that are not in the variable list are denied.
#
# The effective SSH port comes from var.ssh_port, not a literal: every root
# declares it with a default, so plan JSON always carries the value.
#
# Provider-specific checks:
#
#   upcloud_firewall_rules — firewall_rule blocks for var.ssh_port/tcp must have
#     source_address_start inside a network from allowed_ssh_cidrs (structural
#     check; the rule comment is not trusted).
#
#   hcloud_firewall — rule blocks for var.ssh_port/tcp must have all source_ips
#     members present in allowed_ssh_cidrs.
#
#   vultr_firewall_rule (resource "vultr_firewall_rule" "ssh") — subnet
#     must match one of the allowed_ssh_cidrs entries.
#
#   scaleway_instance_security_group — nested inbound_rule blocks use
#     ip_range directly.

allowed_cidrs := {cidr | cidr := input.variables.allowed_ssh_cidrs.value[_]}

ssh_port := sprintf("%v", [input.variables.ssh_port.value])

valid_ssh_port {
  port := input.variables.ssh_port.value
  is_number(port)
  port == floor(port)
  port >= 1
  port <= 65535
}

# Saved plans can predate root validation. Unknown/fractional management inputs
# cannot reliably identify the actual guest listener and must refuse evaluation.
deny[msg] {
  rc := input.resource_changes[_]
  {"upcloud_firewall_rules", "hcloud_firewall", "vultr_firewall_rule", "scaleway_instance_security_group"}[rc.type]
  not valid_ssh_port
  msg := "SSH plan port must be a known integer within 1..65535"
}

# upcloud: each SSH accept rule source must be within an allowed CIDR.
# Evaluation is structural — the comment is not trusted: a missing or
# reworded comment must not bypass the gate, because conftest is the only
# offline enforcement point for this provider. A source passes when it is
# exactly listed in var.allowed_ssh_cidrs or falls inside one of those
# networks (net.cidr_contains accepts both bare hosts and nested CIDRs).
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  rule := rc.change.after.firewall_rule[_]
  rule.action == "accept"
  rule.direction == "in"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  data.terraform.policy.ports.interval_covers(object.get(rule, "destination_port_start", ""), object.get(rule, "destination_port_end", object.get(rule, "destination_port_start", "")), ssh_port)

  source := object.get(rule, "source_address_start", "")
  not upcloud_interval_allowed(rule)

  msg := sprintf(
    "resource %q: SSH allow rule source %q is not in var.allowed_ssh_cidrs",
    [rc.address, source],
  )
}

upcloud_source_allowed(source) {
  allowed_cidrs[source]
}

upcloud_source_allowed(source) {
  cidr := allowed_cidrs[_]
  net.cidr_contains(cidr, source)
}

# scaleway: each SSH inbound rule must use a documented CIDR.
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  rule := rc.change.after.inbound_rule[_]
  rule.action == "accept"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  data.terraform.policy.ports.scaleway_covers(rule, ssh_port)
  not upcloud_source_allowed(object.get(rule, "ip_range", ""))

  msg := sprintf(
    "resource %q: Scaleway SSH rule source CIDR %q is not in var.allowed_ssh_cidrs",
    [rc.address, rule.ip_range],
  )
}

# hcloud: each source_ip in an SSH rule must be in allowed_ssh_cidrs
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "hcloud_firewall"
  rule := rc.change.after.rule[_]
  rule.direction == "in"
  data.terraform.policy.ports.tcp_protocol(object.get(rule, "protocol", null))
  data.terraform.policy.ports.covers(object.get(rule, "port", null), ssh_port)
  source_ip := rule.source_ips[_]
  not upcloud_source_allowed(source_ip)

  msg := sprintf(
    "resource %q: hcloud SSH rule source IP %q is not in var.allowed_ssh_cidrs",
    [rc.address, source_ip],
  )
}

# vultr: SSH firewall rules use subnet+subnet_size; compare via comment or
# reconstruct CIDR string from subnet/subnet_size attributes.
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "vultr_firewall_rule"
  data.terraform.policy.ports.tcp_protocol(object.get(rc.change.after, "protocol", null))
  data.terraform.policy.ports.covers(object.get(rc.change.after, "port", null), ssh_port)
  after := rc.change.after
  cidr := sprintf("%s/%d", [after.subnet, after.subnet_size])
  not upcloud_source_allowed(cidr)

  msg := sprintf(
    "resource %q: vultr SSH rule source CIDR %q is not in var.allowed_ssh_cidrs",
    [rc.address, cidr],
  )
}


upcloud_interval_allowed(rule) {
  start := object.get(rule, "source_address_start", "")
  end := object.get(rule, "source_address_end", start)
  cidr := allowed_cidrs[_]
  net.cidr_contains(cidr, start)
  net.cidr_contains(cidr, end)
}
