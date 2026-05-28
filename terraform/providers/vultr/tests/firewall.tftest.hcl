# Native Terraform tests for the Vultr provider root.

mock_provider "vultr" {}

variables {
  vultr_api_key        = "test-vultr-api-key"
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
}

run "firewall_opens_reality_tcp_443_v4_and_v6" {
  command = plan

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.tcp_public) :
      r if r.notes == "TCP/443 VLESS+REALITY"
      && r.protocol == "tcp"
      && r.port == "443"
    ]) == 2
    error_message = "REALITY must accept TCP/443 on both IPv4 and IPv6 by default"
  }
}

run "firewall_opens_hysteria_udp_443_when_enabled" {
  command = plan

  variables {
    enable_hysteria = true
  }

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.hysteria) :
      r if r.notes == "UDP/443 Hysteria2"
      && r.protocol == "udp"
      && r.port == "443"
    ]) == 2
    error_message = "enable_hysteria=true must open UDP/443 on v4+v6"
  }
}

run "firewall_drops_hysteria_udp_443_when_disabled" {
  command = plan

  variables {
    enable_hysteria = false
  }

  assert {
    condition     = length(vultr_firewall_rule.hysteria) == 0
    error_message = "enable_hysteria=false must NOT open UDP/443"
  }
}

run "firewall_ssh_count_matches_allowed_cidrs" {
  command = plan

  variables {
    allowed_ssh_cidrs = [
      "198.51.100.42/32",
      "198.51.100.50/32",
      "2001:db8::42/128",
    ]
  }

  assert {
    condition     = length(vultr_firewall_rule.ssh) == length(var.allowed_ssh_cidrs)
    error_message = "SSH rule count must equal allowed_ssh_cidrs length"
  }
}

run "firewall_ssh_never_world_readable" {
  command = plan

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.ssh) :
      r if r.subnet == "0.0.0.0" && r.subnet_size == 0
    ]) == 0
    error_message = "SSH must never be reachable from 0.0.0.0/0"
  }
}

run "firewall_emits_xhttp_port_when_distinct_from_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 8443
  }

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.tcp_public) :
      r if r.notes == "TCP/8443 nginx-xhttp"
      && r.protocol == "tcp"
      && r.port == "8443"
    ]) == 2
    error_message = "Distinct XHTTP port must be opened on v4+v6"
  }
}

run "firewall_skips_xhttp_port_when_equal_to_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 443
  }

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.tcp_public) :
      r if r.notes == "TCP/443 VLESS+REALITY"
      ]) == 2 && length([
      for r in values(vultr_firewall_rule.tcp_public) :
      r if r.notes == "TCP/443 nginx-xhttp"
    ]) == 0
    error_message = "When XHTTP shares :443, no duplicate TCP/443 nginx-xhttp rule is added"
  }
}

run "rejects_invalid_xhttp_port_high" {
  command = plan

  variables {
    nginx_xhttp_public_port = 70000
  }

  expect_failures = [var.nginx_xhttp_public_port]
}

run "rejects_invalid_xhttp_port_zero" {
  command = plan

  variables {
    nginx_xhttp_public_port = 0
  }

  expect_failures = [var.nginx_xhttp_public_port]
}
