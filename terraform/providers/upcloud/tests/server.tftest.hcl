# Asserts on the server resource itself.

mock_provider "upcloud" {}

variables {
  server_name          = "vpn-test"
  zone                 = "fi-hel1"
  plan                 = "1xCPU-2GB"
  storage_template     = "01000000-0000-4000-8000-000020030200"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY operator: ci # fixture"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
}

# Cloud-init carries the build label downward into the VM. A refactor
# that drops the `metadata = true` attribute would silently disable
# cloud-init — host comes up unconfigured, ansible runs into a stock
# image. Tested as a plan-time invariant.
run "server_metadata_is_enabled" {
  command = plan

  assert {
    condition     = upcloud_server.vpn.metadata == true
    error_message = "upcloud_server.metadata must remain true; cloud-init depends on it"
  }
}

run "server_cloud_init_user_data_preserves_structured_values" {
  command = plan

  assert {
    condition = (
      yamldecode(upcloud_server.vpn.user_data).users[1].name == "deploy"
      && yamldecode(upcloud_server.vpn.user_data).users[1].ssh_authorized_keys[0] == "ssh-ed25519 AAAATESTKEY operator: ci # fixture"
      && one([
        for file in yamldecode(upcloud_server.vpn.user_data).write_files :
        file if file.path == "/etc/vpn-build-id"
      ]).content == "provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=test\n"
    )
    error_message = "upcloud_server.user_data must preserve decoded cloud-init inputs exactly"
  }
}

# Honeypot toggle controls whether a second public IPv4 is allocated.
# Default-off: catches accidental cost regression.
run "server_no_secondary_public_ip_by_default" {
  command = plan

  assert {
    condition = length([
      for ni in upcloud_server.vpn.network_interface :
      ni if ni.type == "public" && ni.ip_address_family == "IPv4"
    ]) == 1
    error_message = "Default deploy must allocate exactly one public NIC — secondary is opt-in"
  }
}

run "server_secondary_public_ip_when_honeypot_enabled" {
  command = plan

  variables {
    additional_public_ip = true
  }

  assert {
    condition = length([
      for ni in upcloud_server.vpn.network_interface :
      ni if ni.type == "public" && ni.ip_address_family == "IPv4"
    ]) == 2
    error_message = "additional_public_ip=true must allocate the second public NIC for the honeypot role"
  }
}

run "server_ipv6_is_disabled_when_requested" {
  command = plan

  variables {
    enable_ipv6 = false
  }

  assert {
    condition     = length([for ni in upcloud_server.vpn.network_interface : ni if ni.type == "public" && ni.ip_address_family == "IPv6"]) == 0
    error_message = "enable_ipv6=false must not allocate a public IPv6 interface"
  }
}

run "server_ipv6_is_allocated_by_default" {
  command = plan

  assert {
    condition     = length([for ni in upcloud_server.vpn.network_interface : ni if ni.type == "public" && ni.ip_address_family == "IPv6"]) == 1
    error_message = "enable_ipv6=true must allocate one public IPv6 interface"
  }
}

# Server template must always be a UUID-shaped string. Catches the
# REPLACE_WITH_TEMPLATE_UUID placeholder leaking past PR review.
run "rejects_unfilled_template_placeholder" {
  command = plan

  variables {
    storage_template = "REPLACE_WITH_TEMPLATE_UUID"
  }

  expect_failures = [var.storage_template]
}

run "rejects_invalid_admin_user" {
  command = plan

  variables {
    admin_user = "Deploy:root"
  }

  expect_failures = [var.admin_user]
}

run "rejects_multiline_admin_ssh_public_key" {
  command = plan

  variables {
    admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY\noperator"
  }

  expect_failures = [var.admin_ssh_public_key]
}

run "rejects_newline_bearing_build_env" {
  command = plan

  variables {
    build_env = "test\nprod"
  }

  expect_failures = [var.build_env]
}
