package terraform.policy.egress_address

test_deny_auto_deleted_primary_ip {
  result := deny with input as {"resource_changes": [{
    "address": "hcloud_primary_ip.egress",
    "type": "hcloud_primary_ip",
    "change": {"actions": ["create"], "after": {"auto_delete": true}},
  }]}
  count(result) == 1
}

test_deny_primary_ip_without_auto_delete_value {
  result := deny with input as {"resource_changes": [{
    "address": "hcloud_primary_ip.egress",
    "type": "hcloud_primary_ip",
    "change": {"actions": ["create"], "after": {}},
  }]}
  count(result) == 1
}

test_allow_retained_primary_ip {
  result := deny with input as {"resource_changes": [{
    "address": "hcloud_primary_ip.egress",
    "type": "hcloud_primary_ip",
    "change": {"actions": ["create"], "after": {"auto_delete": false}},
  }]}
  count(result) == 0
}
