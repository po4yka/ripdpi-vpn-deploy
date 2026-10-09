package terraform.policy.firewall

import future.keywords.in

# Provider APIs encode a single port as either a number or string, and ranges
# as strings or separate endpoints. Normalize before testing management ports.
port_contains(value, target) {
  regex.match(`^[0-9]+$`, sprintf("%v", [value]))
  to_number(value) == to_number(target)
}

port_contains(value, target) {
  is_string(value)
  regex.match(`^[0-9]+-[0-9]+$`, value)
  ends := split(value, "-")
  count(ends) == 2
  range_contains(ends[0], ends[1], target)
}

range_contains(start, end, target) {
  regex.match(`^[0-9]+$`, sprintf("%v", [start]))
  regex.match(`^[0-9]+$`, sprintf("%v", [end]))
  to_number(start) <= to_number(target)
  to_number(target) <= to_number(end)
}

upcloud_port_contains(rule, target) {
  start := object.get(rule, "destination_port_start", "")
  end := object.get(rule, "destination_port_end", start)
  range_contains(start, end, target)
}

upcloud_port_contains(rule, _) {
  object.get(rule, "destination_port_start", "") in {"", null}
  object.get(rule, "destination_port_end", "") in {"", null}
}

scaleway_port_contains(rule, target) {
  port_contains(object.get(rule, "port", null), target)
}

scaleway_port_contains(rule, target) {
  port_contains(object.get(rule, "port_range", ""), target)
}

scaleway_port_contains(rule, _) {
  object.get(rule, "port", null) == null
  object.get(rule, "port_range", "") in {"", null}
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
