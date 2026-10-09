package terraform.policy.firewall

import future.keywords.in

# Provider selectors are either singletons or inclusive hyphen/colon ranges.
valid_selector(selector) {
  text := sprintf("%v", [selector])
  regex.match("^[1-9][0-9]*$", text)
  to_number(text) <= 65535
}

valid_selector(selector) {
  text := replace(sprintf("%v", [selector]), ":", "-")
  regex.match("^[1-9][0-9]*-[1-9][0-9]*$", text)
  bounds := split(text, "-")
  to_number(bounds[0]) <= to_number(bounds[1])
  to_number(bounds[1]) <= 65535
}

# Omitted selectors mean all ports on these edges. Unknown/malformed selectors
# conservatively match management too, so exposure checks refuse uncertain rules.
port_contains(selector, port) {
  not valid_selector(selector)
}

port_contains(selector, port) {
  regex.match("^[1-9][0-9]*$", sprintf("%v", [selector]))
  to_number(selector) == to_number(port)
}

port_contains(selector, port) {
  text := replace(sprintf("%v", [selector]), ":", "-")
  regex.match("^[1-9][0-9]*-[1-9][0-9]*$", text)
  bounds := split(text, "-")
  count(bounds) == 2
  to_number(bounds[0]) <= to_number(port)
  to_number(port) <= to_number(bounds[1])
}

range_contains(start, end, port) {
  valid_selector(sprintf("%v-%v", [start, end]))
  to_number(start) <= to_number(port)
  to_number(port) <= to_number(end)
}

range_contains(start, end, port) {
  not valid_selector(sprintf("%v-%v", [start, end]))
}

empty_selector(selector) {
  {null, "", 0, "0"}[selector]
}

scaleway_port_contains(rule, port) {
  selector := object.get(rule, "port", null)
  not empty_selector(selector)
  port_contains(selector, port)
}

scaleway_port_contains(rule, port) {
  selector := object.get(rule, "port_range", null)
  not empty_selector(selector)
  port_contains(selector, port)
}

scaleway_port_contains(rule, port) {
  empty_selector(object.get(rule, "port", null))
  empty_selector(object.get(rule, "port_range", null))
}

tcp_protocol(protocol) {
  is_string(protocol)
  {"tcp", "any", ""}[lower(protocol)]
}

tcp_protocol(protocol) {
  protocol == null
}

world_cidr(cidr) {
  is_string(cidr)
  parts := split(cidr, "/")
  count(parts) == 2
  regex.match("^[0-9]+$", parts[1])
  to_number(parts[1]) == 0
}

world_cidr(cidr) {
  {null, ""}[cidr]
}

# UpCloud accepts omitted destination selectors as all ports.
upcloud_port_contains(rule, port) {
  start := object.get(rule, "destination_port_start", "")
  end := object.get(rule, "destination_port_end", start)
  range_contains(start, end, port)
}

upcloud_is_world(rule) {
  object.get(rule, "source_address_start", "") in {"", null}
  object.get(rule, "source_address_end", "") in {"", null}
}

upcloud_is_world(rule) {
  rule.source_address_start == "0.0.0.0"
  rule.source_address_end == "255.255.255.255"
}

upcloud_is_world(rule) {
  rule.source_address_start == "::"
  rule.source_address_end == "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
}

# Hetzner defaults an omitted source set to unrestricted sources.
hcloud_is_world(rule) {
  world_cidr(rule.source_ips[_])
}

hcloud_is_world(rule) {
  count(object.get(rule, "source_ips", [])) == 0
}

hcloud_is_world(rule) {
  object.get(rule, "source_ips", null) == null
}
