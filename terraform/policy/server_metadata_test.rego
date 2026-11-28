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

upcloud_default_drops := [
  {"action": "drop", "direction": "in", "family": "IPv4"},
  {"action": "drop", "direction": "in", "family": "IPv6"},
  {"action": "accept", "direction": "out"},
]

test_deny_upcloud_existing_server_keeps_firewall_off {
  result := deny with input as {
    "resource_changes": [
      unpromoted_server,
      {
        "address": "upcloud_firewall_rules.vpn",
        "type": "upcloud_firewall_rules",
        "change": {"actions": ["update"], "before": {}, "after": {"firewall_rule": upcloud_default_drops}},
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

test_allow_upcloud_first_creation {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "upcloud_server.fresh",
        "type": "upcloud_server",
        "change": {"actions": ["create"], "before": null, "after": {"firewall": false, "metadata": true}},
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
        "change": {"actions": ["create"], "before": null, "after": {"firewall_rule": upcloud_default_drops}},
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

test_scaleway_requires_explicit_inbound_default_drop {
  every_default_omission := [after |
    after := [{}, {"inbound_default_policy": null}][_]
    result := deny with input as {"resource_changes": [
      {"address": "scaleway_instance_security_group.vpn", "type": "scaleway_instance_security_group", "change": {"after": after}},
    ]}
    count(result) == 1
  ]
  count(every_default_omission) == 2
}

test_known_empty_and_unknown_empty_firewall_attachments_refuse {
  rejected := [unknown |
    unknown := [null, {}, {"firewall_ids": [false]}][_]
    result := deny with input as {"resource_changes": [
      {"address": "hcloud_server.vpn", "type": "hcloud_server", "change": {
        "after": {"firewall_ids": []}, "after_unknown": unknown,
      }},
    ]}
    count(result) == 1
  ]
  count(rejected) == 3
}

test_upcloud_final_drop_covers_all_inbound_traffic_for_each_family {
  restricted := {"action": "drop", "direction": "in", "family": "IPv6", "protocol": "tcp"}
  scoped := {"action": "drop", "direction": "in", "family": "IPv6", "source_address_start": "2001:db8::1"}
  rejected := [rules |
    rules := [[upcloud_default_drops[0]], array.concat(upcloud_default_drops, [restricted]),
              [upcloud_default_drops[0], scoped]][_]
    result := deny with input as {"resource_changes": [
      {"address": "upcloud_firewall_rules.vpn", "type": "upcloud_firewall_rules", "change": {
        "after": {"firewall_rule": rules},
      }},
    ]}
    count(result) == 1
    contains(result[_], "ipv6")
  ]
  count(rejected) == 3
}

test_upcloud_unscoped_final_inbound_drop_covers_both_families {
  result := deny with input as {"resource_changes": [
    {"address": "upcloud_firewall_rules.vpn", "type": "upcloud_firewall_rules", "change": {
      "after": {"firewall_rule": [{"action": "drop", "direction": "in"}]},
    }},
  ]}
  count(result) == 0
}

# -- an ordinary plan never deletes or replaces the server --

test_deny_server_replacement {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.replaced",
      "type": "upcloud_server",
      "change": {"actions": ["delete", "create"], "before": {"firewall": false}, "after": {"firewall": false, "metadata": true}},
    }]
  }
  count(result) == 1
}

test_deny_server_deletion {
  result := deny with input as {
    "resource_changes": [{
      "address": "hcloud_server.destroyed",
      "type": "hcloud_server",
      "change": {"actions": ["delete"], "before": {"firewall_ids": []}, "after": null},
    }]
  }
  count(result) == 1
}

test_allow_server_update_and_other_deletion {
  result := deny with input as {
    "resource_changes": [
      {
        "address": "hcloud_server.vpn",
        "type": "hcloud_server",
        "change": {"actions": ["update"], "after": {"metadata": true, "firewall_ids": [1001]}},
      },
      {
        "address": "hcloud_firewall.vpn",
        "type": "hcloud_firewall",
        "change": {"actions": ["delete"], "after": null},
      },
    ]
  }
  count(result) == 0
}
