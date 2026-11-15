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
      "change": {"after": {"metadata": false, "firewall_ids": [1001]}},
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
      "change": {"after": {"hostname": "vpn-test", "firewall_group_id": "group-1"}},
    }]
  }
  count(result) == 0
}

test_allow_scaleway_no_metadata_attribute {
  result := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_server.vpn",
      "type": "scaleway_instance_server",
      "change": {"after": {"name": "vpn-test", "security_group_id": "group-1"}},
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
      "change": {"actions": ["update"], "before": {"firewall": true}, "after": {"firewall": false, "metadata": true}},
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

# -- provider firewall: an existing node must not stay without it across a change --

unpromoted_server := {
  "address": "upcloud_server.vpn",
  "type": "upcloud_server",
  "change": {"actions": ["no-op"], "before": {"firewall": false}, "after": {"firewall": false, "metadata": true}},
}

test_deny_upcloud_existing_server_keeps_firewall_off {
  result := deny with input as {
    "resource_changes": [
      unpromoted_server,
      {
        "address": "upcloud_firewall_rules.vpn",
        "type": "upcloud_firewall_rules",
        "change": {"actions": ["update"], "before": {}, "after": {}},
      },
    ]
  }
  count(result) == 1
  contains(result[_], "promote the node first")
}

test_deny_upcloud_server_update_keeps_firewall_off {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"actions": ["update"], "before": {"firewall": false}, "after": {"firewall": false, "metadata": true}},
    }]
  }
  count(result) == 1
}

test_allow_upcloud_first_creation_and_replacement {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "upcloud_server.fresh",
        "type": "upcloud_server",
        "change": {"actions": ["create"], "before": null, "after": {"firewall": false, "metadata": true}},
      },
      {
        "address": "upcloud_server.replaced",
        "type": "upcloud_server",
        "change": {"actions": ["delete", "create"], "before": {"firewall": false}, "after": {"firewall": false, "metadata": true}},
      },
    ]
  }
  count(result) == 0
}

test_allow_upcloud_promotion_plan {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"actions": ["update"], "before": {"firewall": false}, "after": {"firewall": true, "metadata": true}},
    }]
  }
  count(result) == 0
}

test_allow_upcloud_interrupted_first_apply_and_empty_plan {
  finishing := deny with input as {
    "resource_changes": [
      unpromoted_server,
      {
        "address": "upcloud_firewall_rules.vpn",
        "type": "upcloud_firewall_rules",
        "change": {"actions": ["create"], "before": null, "after": {}},
      },
    ]
  }
  count(finishing) == 0
  empty := deny with input as {"resource_changes": [unpromoted_server]}
  count(empty) == 0
}

# -- every other provider attaches its firewall on the server resource --

test_deny_server_without_provider_firewall {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "hcloud_server.vpn",
        "type": "hcloud_server",
        "change": {"actions": ["create"], "after": {"firewall_ids": []}, "after_unknown": {"id": true}},
      },
      {
        "address": "vultr_instance.vpn",
        "type": "vultr_instance",
        "change": {"actions": ["update"], "after": {"firewall_group_id": ""}, "after_unknown": {"firewall_group_id": false}},
      },
      {
        "address": "scaleway_instance_server.vpn",
        "type": "scaleway_instance_server",
        "change": {"actions": ["create"], "after": {"name": "vpn-test"}},
      },
    ]
  }
  count(result) == 3
}

test_allow_server_with_known_or_pending_provider_firewall {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "hcloud_server.created",
        "type": "hcloud_server",
        "change": {"actions": ["create"], "after": {}, "after_unknown": {"firewall_ids": true}},
      },
      {
        "address": "hcloud_server.element",
        "type": "hcloud_server",
        "change": {"actions": ["create"], "after": {"firewall_ids": [null]}, "after_unknown": {"firewall_ids": [true]}},
      },
      {
        "address": "hcloud_server.existing",
        "type": "hcloud_server",
        "change": {"actions": ["no-op"], "after": {"firewall_ids": [1001]}, "after_unknown": {}},
      },
      {
        "address": "vultr_instance.vpn",
        "type": "vultr_instance",
        "change": {"actions": ["no-op"], "after": {"firewall_group_id": "group-1"}},
      },
      {
        "address": "scaleway_instance_server.vpn",
        "type": "scaleway_instance_server",
        "change": {"actions": ["create"], "after": {}, "after_unknown": {"security_group_id": true}},
      },
      {
        "address": "hcloud_server.destroyed",
        "type": "hcloud_server",
        "change": {"actions": ["delete"], "before": {"firewall_ids": []}, "after": null},
      },
    ]
  }
  count(result) == 0
}

test_scaleway_inbound_default_policy {
  accept := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"actions": ["create"], "after": {"inbound_default_policy": "accept"}},
    }]
  }
  count(accept) == 1
  drop := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_security_group.vpn",
      "type": "scaleway_instance_security_group",
      "change": {"actions": ["create"], "after": {"inbound_default_policy": "drop"}},
    }]
  }
  count(drop) == 0
}
