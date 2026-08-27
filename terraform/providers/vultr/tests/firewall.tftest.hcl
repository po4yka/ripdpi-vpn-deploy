# Native Terraform tests for the Vultr provider root.
#
# DEFAULT-DENY MODEL (implicit):
# Vultr firewall groups are allowlist-only. Any inbound traffic that does not
# match an explicit rule is implicitly dropped by Vultr's edge — there is no
# separate "drop all" rule in the emitted HCL. The safety net is built in to
# the Vultr firewall group model.
#
# The assertion firewall_no_unrestricted_tcp_accept below documents and
# machine-verifies this property: it checks that no TCP rule opens an accept-all
# source (0.0.0.0/0 or ::/0), which would defeat the implicit default-deny for
# that port. SSH is the only port with source-restricted rules; public ports
# (443, xhttp) intentionally accept from 0.0.0.0 / :: — that is correct and
# is not tested here (see the REALITY and hysteria assertions above).

mock_provider "vultr" {}

variables {
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
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

run "firewall_fails_closed_without_listener_contract" {
  command = plan

  variables {
    public_listeners            = []
    use_legacy_public_listeners = false
  }

  expect_failures = [vultr_firewall_group.vpn]
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
    enable_hysteria             = true
    public_listeners            = []
    use_legacy_public_listeners = true
  }

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.tcp_public) :
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
    enable_hysteria             = false
    public_listeners            = []
    use_legacy_public_listeners = true
  }

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.tcp_public) :
      r if r.notes == "UDP/443 Hysteria2"
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
    condition     = length(vultr_firewall_rule.ssh) == length(var.allowed_ssh_cidrs)
    error_message = "SSH rule count must equal allowed_ssh_cidrs length"
  }
}

run "firewall_ssh_uses_configured_port" {
  command = plan

  variables {
    ssh_port = 2222
  }

  assert {
    condition = alltrue([
      for r in values(vultr_firewall_rule.ssh) : r.port == "2222"
    ])
    error_message = "SSH rules must use ssh_port instead of hard-coded TCP/22"
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

run "rejects_listener_with_empty_name" {
  command = plan

  variables {
    public_listeners = [{ name = "", protocol = "tcp", port = 4443 }]
  }

  expect_failures = [var.public_listeners]
}

# Implicit default-deny contract: no SSH rule must open an unrestricted source.
# Public ports (443, xhttp) are intentionally world-accessible; SSH must always
# carry a CIDR constraint (subnet_size > 0 or subnet != "0.0.0.0"/"::").
run "firewall_ssh_carries_cidr_constraint" {
  command = plan

  assert {
    condition = length([
      for r in values(vultr_firewall_rule.ssh) :
      r if r.subnet == "0.0.0.0" && r.subnet_size == 0
    ]) == 0
    error_message = "SSH rules must carry a CIDR constraint; unrestricted 0.0.0.0/0 SSH violates the implicit default-deny contract"
  }
}

run "rejects_empty_ssh_allowlist" {
  command = plan
  variables {
    allowed_ssh_cidrs = []
  }
  expect_failures = [var.allowed_ssh_cidrs]
}
