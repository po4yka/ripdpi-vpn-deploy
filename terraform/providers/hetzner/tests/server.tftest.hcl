# Asserts on the Hetzner server resources and inventory-facing outputs.

mock_provider "hcloud" {}

variables {
  server_name          = "vpn-test"
  location             = "hel1"
  server_type          = "cpx21"
  image                = "debian-12"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
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
      && strcontains(hcloud_server.vpn.user_data, "Port 2222")
    )
    error_message = "hcloud_server.user_data must carry the rendered cloud-init bootstrap"
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
