# The primary IP's ip_address has no mock default, so a recreated primary IP
# would get a new random value; an unchanged value proves the address survived.
mock_provider "hcloud" {
  mock_resource "hcloud_server" {
    defaults = { id = "1001" }
  }
  mock_resource "hcloud_firewall" {
    defaults = { id = "2001" }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = "3001" }
  }
  mock_resource "hcloud_primary_ip" {
    defaults = { id = "4001" }
  }
}

variables {
  server_name           = "egress-test"
  location              = "hel1"
  server_type           = "cx23"
  image                 = "debian-13"
  admin_ssh_public_keys = ["ssh-ed25519 AAAATESTKEY test@harness"]
  allowed_ssh_cidrs     = ["203.0.113.42/32"]
  build_env             = "test"
}

run "create" {
  command = apply

  assert {
    condition     = hcloud_primary_ip.egress.auto_delete == false && hcloud_primary_ip.egress.type == "ipv4"
    error_message = "The egress address must be an IPv4 primary IP that is not deleted with its server."
  }

  assert {
    condition     = one(hcloud_server.egress.public_net).ipv4 == 4001 && one(hcloud_server.egress.public_net).ipv6_enabled == false
    error_message = "The server must use the retained primary IP and no public IPv6."
  }

  assert {
    condition = (
      length(hcloud_firewall.egress.rule) == 2 &&
      length([for rule in hcloud_firewall.egress.rule : rule if rule.protocol == "tcp" && rule.port == "22" && rule.source_ips == toset(["203.0.113.42/32"])]) == 1
    )
    error_message = "The provider firewall must open only ICMP and management SSH from the allowed CIDRs."
  }
}

# Changing ssh_port replaces the server. A primary IP planned for replacement
# would have an unknown address and fail this evaluation; a known one survives.
run "server_replacement_keeps_address" {
  command = plan

  variables {
    ssh_port = 2222
  }

  assert {
    condition     = terraform_data.ssh_port.input == 2222
    error_message = "The run must plan the replacement-triggering SSH port."
  }

  assert {
    condition     = output.server_ipv4 != ""
    error_message = "Server replacement must keep the retained egress address."
  }
}

run "rejects_a_broad_ssh_source" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}
