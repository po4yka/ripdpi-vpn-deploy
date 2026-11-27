package terraform.policy.listener_family

import data.terraform.policy.firewall
import future.keywords.in

# closed_family_listener_rule
#
# Deny a world-open provider rule that admits any port of a single-family
# public listener on the other address family. The family comes from the
# plan's own public_listeners input, so the saved plan cannot open a family
# that the contract closes. An absent or dual family closes nothing.

closed := {"ipv4": "ipv6", "ipv6": "ipv4"}

closed_listeners[listener] {
  listener := input.variables.public_listeners.value[_]
  closed[object.get(listener, "family", null)]
}

listener_bounds(listener) := [listener.port, listener.port] {
  object.get(listener, "port", null) != null
}

listener_bounds(listener) := [to_number(bounds[0]), to_number(bounds[1])] {
  object.get(listener, "port", null) == null
  bounds := split(listener.port_range, "-")
}

# An omitted or malformed provider selector means every port. The branches must
# exclude each other: an out-of-range or reversed selector that also matched a
# shape branch made the function conflict and stopped the whole evaluation.
selector_bounds(selector) := [to_number(text), to_number(text)] {
  firewall.valid_selector(selector)
  text := sprintf("%v", [selector])
  regex.match("^[1-9][0-9]*$", text)
}

selector_bounds(selector) := [to_number(bounds[0]), to_number(bounds[1])] {
  firewall.valid_selector(selector)
  text := replace(sprintf("%v", [selector]), ":", "-")
  regex.match("^[1-9][0-9]*-[1-9][0-9]*$", text)
  bounds := split(text, "-")
}

selector_bounds(selector) := [1, 65535] {
  not firewall.valid_selector(selector)
}

overlaps(rule_bounds, listener) {
  bounds := listener_bounds(listener)
  rule_bounds[0] <= bounds[1]
  rule_bounds[1] >= bounds[0]
}

# An omitted or "any" provider protocol admits every protocol.
protocol_matches(rule_protocol, listener) {
  lower(sprintf("%v", [rule_protocol])) == listener.protocol
}

protocol_matches(rule_protocol, listener) {
  {"", "any"}[lower(sprintf("%v", [rule_protocol]))]
}

protocol_matches(rule_protocol, listener) {
  rule_protocol == null
}

# Address families admitted by one world-open source CIDR; an omitted CIDR admits both.
cidr_families(cidr) := {"ipv6"} {
  is_string(cidr)
  contains(cidr, ":")
}

cidr_families(cidr) := {"ipv4"} {
  is_string(cidr)
  cidr != ""
  not contains(cidr, ":")
}

cidr_families(cidr) := {"ipv4", "ipv6"} {
  {null, ""}[cidr]
}

message(address, listener, family) := sprintf(
  "resource %q: %s %s is stated %s but the provider admits %s",
  [address, upper(listener.protocol), listener.name, listener.family, family],
)

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "upcloud_firewall_rules"
  rule := rc.change.after.firewall_rule[_]
  rule.action == "accept"
  rule.direction == "in"
  listener := closed_listeners[_]
  family := closed[listener.family]
  lower(rule.family) == family
  protocol_matches(object.get(rule, "protocol", null), listener)
  firewall.upcloud_is_world(rule)
  start := object.get(rule, "destination_port_start", "")
  end := object.get(rule, "destination_port_end", start)
  overlaps(selector_bounds(sprintf("%v-%v", [start, end])), listener)
  msg := message(rc.address, listener, family)
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_security_group"
  rule := rc.change.after.inbound_rule[_]
  rule.action == "accept"
  listener := closed_listeners[_]
  family := closed[listener.family]
  cidr := object.get(rule, "ip_range", null)
  firewall.world_cidr(cidr)
  family in cidr_families(cidr)
  protocol_matches(object.get(rule, "protocol", null), listener)
  selector := scaleway_selector(rule)
  overlaps(selector_bounds(selector), listener)
  msg := message(rc.address, listener, family)
}

scaleway_selector(rule) := object.get(rule, "port", null) {
  not firewall.empty_selector(object.get(rule, "port", null))
}

scaleway_selector(rule) := object.get(rule, "port_range", null) {
  firewall.empty_selector(object.get(rule, "port", null))
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "hcloud_firewall"
  rule := rc.change.after.rule[_]
  rule.direction == "in"
  listener := closed_listeners[_]
  family := closed[listener.family]
  family in hcloud_families(rule)
  protocol_matches(object.get(rule, "protocol", null), listener)
  overlaps(selector_bounds(object.get(rule, "port", null)), listener)
  msg := message(rc.address, listener, family)
}

hcloud_families(rule) := {family |
  source := rule.source_ips[_]
  firewall.world_cidr(source)
  family := cidr_families(source)[_]
} {
  not hcloud_unrestricted(rule)
}

# Hetzner treats an omitted source set as unrestricted on both families.
hcloud_families(rule) := {"ipv4", "ipv6"} {
  hcloud_unrestricted(rule)
}

hcloud_unrestricted(rule) {
  object.get(rule, "source_ips", null) == null
}

hcloud_unrestricted(rule) {
  count(object.get(rule, "source_ips", [])) == 0
}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "vultr_firewall_rule"
  rule := rc.change.after
  listener := closed_listeners[_]
  family := closed[listener.family]
  rule.ip_type == {"ipv4": "v4", "ipv6": "v6"}[family]
  rule.subnet_size == 0
  protocol_matches(object.get(rule, "protocol", null), listener)
  overlaps(selector_bounds(object.get(rule, "port", null)), listener)
  msg := message(rc.address, listener, family)
}
