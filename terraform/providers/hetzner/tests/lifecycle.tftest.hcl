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
  server_name          = "vpn-test"
  location             = "hel1"
  server_type          = "cpx22"
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

# Shared test state exercises an actual mock apply followed by a plan.
run "create_node" {
  command = apply

  assert {
    condition     = terraform_data.admin_user.output == var.admin_user
    error_message = "Creation must record the administrator username guard."
  }

  assert {
    condition     = hcloud_server.vpn.firewall_ids == toset([tonumber(hcloud_firewall.vpn.id)])
    error_message = "The Hetzner server must attach its firewall at creation."
  }
}

run "unchanged_identity" {
  command = plan

  assert {
    condition     = hcloud_server.vpn.id != ""
    error_message = "Unchanged administrator identity must retain the node."
  }
}
