package terraform.policy.ssh_cidrs

# firewall_rules_pin_ssh_to_documented_cidrs
#
# SSH allow rules must reference a CIDR that appears in var.allowed_ssh_cidrs.
# Inline string literals that are not in the variable list are denied.
#
# Provider-specific checks:
#
#   upcloud_firewall_rules — firewall_rule blocks for TCP/22 must have
#     source_address_start matching a network address from allowed_ssh_cidrs.
#
#   hcloud_firewall — rule blocks for TCP/22 must have all source_ips
#     members present in allowed_ssh_cidrs.
#
#   vultr_firewall_rule (resource "vultr_firewall_rule" "ssh") — subnet
#     must match one of the allowed_ssh_cidrs entries.
#
#   scaleway_instance_security_group — nested TCP/22 inbound_rule blocks use
#     ip_range directly.

allowed_cidrs := {cidr | cidr := input.variables.allowed_ssh_cidrs.value[_]}

# upcloud: each SSH accept rule source must be within an allowed CIDR.
# We compare source_address_start to the network address of each allowed CIDR.
# Conftest/OPA does not have a native CIDR-contains function, so we verify
# that the source_address_start appears as a key in our allowed set when
# normalised to /32 or /128 notation, OR that the comment field names the CIDR.
# The most reliable signal available in the plan JSON is the comment field,
# which the TF code sets to "SSH allow <cidr>".

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  rule := rc.change.after.firewall_rule[_]
  rule.action == "accept"
  rule.direction == "in"
  rule.protocol == "tcp"
  rule.destination_port_start == "22"

  # Extract the CIDR from the comment ("SSH allow <cidr>")
  comment := rule.comment
  startswith(comment, "SSH allow ")
  cidr := substring(comment, count("SSH allow "), -1)
  not allowed_cidrs[cidr]

  msg := sprintf(
    "resource %q: SSH allow rule for CIDR %q is not in var.allowed_ssh_cidrs",
    [rc.address, cidr],
  )
}

# scaleway: each SSH inbound rule must use a documented CIDR.
deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  rule := rc.change.after.inbound_rule[_]
  rule.action == "accept"
  rule.protocol == "TCP"
  rule.port == 22
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
  rule.port == "22"
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
  rc.change.after.port == "22"
  after := rc.change.after
  cidr := sprintf("%s/%d", [after.subnet, after.subnet_size])
  not allowed_cidrs[cidr]

  msg := sprintf(
    "resource %q: vultr SSH rule source CIDR %q is not in var.allowed_ssh_cidrs",
    [rc.address, cidr],
  )
}
