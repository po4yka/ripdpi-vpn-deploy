package terraform.policy.secondary_ip

# -- bad input: secondary IP without opt-in should deny --

test_deny_upcloud_two_public_ifaces_no_opt_in {
  result := deny with input as {
    "variables": {"additional_public_ip": {"value": false}},
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"network_interface": [
        {"type": "public"},
        {"type": "public"},
        {"type": "utility"},
      ]}},
    }],
  }
  count(result) == 1
}

test_deny_hcloud_floating_ip_no_opt_in {
  result := deny with input as {
    "variables": {"additional_public_ip": {"value": false}},
    "resource_changes": [{
      "address": "hcloud_floating_ip.honeypot_ipv4",
      "type": "hcloud_floating_ip",
      "change": {"actions": ["create"], "after": {}},
    }],
  }
  count(result) == 1
}

test_deny_vultr_instance_ipv4_no_opt_in {
  result := deny with input as {
    "variables": {"additional_public_ip": {"value": false}},
    "resource_changes": [{
      "address": "vultr_instance_ipv4.honeypot",
      "type": "vultr_instance_ipv4",
      "change": {"actions": ["create"], "after": {}},
    }],
  }
  count(result) == 1
}

# -- good input: secondary IP with opt-in should pass --

test_allow_upcloud_two_public_ifaces_with_opt_in {
  result := deny with input as {
    "variables": {"additional_public_ip": {"value": true}},
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"network_interface": [
        {"type": "public"},
        {"type": "public"},
        {"type": "utility"},
      ]}},
    }],
  }
  count(result) == 0
}

test_allow_single_public_iface_no_opt_in {
  result := deny with input as {
    "variables": {"additional_public_ip": {"value": false}},
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"network_interface": [
        {"type": "public"},
        {"type": "utility"},
      ]}},
    }],
  }
  count(result) == 0
}
