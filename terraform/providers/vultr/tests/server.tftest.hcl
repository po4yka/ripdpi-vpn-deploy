# Asserts on the Vultr server resources and inventory-facing outputs.

mock_provider "vultr" {}

variables {
  vultr_api_key        = "test-vultr-api-key"
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ecdsa-sha2-nistp256 AAAATESTKEY operator: ci # fixture"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
}

run "server_cloud_init_user_data_is_wired" {
  command = plan

  assert {
    condition = (
      yamldecode(vultr_instance.vpn.user_data).users[1].name == "deploy"
      && yamldecode(vultr_instance.vpn.user_data).users[1].ssh_authorized_keys[0] == "ecdsa-sha2-nistp256 AAAATESTKEY operator: ci # fixture"
      && one([
        for file in yamldecode(vultr_instance.vpn.user_data).write_files :
        file if file.path == "/etc/vpn-build-id"
      ]).content == "provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=test\n"
    )
    error_message = "vultr_instance.user_data must preserve decoded cloud-init inputs exactly"
  }
}

run "server_defaults_to_ipv6_enabled_backups_disabled" {
  command = plan

  assert {
    condition = (
      vultr_instance.vpn.enable_ipv6 == true
      && vultr_instance.vpn.backups == "disabled"
    )
    # Backups are disabled by default: Vultr snapshots are unencrypted.
    # Backup ownership belongs to the restic+age backup role.
    error_message = "Default Vultr deploy must have IPv6 enabled and provider backups disabled (unencrypted snapshots)"
  }
}

run "outputs_preserve_inventory_contract" {
  command = plan

  assert {
    condition = (
      output.admin_user == "deploy"
      && output.server_hostname == "vpn-test"
      && output.zone == "ams"
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
    condition     = length(vultr_instance_ipv4.honeypot) == 0
    error_message = "Default deploy must not allocate the honeypot IPv4"
  }
}

run "server_secondary_public_ip_when_honeypot_enabled" {
  command = plan

  variables {
    additional_public_ip = true
  }

  assert {
    condition = (
      length(vultr_instance_ipv4.honeypot) == 1
      && vultr_instance_ipv4.honeypot[0].reboot == true
    )
    error_message = "additional_public_ip=true must allocate the honeypot IPv4 and reboot for guest convergence"
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
    admin_ssh_public_key = "ecdsa-sha2-nistp256 AAAATESTKEY\noperator"
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
