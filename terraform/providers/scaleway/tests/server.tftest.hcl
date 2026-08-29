# Asserts on the Scaleway server resources and inventory-facing outputs.

mock_provider "scaleway" {}

variables {
  server_name          = "vpn-test"
  zone                 = "pl-waw-1"
  server_type          = "DEV1-S"
  image                = "ubuntu_noble"
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
      strcontains(scaleway_instance_server.vpn.user_data["cloud-init"], "provisioned_by=cloud-init")
      && strcontains(scaleway_instance_server.vpn.user_data["cloud-init"], "build_env=test")
      && strcontains(scaleway_instance_server.vpn.user_data["cloud-init"], "ssh-ed25519 AAAATESTKEY test@harness")
      && strcontains(scaleway_instance_server.vpn.user_data["cloud-init"], "--ssh-port 2222")
      && one([
        for item in yamldecode(scaleway_instance_server.vpn.user_data["cloud-init"]).write_files : item
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ]).encoding == "b64"
      && base64decode(one([
        for item in yamldecode(scaleway_instance_server.vpn.user_data["cloud-init"]).write_files : item.content
        if item.path == "/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"
      ])) == file("${path.module}/../../shared/bootstrap-sshd-ownership.py")
    )
    error_message = "scaleway_instance_server user_data must carry the SSH port and exact embedded ownership helper"
  }
}

run "server_defaults_to_reserved_dual_stack_addresses" {
  command = plan

  assert {
    condition = (
      length(scaleway_instance_ip.ipv4) == 1
      && length(scaleway_instance_ip.ipv6) == 1
      && scaleway_instance_ip.ipv4[0].type == "routed_ipv4"
      && scaleway_instance_ip.ipv6[0].type == "routed_ipv6"
    )
    error_message = "Default Scaleway deploy must attach reserved routed IPv4 and IPv6 addresses"
  }
}

run "outputs_preserve_inventory_contract" {
  command = plan

  assert {
    condition = (
      output.admin_user == "deploy"
      && output.ssh_port == 22
      && output.server_hostname == "vpn-test"
      && output.zone == "pl-waw-1"
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
    condition     = length(scaleway_instance_ip.honeypot_ipv4) == 0
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
      length(scaleway_instance_ip.honeypot_ipv4) == 1
      && scaleway_instance_ip.honeypot_ipv4[0].type == "routed_ipv4"
    )
    error_message = "additional_public_ip=true must allocate a routed honeypot IPv4"
  }
}
