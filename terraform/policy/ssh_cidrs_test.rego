package terraform.policy.ssh_cidrs

# -- bad input: SSH rule sourced from a CIDR not in allowed list should deny --

test_deny_hcloud_ssh_unlisted_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "hcloud_firewall.vpn",
      "type": "hcloud_firewall",
      "change": {"after": {"rule": [{
        "direction": "in",
        "protocol": "tcp",
        "port": "22",
        "source_ips": ["198.51.100.99/32"],
      }]}},
    }],
  }
  count(result) == 1
}

test_deny_vultr_ssh_unlisted_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.ssh_0",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "22",
        "subnet": "198.51.100.99",
        "subnet_size": 32,
      }},
    }],
  }
  count(result) == 1
}

test_deny_upcloud_ssh_unlisted_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "upcloud_firewall_rules.vpn",
      "type": "upcloud_firewall_rules",
      "change": {"after": {"firewall_rule": [{
        "action": "accept",
        "direction": "in",
        "protocol": "tcp",
        "destination_port_start": "22",
        "comment": "SSH allow 198.51.100.99/32",
        "source_address_start": "198.51.100.99",
        "source_address_end": "198.51.100.99",
      }]}},
    }],
  }
  count(result) == 1
}

test_deny_scaleway_ssh_unlisted_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"after": {"inbound_rule": [{
        "action": "accept",
        "protocol": "TCP",
        "port": 22,
        "ip_range": "198.51.100.99/32",
      }]}},
    }],
  }
  count(result) == 1
}

# -- good input: SSH rule matching allowed CIDR should pass --

test_allow_hcloud_ssh_listed_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "hcloud_firewall.vpn",
      "type": "hcloud_firewall",
      "change": {"after": {"rule": [{
        "direction": "in",
        "protocol": "tcp",
        "port": "22",
        "source_ips": ["203.0.113.42/32"],
      }]}},
    }],
  }
  count(result) == 0
}

test_allow_vultr_ssh_listed_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "vultr_firewall_rule.ssh_0",
      "type": "vultr_firewall_rule",
      "change": {"after": {
        "protocol": "tcp",
        "port": "22",
        "subnet": "203.0.113.42",
        "subnet_size": 32,
      }},
    }],
  }
  count(result) == 0
}

test_allow_upcloud_ssh_listed_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "upcloud_firewall_rules.vpn",
      "type": "upcloud_firewall_rules",
      "change": {"after": {"firewall_rule": [{
        "action": "accept",
        "direction": "in",
        "protocol": "tcp",
        "destination_port_start": "22",
        "comment": "SSH allow 203.0.113.42/32",
        "source_address_start": "203.0.113.42",
        "source_address_end": "203.0.113.42",
      }]}},
    }],
  }
  count(result) == 0
}

test_allow_scaleway_ssh_listed_cidr {
  result := deny with input as {
    "variables": {"allowed_ssh_cidrs": {"value": ["203.0.113.42/32"]}},
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"after": {"inbound_rule": [{
        "action": "accept",
        "protocol": "TCP",
        "port": 22,
        "ip_range": "203.0.113.42/32",
      }]}},
    }],
  }
  count(result) == 0
}
