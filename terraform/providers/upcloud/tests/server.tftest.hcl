# Asserts on the server resource itself.

mock_provider "upcloud" {}

variables {
  server_name          = "vpn-test"
  zone                 = "fi-hel1"
  plan                 = "1xCPU-2GB"
  storage_template     = "01000000-0000-4000-8000-000020030200"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  public_listeners = [
    { name = "xray", protocol = "tcp", port = 443 },
    { name = "xray-fallback", protocol = "tcp", port = 2053 },
    { name = "nginx-xhttp", protocol = "tcp", port = 8443 },
    { name = "hysteria", protocol = "udp", port = 443 },
    { name = "amneziawg", protocol = "udp", port = 51820 },
  ]
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

run "server_cloud_init_uses_configured_ssh_port" {
  command = plan

  variables {
    ssh_port = 2222
  }

  assert {
    condition     = strcontains(upcloud_server.vpn.user_data, "Port 2222")
    error_message = "cloud-init must configure the same SSH port as the provider firewall"
  }
}

run "outputs_preserve_inventory_contract" {
  command = plan

  variables {
    ssh_port = 2222
  }

  assert {
    condition     = output.admin_user == "deploy" && output.server_hostname == "vpn-test" && output.ssh_port == 2222
    error_message = "Inventory-facing outputs must expose the effective SSH port"
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

# Server template must always be a UUID-shaped string. Catches an
# unfilled operator marker leaking past review.
run "rejects_unfilled_template_marker" {
  command = plan

  variables {
    storage_template = "UPCLOUD_TEMPLATE_UUID"
  }

  expect_failures = [var.storage_template]
}
