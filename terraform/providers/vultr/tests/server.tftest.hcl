# Asserts on the Vultr server resources and inventory-facing outputs.

mock_provider "vultr" {}

variables {
  vultr_api_key        = "test-vultr-api-key"
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
}

run "server_cloud_init_user_data_is_wired" {
  command = plan

  assert {
    condition = (
      strcontains(vultr_instance.vpn.user_data, "provisioned_by=cloud-init")
      && strcontains(vultr_instance.vpn.user_data, "build_env=test")
      && strcontains(vultr_instance.vpn.user_data, "ssh-ed25519 AAAATESTKEY test@harness")
    )
    error_message = "vultr_instance.user_data must carry the rendered cloud-init bootstrap"
  }
}

run "server_defaults_to_ipv6_and_backups_enabled" {
  command = plan

  assert {
    condition = (
      vultr_instance.vpn.enable_ipv6 == true
      && vultr_instance.vpn.backups == "enabled"
    )
    error_message = "Default Vultr deploy must keep IPv6 and provider backups enabled"
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
    condition     = length(vultr_instance_ipv4.honeypot) == 1
    error_message = "additional_public_ip=true must allocate the honeypot IPv4"
  }
}
