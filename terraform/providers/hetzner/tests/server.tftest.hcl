# Asserts on the Hetzner server resources and inventory-facing outputs.

mock_provider "hcloud" {
  mock_resource "hcloud_server" {
    defaults = { id = "1001", ipv4_address = "203.0.113.10", ipv6_address = "2001:db8::10" }
  }
  mock_resource "hcloud_firewall" {
    defaults = { id = "2001" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "3001" }
  }
}

variables {
  server_name           = "vpn-test"
  location              = "hel1"
  server_type           = "cpx22"
  image                 = "debian-13"
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
      strcontains(hcloud_server.vpn.user_data, "provisioned_by=cloud-init")
      && strcontains(hcloud_server.vpn.user_data, "build_env=test")
      && strcontains(hcloud_server.vpn.user_data, "ssh-ed25519 AAAATESTKEY test@harness")
      && strcontains(hcloud_server.vpn.user_data, "--ssh-port 2222")
      && one([
        for item in yamldecode(hcloud_server.vpn.user_data).write_files : item
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ]).encoding == "b64"
      && base64decode(one([
        for item in yamldecode(hcloud_server.vpn.user_data).write_files : item.content
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ])) == file("${path.module}/../../shared/bootstrap-sshd-ownership.py")
    )
    error_message = "hcloud_server.user_data must carry the SSH port and exact embedded ownership helper"
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
      && output.ssh_port == 22
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

run "service_ipv4_defaults_to_the_primary_address" {
  command = plan

  assert {
    condition = (
      length(hcloud_floating_ip.service_ipv4) == 0
      && output.service_ipv4 == "203.0.113.10"
      && length(output.service_ipv4_addresses) == 0
    )
    error_message = "Without service generations the primary IPv4 must remain the client endpoint"
  }
}

run "service_ipv4_generations_attach_movable_addresses" {
  command = plan

  variables {
    service_ipv4_generations = ["g1", "g2"]
  }

  override_resource {
    target = hcloud_floating_ip.service_ipv4["g1"]
    values = { id = "4001", ip_address = "198.51.100.11" }
  }

  override_resource {
    target = hcloud_floating_ip.service_ipv4["g2"]
    values = { id = "4002", ip_address = "198.51.100.12" }
  }

  assert {
    condition = (
      length(hcloud_floating_ip.service_ipv4) == 2
      && hcloud_floating_ip.service_ipv4["g2"].type == "ipv4"
      && hcloud_floating_ip.service_ipv4["g2"].home_location == "hel1"
      && hcloud_floating_ip.service_ipv4["g2"].server_id == 1001
      && output.service_ipv4 == "198.51.100.12"
      && jsonencode(output.service_ipv4_addresses) == jsonencode(["198.51.100.11", "198.51.100.12"])
      && output.server_ipv4 == "203.0.113.10"
    )
    error_message = "Service generations must attach floating IPv4s to the server and publish the newest one as the client endpoint"
  }
}

run "service_ipv4_generations_are_bounded" {
  command = plan

  variables {
    service_ipv4_generations = ["g1", "g2", "g3"]
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

run "server_rejects_debian12_without_nft_destroy" {
  command = plan

  variables {
    image = "debian-12"
  }

  expect_failures = [var.image]
}

run "server_selects_ubuntu2404_image" {
  command = plan

  variables {
    image = "ubuntu-24.04"
  }

  assert {
    condition     = hcloud_server.vpn.image == "ubuntu-24.04"
    error_message = "Ubuntu 24.04 must remain selectable"
  }
}
