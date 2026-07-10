# Native Terraform tests for the Hetzner provider root.
#
# DEFAULT-DENY MODEL (implicit):
# Hetzner Cloud firewalls are allowlist-only. Any inbound traffic that does not
# match an explicit rule is implicitly dropped at the Hetzner edge — there is no
# separate "drop all" rule required in the emitted HCL. The safety net is built
# in to the hcloud_firewall resource model.
#
# The assertion firewall_ssh_carries_cidr_constraint below documents and
# machine-verifies this property: it checks that no SSH rule lists 0.0.0.0/0
# or ::/0 as a source, which would defeat the implicit default-deny for port 22.

mock_provider "hcloud" {}

variables {
  server_name          = "vpn-test"
  location             = "hel1"
  server_type          = "cpx21"
  image                = "debian-12"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
}

run "firewall_opens_reality_tcp_443_dual_stack" {
  command = plan

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "TCP/443 VLESS+REALITY"
      && r.direction == "in"
      && r.protocol == "tcp"
      && r.port == "443"
      && contains(r.source_ips, "0.0.0.0/0")
      && contains(r.source_ips, "::/0")
    ]) == 1
    error_message = "REALITY must accept TCP/443 from both IPv4 and IPv6 public sources"
  }
}

run "firewall_opens_hysteria_udp_443_when_enabled" {
  command = plan

  variables {
    enable_hysteria = true
  }

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "UDP/443 Hysteria2"
      && r.direction == "in"
      && r.protocol == "udp"
      && r.port == "443"
      && contains(r.source_ips, "0.0.0.0/0")
      && contains(r.source_ips, "::/0")
    ]) == 1
    error_message = "enable_hysteria=true must open UDP/443 to v4+v6"
  }
}

run "firewall_drops_hysteria_udp_443_when_disabled" {
  command = plan

  variables {
    enable_hysteria = false
  }

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "UDP/443 Hysteria2"
    ]) == 0
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
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if startswith(r.description, "SSH allow ")
    ]) == length(var.allowed_ssh_cidrs)
    error_message = "SSH rule count must equal allowed_ssh_cidrs length"
  }
}

run "firewall_ssh_never_world_readable" {
  command = plan

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.protocol == "tcp"
      && r.port == "22"
      && (contains(r.source_ips, "0.0.0.0/0") || contains(r.source_ips, "::/0"))
    ]) == 0
    error_message = "SSH must never be reachable from world-readable public CIDRs"
  }
}

run "firewall_emits_xhttp_port_when_distinct_from_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 8443
  }

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "TCP/8443 nginx-xhttp"
      && r.direction == "in"
      && r.protocol == "tcp"
      && r.port == "8443"
      && contains(r.source_ips, "0.0.0.0/0")
      && contains(r.source_ips, "::/0")
    ]) == 1
    error_message = "Distinct XHTTP port must be opened to v4+v6"
  }
}

run "firewall_skips_xhttp_port_when_equal_to_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 443
  }

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "TCP/443 VLESS+REALITY"
      ]) == 1 && length([
      for r in hcloud_firewall.vpn.rule :
      r if r.description == "TCP/443 nginx-xhttp"
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

run "rejects_listener_with_empty_name" {
  command = plan

  variables {
    public_listeners = [{ name = "", protocol = "tcp", port = 4443 }]
  }

  expect_failures = [var.public_listeners]
}

# Implicit default-deny contract: SSH must never accept from world-readable CIDRs.
# Public ports (443, xhttp, UDP/443) intentionally list 0.0.0.0/0 and ::/0 as
# sources; SSH must always be CIDR-scoped to preserve the implicit default-deny.
run "firewall_ssh_carries_cidr_constraint" {
  command = plan

  assert {
    condition = length([
      for r in hcloud_firewall.vpn.rule :
      r if r.protocol == "tcp"
      && r.port == "22"
      && (contains(r.source_ips, "0.0.0.0/0") || contains(r.source_ips, "::/0"))
    ]) == 0
    error_message = "SSH rules must carry a CIDR constraint; 0.0.0.0/0 or ::/0 SSH violates the implicit default-deny contract"
  }
}
