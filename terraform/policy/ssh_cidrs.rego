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
  rule.protocol == "tcp"
  rule.destination_port_start == ssh_port

  source := rule.source_address_start
  not upcloud_source_allowed(source)

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
  rule.protocol == "TCP"
  sprintf("%v", [rule.port]) == ssh_port
  not allowed_cidrs[rule.ip_range]

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
  rule.protocol == "tcp"
  rule.port == ssh_port
  source_ip := rule.source_ips[_]
  not allowed_cidrs[source_ip]

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
  rc.change.after.protocol == "tcp"
  rc.change.after.port == ssh_port
  after := rc.change.after
  cidr := sprintf("%s/%d", [after.subnet, after.subnet_size])
  not allowed_cidrs[cidr]

  msg := sprintf(
    "resource %q: vultr SSH rule source CIDR %q is not in var.allowed_ssh_cidrs",
    [rc.address, cidr],
  )
}
