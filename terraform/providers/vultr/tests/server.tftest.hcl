# Asserts on the Vultr server resources and inventory-facing outputs.

mock_provider "vultr" {}

variables {
  server_name           = "vpn-test"
  region                = "ams"
  plan                  = "vc2-1c-1gb"
  os_id                 = 2625
  admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness"]
  allowed_ssh_cidrs     = ["203.0.113.42/32"]
  build_env             = "test"
  public_listeners = [
    { name = "xray", protocol = "tcp", port = 443 },
    { name = "xray-fallback", protocol = "tcp", port = 2053 },
    { name = "nginx-xhttp", protocol = "tcp", port = 8443 },
    { name = "hysteria", protocol = "udp", port = 443 },
    { name = "amneziawg", protocol = "udp", port = 51820 },
  ]
}

run "server_cloud_init_user_data_is_wired" {
  command = plan

  variables {
    ssh_port = 2222
  }

  assert {
    condition = (
      strcontains(vultr_instance.vpn.user_data, "provisioned_by=cloud-init")
      && strcontains(vultr_instance.vpn.user_data, "build_env=test")
      && strcontains(vultr_instance.vpn.user_data, "ssh-ed25519 AAAATESTKEY test@harness")
      && strcontains(vultr_instance.vpn.user_data, "--ssh-port 2222")
      && one([
        for item in yamldecode(vultr_instance.vpn.user_data).write_files : item
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ]).encoding == "b64"
      && base64decode(one([
        for item in yamldecode(vultr_instance.vpn.user_data).write_files : item.content
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ])) == file("${path.module}/../../shared/bootstrap-sshd-ownership.py")
    )
    error_message = "vultr_instance.user_data must carry the SSH port and exact embedded ownership helper"
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
      && output.ssh_port == 22
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

run "server_selects_debian13_image" {
  command = plan

  variables {
    os_id = 2625
  }

  assert {
    condition     = vultr_instance.vpn.os_id == 2625
    error_message = "Debian 13 x64 must select Vultr OS 2625, not Ubuntu 24.04 OS 2284"
  }
}

run "server_selects_ubuntu2404_image" {
  command = plan

  variables {
    os_id = 2284
  }

  assert {
    condition     = vultr_instance.vpn.os_id == 2284
    error_message = "Ubuntu 24.04 x64 must remain explicitly selectable as Vultr OS 2284"
  }
}

run "server_rejects_mislabeled_rocky9_image" {
  command = plan

  variables {
    os_id = 1869
  }

  expect_failures = [var.os_id]
}

run "server_rejects_releases_without_nft_destroy" {
  command = plan

  variables {
    os_id = 2136
  }

  expect_failures = [var.os_id]
}

run "server_rejects_ubuntu2204_without_nft_destroy" {
  command = plan

  variables {
    os_id = 1743
  }

  expect_failures = [var.os_id]
}

run "server_rejects_unapproved_image" {
  command = plan

  variables {
    os_id = 999999
  }

  expect_failures = [var.os_id]
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

run "service_ipv4_defaults_to_the_main_address" {
  command = plan

  assert {
    condition = (
      length(vultr_reserved_ip.service_ipv4) == 0
      && output.service_ipv4 == output.server_ipv4
      && length(output.service_ipv4_addresses) == 0
    )
    error_message = "Without service generations the main IPv4 must remain the client endpoint"
  }
}

run "service_ipv4_generations_attach_movable_addresses" {
  command = plan

  variables {
    service_ipv4_generations = ["g1", "g2"]
  }

  override_resource {
    target = vultr_instance.vpn
    values = { id = "instance-1", main_ip = "203.0.113.10" }
  }

  override_resource {
    target = vultr_reserved_ip.service_ipv4["g1"]
    values = { subnet = "198.51.100.11" }
  }

  override_resource {
    target = vultr_reserved_ip.service_ipv4["g2"]
    values = { subnet = "198.51.100.12" }
  }

  assert {
    condition = (
      length(vultr_reserved_ip.service_ipv4) == 2
      && vultr_reserved_ip.service_ipv4["g2"].ip_type == "v4"
      && vultr_reserved_ip.service_ipv4["g2"].region == var.region
      && vultr_reserved_ip.service_ipv4["g2"].instance_id == "instance-1"
      && output.service_ipv4 == "198.51.100.12"
      && jsonencode(output.service_ipv4_addresses) == jsonencode(["198.51.100.11", "198.51.100.12"])
      && output.server_ipv4 == "203.0.113.10"
    )
    error_message = "Service generations must attach reserved IPv4s to the instance and publish the newest one as the client endpoint"
  }
}

run "service_ipv4_generations_are_bounded" {
  command = plan

  variables {
    service_ipv4_generations = ["-g1"]
  }

  expect_failures = [var.service_ipv4_generations]
}

run "stateful_provider_preserves_unconstrained_nat_output" {
  command = plan
  assert {
    condition     = output.nat_source_port_range == ""
    error_message = "Stateful provider filtering must preserve ordinary guest NAT source-port selection."
  }
}
