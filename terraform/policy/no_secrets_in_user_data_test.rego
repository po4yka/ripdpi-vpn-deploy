package terraform.policy.no_secrets_in_user_data

# -- bad input: plaintext password in user_data should deny --

test_deny_on_plaintext_password {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "password=hunter2secret\n"}},
    }]
  }
  count(result) == 1
}

test_deny_on_plaintext_token {
  result := deny with input as {
    "resource_changes": [{
      "address": "hcloud_server.vpn",
      "type": "hcloud_server",
      "change": {"after": {"user_data": "token=ghp_abcdefghijklmnop\n"}},
    }]
  }
  count(result) == 1
}

test_deny_on_plaintext_api_key {
  result := deny with input as {
    "resource_changes": [{
      "address": "vultr_instance.vpn",
      "type": "vultr_instance",
      "change": {"after": {"user_data": "api_key=SOMEAPIKEY123456\n"}},
    }]
  }
  count(result) == 1
}

test_deny_scaleway_cloud_init_map_with_plaintext_secret {
  result := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_server.vpn",
      "type": "scaleway_instance_server",
      "change": {"after": {"user_data": {"cloud-init": "#cloud-config\nsecret=plaintextvalue\n"}}},
    }]
  }
  count(result) == 1
}

test_deny_on_plaintext_secret {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "secret=mysecretvalue123\n"}},
    }]
  }
  count(result) == 1
}

# -- good input: SSH public key in authorized_keys should NOT deny --

test_allow_ssh_authorized_keys_block {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "ssh_authorized_keys:\n  - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI test@harness\n"}},
    }]
  }
  count(result) == 0
}

test_allow_normal_cloud_init_with_no_secrets {
  result := deny with input as {
    "resource_changes": [{
      "address": "hcloud_server.vpn",
      "type": "hcloud_server",
      "change": {"after": {"user_data": "#cloud-config\npackages:\n  - python3\n  - sudo\n"}},
    }]
  }
  count(result) == 0
}

test_allow_null_user_data {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": null}},
    }]
  }
  count(result) == 0
}

# -- multiline user_data: secret on a non-first line must still be caught --
# Validates that the (?im) flags make ^ anchor per-line, not just string-start.
# Without (?m), the regex would only match if the keyword is at byte-0 of the blob.
test_deny_on_secret_in_multiline_user_data {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "#cloud-config\npackages:\n  - python3\npassword: hunter2secret\n"}},
    }]
  }
  count(result) == 1
}

test_allow_non_server_resource_type {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_network.vpn",
      "type": "upcloud_network",
      "change": {"after": {"user_data": "password=shouldbeignored\n"}},
    }]
  }
  count(result) == 0
}

# -- quoted keys (yamlencode), cloud-init account passwords and private keys --

test_deny_quoted_yaml_password {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "#cloud-config\n\"password\": \"hunter2hunter2\"\n"}},
    }]
  }
  count(result) == 1
}

test_deny_cloud_init_account_password {
  result := deny with input as {
    "resource_changes": [{
      "address": "vultr_instance.vpn",
      "type": "vultr_instance",
      "change": {"after": {"user_data": "users:\n  - name: deploy\n    hashed_passwd: $6$rounds=4096$abcdefgh\n"}},
    }]
  }
  count(result) == 1
}

test_deny_private_key_block {
  result := deny with input as {
    "resource_changes": [{
      "address": "scaleway_instance_server.vpn",
      "type": "scaleway_instance_server",
      "change": {"after": {"user_data": {"cloud-init": "ssh_keys:\n  ed25519_private: |\n    -----BEGIN OPENSSH PRIVATE KEY-----\n"}}},
    }]
  }
  count(result) == 1
}

test_allow_locked_account_and_public_key {
  result := deny with input as {
    "resource_changes": [{
      "address": "upcloud_server.vpn",
      "type": "upcloud_server",
      "change": {"after": {"user_data": "users:\n  - name: deploy\n    lock_passwd: true\n    ssh_authorized_keys:\n      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIexample\nssh_pwauth: false\n"}},
    }]
  }
  count(result) == 0
}
