package terraform.policy.ports

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
covers(selector, port) {
  not valid_selector(selector)
}

covers(selector, port) {
  to_number(selector) == to_number(port)
}

covers(selector, port) {
  bounds := split(replace(sprintf("%v", [selector]), ":", "-"), "-")
  count(bounds) == 2
  to_number(bounds[0]) <= to_number(port)
  to_number(port) <= to_number(bounds[1])
}

interval_covers(start, end, port) {
  to_number(start) <= to_number(port)
  to_number(port) <= to_number(end)
}

interval_covers(start, end, port) {
  not valid_selector(sprintf("%v-%v", [start, end]))
}

empty_selector(selector) {
  {null, "", 0, "0"}[selector]
}

scaleway_covers(rule, port) {
  selector := object.get(rule, "port", null)
  not empty_selector(selector)
  covers(selector, port)
}

scaleway_covers(rule, port) {
  selector := object.get(rule, "port_range", null)
  not empty_selector(selector)
  covers(selector, port)
}

scaleway_covers(rule, port) {
  empty_selector(object.get(rule, "port", null))
  empty_selector(object.get(rule, "port_range", null))
}

tcp_protocol(protocol) {
  {"tcp", "any", ""}[lower(protocol)]
}

tcp_protocol(protocol) {
  protocol == null
}

world_cidr(cidr) {
  parts := split(cidr, "/")
  count(parts) == 2
  to_number(parts[1]) == 0
}

world_cidr(cidr) {
  {null, ""}[cidr]
}
