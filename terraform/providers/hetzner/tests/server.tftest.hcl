# Asserts on the Hetzner server resources and inventory-facing outputs.

mock_provider "hcloud" {}

variables {
  server_name          = "vpn-test"
  location             = "hel1"
  server_type          = "cpx21"
  image                = "debian-12"
  admin_ssh_public_key = "ssh-rsa AAAATESTKEY operator: ci # fixture"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
}

run "server_cloud_init_user_data_is_wired" {
  command = plan

  assert {
    condition = (
      yamldecode(hcloud_server.vpn.user_data).users[1].name == "deploy"
      && yamldecode(hcloud_server.vpn.user_data).users[1].ssh_authorized_keys[0] == "ssh-rsa AAAATESTKEY operator: ci # fixture"
      && one([
        for file in yamldecode(hcloud_server.vpn.user_data).write_files :
        file if file.path == "/etc/vpn-build-id"
      ]).content == "provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=test\n"
    )
    error_message = "hcloud_server.user_data must preserve decoded cloud-init inputs exactly"
  }
}

run "server_public_network_defaults_to_dual_stack" {
  command = plan

  assert {
    condition = length([
      for net in hcloud_server.vpn.public_net :
      net if net.ipv4_enabled == true && net.ipv6_enabled == true
    ]) == 1
    error_message = "Default Hetzner deploy must keep primary public IPv4 and IPv6 enabled"
  }
}

run "outputs_preserve_inventory_contract" {
  command = plan

  assert {
    condition = (
      output.admin_user == "deploy"
      && output.server_hostname == "vpn-test"
      && output.zone == "hel1"
      && output.honeypot_ipv4 == null
    )
    error_message = "Inventory-facing outputs must stay compatible with the shared provider contract"
  }
}

run "server_ipv6_output_is_null_when_ipv6_disabled" {
  command = plan

  variables {
    enable_ipv6 = false
  }

  assert {
    condition     = output.server_ipv6 == null
    error_message = "server_ipv6 output must be null when enable_ipv6=false"
  }
}

run "server_no_secondary_public_ip_by_default" {
  command = plan

  assert {
    condition     = length(hcloud_floating_ip.honeypot_ipv4) == 0
    error_message = "Default deploy must not allocate the honeypot floating IPv4"
  }
}

run "server_secondary_public_ip_when_honeypot_enabled" {
  command = plan

  variables {
    additional_public_ip = true
  }

  assert {
    condition     = length(hcloud_floating_ip.honeypot_ipv4) == 1
    error_message = "additional_public_ip=true must allocate a honeypot floating IPv4"
  }
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
    admin_ssh_public_key = "ssh-rsa AAAATESTKEY\noperator"
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
