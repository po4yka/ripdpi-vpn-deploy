package terraform.policy.admin_port

# -- bad input: world-open SSH should deny --

test_deny_upcloud_ssh_world_open_ipv4 {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "upcloud_firewall_rules.vpn",
      "type": "upcloud_firewall_rules",
      "change": {"after": {"firewall_rule": [{
        "action": "accept",
        "direction": "in",
        "protocol": "tcp",
        "destination_port_start": "22",
        "source_address_start": "0.0.0.0",
        "source_address_end": "255.255.255.255",
      }]}},
    }]
  }
  count(result) == 1
}

test_deny_upcloud_ssh_world_open_ipv6 {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "upcloud_firewall_rules.vpn",
      "type": "upcloud_firewall_rules",
      "change": {"after": {"firewall_rule": [{
        "action": "accept",
        "direction": "in",
        "protocol": "tcp",
        "destination_port_start": "22",
        "source_address_start": "::",
        "source_address_end": "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",
      }]}},
    }]
  }
  count(result) == 1
}

test_deny_hcloud_ssh_world_open {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "hcloud_firewall.vpn",
      "type": "hcloud_firewall",
      "change": {"after": {"rule": [{
        "direction": "in",
        "protocol": "tcp",
        "port": "22",
        "source_ips": ["0.0.0.0/0", "::/0"],
      }]}},
    }]
  }
  count(result) >= 1
}

test_deny_vultr_ssh_world_open {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.ssh_world",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "22",
        "subnet": "0.0.0.0",
        "subnet_size": 0,
      }},
    }]
  }
  count(result) == 1
}

test_deny_scaleway_ssh_world_open {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"after": {"inbound_rule": [{
        "action": "accept",
        "protocol": "TCP",
        "port": 22,
        "ip_range": "0.0.0.0/0",
      }]}},
    }]
  }
  count(result) == 1
}

# -- good input: SSH restricted to specific CIDR should pass --

test_allow_upcloud_ssh_restricted_cidr {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "upcloud_firewall_rules.vpn",
      "type": "upcloud_firewall_rules",
      "change": {"after": {"firewall_rule": [{
        "action": "accept",
        "direction": "in",
        "protocol": "tcp",
        "destination_port_start": "22",
        "source_address_start": "203.0.113.42",
        "source_address_end": "203.0.113.42",
      }]}},
    }]
  }
  count(result) == 0
}

test_allow_hcloud_ssh_restricted_cidr {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "hcloud_firewall.vpn",
      "type": "hcloud_firewall",
      "change": {"after": {"rule": [{
        "direction": "in",
        "protocol": "tcp",
        "port": "22",
        "source_ips": ["203.0.113.42/32"],
      }]}},
    }]
  }
  count(result) == 0
}

test_allow_vultr_tcp_443_world_open {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.reality",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "443",
        "subnet": "0.0.0.0",
        "subnet_size": 0,
      }},
    }]
  }
  count(result) == 0
}

test_allow_scaleway_ssh_restricted_cidr {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 22}},
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"after": {"inbound_rule": [{
        "action": "accept",
        "protocol": "TCP",
        "port": 22,
        "ip_range": "203.0.113.42/32",
      }]}},
    }]
  }
  count(result) == 0
}

# -- custom ssh_port: the pinned port must follow var.ssh_port, not literal 22 --

test_deny_vultr_custom_ssh_port_world_open {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 2222}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.ssh_world",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "2222",
        "subnet": "0.0.0.0",
        "subnet_size": 0,
      }},
    }]
  }
  count(result) == 1
}

test_allow_vultr_custom_ssh_port_restricted {
  result := deny with input as {
    "variables": {"ssh_port": {"value": 2222}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.ssh_0",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "2222",
        "subnet": "203.0.113.42",
        "subnet_size": 32,
      }},
    }]
  }
  count(result) == 0
}
