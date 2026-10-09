package terraform.policy.firewall_test

import data.terraform.policy.admin_port
import data.terraform.policy.firewall
import data.terraform.policy.ssh_cidrs

variables := {
  "ssh_port": {"value": 2222},
  "allowed_ssh_cidrs": {"value": ["192.0.2.20/32"]},
}

world_ranges := [
  {"address": "hcloud_firewall.vpn", "type": "hcloud_firewall", "change": {"after": {"rule": [{
    "direction": "in", "protocol": "tcp", "port": "2000-4000", "source_ips": ["0.0.0.0/0"],
  }]}}},
  {"address": "vultr_firewall_rule.public", "type": "vultr_firewall_rule", "change": {"after": {
    "protocol": "tcp", "port": "2000-4000", "subnet": "0.0.0.0", "subnet_size": 0,
  }}},
  {"address": "scaleway_instance_security_group.vpn", "type": "scaleway_instance_security_group", "change": {"after": {"inbound_rule": [{
    "action": "accept", "protocol": "TCP", "port": null, "port_range": "2000-4000", "ip_range": "::/0",
  }]}}},
  {"address": "upcloud_firewall_rules.vpn", "type": "upcloud_firewall_rules", "change": {"after": {"firewall_rule": [{
    "action": "accept", "direction": "in", "protocol": "tcp",
    "destination_port_start": "2000", "destination_port_end": "4000",
    "source_address_start": "", "source_address_end": "",
  }]}}},
]

test_reject_world_management_ranges_all_providers {
  denied := [resource |
    resource := world_ranges[_]
    result := admin_port.deny with input as {"variables": variables, "resource_changes": [resource]}
    count(result) == 2
  ]
  count(denied) == 4
}

test_reject_undocumented_ssh_sources_inside_ranges_all_providers {
  denied := [resource |
    resource := world_ranges[_]
    result := ssh_cidrs.deny with input as {"variables": variables, "resource_changes": [resource]}
    count(result) == 1
  ]
  count(denied) == 4
}

test_upcloud_omitted_source_is_world {
  result := admin_port.deny with input as {
    "variables": variables,
    "resource_changes": [{"address": "upcloud_firewall_rules.vpn", "type": "upcloud_firewall_rules", "change": {"after": {"firewall_rule": [{
      "action": "accept", "direction": "in", "protocol": "tcp",
      "destination_port_start": "3389", "destination_port_end": "3389",
    }]}}}],
  }
  count(result) == 1
}

test_upcloud_source_range_must_fit_the_allowed_network {
  result := ssh_cidrs.deny with input as {
    "variables": variables,
    "resource_changes": [{"address": "upcloud_firewall_rules.vpn", "type": "upcloud_firewall_rules", "change": {"after": {"firewall_rule": [{
      "action": "accept", "direction": "in", "protocol": "tcp",
      "destination_port_start": "2222", "destination_port_end": "2222",
      "source_address_start": "192.0.2.20", "source_address_end": "192.0.2.200",
    }]}}}],
  }
  count(result) == 1
}

test_scoped_ssh_range_is_allowed {
  resource := {"address": "hcloud_firewall.vpn", "type": "hcloud_firewall", "change": {"after": {"rule": [{
    "direction": "in", "protocol": "tcp", "port": "2221-2223", "source_ips": ["192.0.2.20/32"],
  }]}}}
  admin := admin_port.deny with input as {"variables": variables, "resource_changes": [resource]}
  sources := ssh_cidrs.deny with input as {"variables": variables, "resource_changes": [resource]}
  count(admin) == 0
  count(sources) == 0
}

test_nonoverlapping_public_range_is_allowed {
  resource := {"address": "hcloud_firewall.vpn", "type": "hcloud_firewall", "change": {"after": {"rule": [{
    "direction": "in", "protocol": "tcp", "port": "4001-5000", "source_ips": ["::/0"],
  }]}}}
  admin := admin_port.deny with input as {"variables": variables, "resource_changes": [resource]}
  sources := ssh_cidrs.deny with input as {"variables": variables, "resource_changes": [resource]}
  count(admin) == 0
  count(sources) == 0
}

# Conservative matching must not raise parser errors under strict verification.
test_unknown_or_malformed_selectors_cover_management {
  selectors := [null, "", "invalid", 0, "0", 22.5, "2300-2200", "2200:bad", "1-65536"]
  matches := [selector |
    selector := selectors[_]
    firewall.port_contains(selector, 2222)
  ]
  count(matches) == count(selectors)
}

test_colon_ranges_include_both_endpoints {
  firewall.port_contains("2222:2300", 2222)
  firewall.port_contains("2200:2222", 2222)
  not firewall.port_contains("2223:2300", 2222)
}

test_malformed_upcloud_interval_covers_management {
  firewall.upcloud_port_contains({"destination_port_start": "invalid", "destination_port_end": "2300"}, 2222)
  firewall.upcloud_port_contains({}, 2222)
}

test_unspecified_and_any_protocol_cover_tcp {
  firewall.tcp_protocol(null)
  firewall.tcp_protocol("")
  firewall.tcp_protocol("ANY")
  firewall.tcp_protocol("TCP")
  not firewall.tcp_protocol("udp")
}

test_noncanonical_zero_prefix_sources_are_world {
  firewall.world_cidr("192.0.2.20/0")
  firewall.world_cidr("2001:db8::20/00")
  firewall.world_cidr(null)
  not firewall.world_cidr("192.0.2.0/24")
}

test_upcloud_null_endpoints_are_world {
  firewall.upcloud_is_world({"source_address_start": null, "source_address_end": null})
}

test_cached_plan_management_port_must_be_integer {
  invalid_ports := [22.5, null, "22", 0, 65536]
  rejected := [port |
    port := invalid_ports[_]
    not ssh_cidrs.valid_ssh_port with input as {"variables": {"ssh_port": {"value": port}}}
  ]
  count(rejected) == count(invalid_ports)
  ssh_cidrs.valid_ssh_port with input as {"variables": {"ssh_port": {"value": 22}}}
}
