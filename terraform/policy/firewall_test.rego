package terraform.policy.firewall_test

import data.terraform.policy.admin_port
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
