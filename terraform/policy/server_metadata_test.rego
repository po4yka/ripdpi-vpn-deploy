package terraform.policy.server_metadata

# -- bad input: metadata explicitly disabled should deny --

test_deny_upcloud_metadata_false {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"metadata": false}},
    }]
  }
  count(result) == 1
}

test_deny_hcloud_metadata_false {
  result := deny with input as {
    "resource_changes": [{
      "address": "hcloud_server.vpn",
      "type": "hcloud_server",
      "change": {"after": {"metadata": false}},
    }]
  }
  count(result) == 1
}

# -- good input: metadata enabled or absent should pass --

test_allow_upcloud_metadata_true {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"metadata": true}},
    }]
  }
  count(result) == 0
}

test_allow_vultr_no_metadata_attribute {
  # vultr_instance does not surface metadata in the plan; rule must not fire
  result := deny with input as {
    "resource_changes": [{
      "address": "vultr_instance.vpn",
      "type": "vultr_instance",
      "change": {"after": {"hostname": "vpn-test"}},
    }]
  }
  count(result) == 0
}

test_allow_scaleway_no_metadata_attribute {
  result := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_server.vpn",
      "type": "scaleway_instance_server",
      "change": {"after": {"name": "vpn-test"}},
    }]
  }
  count(result) == 0
}

# -- provider firewall: an active edge firewall must not be turned off in place --

test_deny_upcloud_firewall_turned_off {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"before": {"firewall": true}, "after": {"firewall": false, "metadata": true}},
    }]
  }
  count(result) == 1
}

test_allow_upcloud_firewall_bootstrap_and_promotion {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "upcloud_server.fresh",
        "type": "upcloud_server",
        "change": {"before": null, "after": {"firewall": false, "metadata": true}},
      },
      {
        "address": "upcloud_server.promoted",
        "type": "upcloud_server",
        "change": {"before": {"firewall": false}, "after": {"firewall": true, "metadata": true}},
      },
      {
        "address": "upcloud_server.destroyed",
        "type": "upcloud_server",
        "change": {"before": {"firewall": true}, "after": null},
      },
    ]
  }
  count(result) == 0
}
