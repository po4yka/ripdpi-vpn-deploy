package terraform.policy.listener_family

listeners := {"value": [
  {"name": "xray", "protocol": "tcp", "port": 443, "port_range": null, "family": "ipv4"},
  {"name": "hop", "protocol": "udp", "port": null, "port_range": "20000-20100", "family": "ipv6"},
  {"name": "site", "protocol": "tcp", "port": 80, "port_range": null, "family": null},
]}

upcloud(rules) := {
  "variables": {"public_listeners": listeners},
  "resource_changes": [{
    "address": "upcloud_firewall_rules.vpn",
    "type": "upcloud_firewall_rules",
    "change": {"after": {"firewall_rule": rules}},
  }],
}

up_rule(family, protocol, start, end) := {
  "action": "accept", "direction": "in", "family": family, "protocol": protocol,
  "destination_port_start": start, "destination_port_end": end,
}

test_upcloud_denies_ipv6_rule_for_ipv4_listener {
  count(deny) == 1 with input as upcloud([up_rule("IPv6", "tcp", "443", "443")])
}

test_upcloud_denies_ipv4_rule_inside_ipv6_range {
  count(deny) == 1 with input as upcloud([up_rule("IPv4", "udp", "20000", "20100")])
}

test_upcloud_allows_stated_families_and_dual {
  count(deny) == 0 with input as upcloud([
    up_rule("IPv4", "tcp", "443", "443"),
    up_rule("IPv6", "udp", "20000", "20100"),
    up_rule("IPv4", "tcp", "80", "80"),
    up_rule("IPv6", "tcp", "80", "80"),
  ])
}

scaleway(rules) := {
  "variables": {"public_listeners": listeners},
  "resource_changes": [{
    "address": "scaleway_instance_security_group.vpn",
    "type": "scaleway_instance_security_group",
    "change": {"after": {"inbound_rule": rules}},
  }],
}

test_scaleway_denies_only_the_closed_family {
  count(deny) == 1 with input as scaleway([
    {"action": "accept", "protocol": "TCP", "port": 443, "port_range": null, "ip_range": "0.0.0.0/0"},
    {"action": "accept", "protocol": "TCP", "port": 443, "port_range": null, "ip_range": "::/0"},
  ])
}

hetzner(rules) := {
  "variables": {"public_listeners": listeners},
  "resource_changes": [{
    "address": "hcloud_firewall.vpn",
    "type": "hcloud_firewall",
    "change": {"after": {"rule": rules}},
  }],
}

test_hetzner_denies_dual_sources_for_ipv4_listener {
  count(deny) == 1 with input as hetzner([
    {"direction": "in", "protocol": "tcp", "port": "443", "source_ips": ["0.0.0.0/0", "::/0"]},
  ])
}

test_hetzner_allows_ipv4_sources_for_ipv4_listener {
  count(deny) == 0 with input as hetzner([
    {"direction": "in", "protocol": "tcp", "port": "443", "source_ips": ["0.0.0.0/0"]},
  ])
}

vultr(rule) := {
  "variables": {"public_listeners": listeners},
  "resource_changes": [{
    "address": "vultr_firewall_rule.tcp_public[\"v6-tcp-443\"]",
    "type": "vultr_firewall_rule",
    "change": {"after": rule},
  }],
}

test_vultr_denies_v6_rule_for_ipv4_listener {
  count(deny) == 1 with input as vultr({"protocol": "tcp", "port": "443", "ip_type": "v6", "subnet": "::", "subnet_size": 0})
}

test_vultr_allows_v4_rule_for_ipv4_listener {
  count(deny) == 0 with input as vultr({"protocol": "tcp", "port": "443", "ip_type": "v4", "subnet": "0.0.0.0", "subnet_size": 0})
}

test_dual_or_absent_family_closes_nothing {
  count(deny) == 0 with input as vultr({"protocol": "tcp", "port": "80", "ip_type": "v6", "subnet": "::", "subnet_size": 0})
}

test_hetzner_denies_omitted_sources_for_ipv4_listener {
  count(deny) == 1 with input as hetzner([{"direction": "in", "protocol": "tcp", "port": "443"}])
}

test_hetzner_denies_empty_sources_for_ipv4_listener {
  count(deny) == 1 with input as hetzner([{"direction": "in", "protocol": "tcp", "port": "443", "source_ips": []}])
}

test_rule_covering_part_of_a_closed_range_is_denied {
  count(deny) == 1 with input as upcloud([up_rule("IPv4", "udp", "20050", "20200")])
}

test_rule_outside_a_closed_range_is_allowed {
  count(deny) == 0 with input as upcloud([up_rule("IPv4", "udp", "20101", "20200")])
}

test_wildcard_protocol_rule_is_denied {
  count(deny) == 1 with input as vultr({"protocol": "any", "port": "443", "ip_type": "v6", "subnet": "::", "subnet_size": 0})
}

test_omitted_port_rule_is_denied {
  count(deny) == 1 with input as upcloud([{"action": "accept", "direction": "in", "family": "IPv6", "protocol": "tcp"}])
}

test_scaleway_omitted_range_admits_both_families {
  count(deny) == 1 with input as scaleway([
    {"action": "accept", "protocol": "TCP", "port": 443, "port_range": null, "ip_range": null},
  ])
}
