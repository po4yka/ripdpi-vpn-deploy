# Native Terraform tests for the UpCloud module.
#
# The module emits an `upcloud_firewall_rules` block whose contents are
# dynamic on the input variables. A regression that, say, drops the
# default-deny rule or opens UDP/443 unconditionally surfaces only at
# real-vps-deploy time today. These assertions catch it at PR time
# without contacting UpCloud — `mock_provider` shortcuts every real API
# call.
#
# Run from the module dir:
#   terraform -chdir=terraform/providers/upcloud test
#
# Requires Terraform 1.6+ (native test framework).

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

run "firewall_fails_closed_without_listener_contract" {
  command = plan

  variables {
    public_listeners            = []
    use_legacy_public_listeners = false
  }

  expect_failures = [upcloud_firewall_rules.vpn]
}

# ---------------------------------------------------------------------------
# REALITY: TCP/443 must always be open on both IPv4 and IPv6.
# ---------------------------------------------------------------------------
run "firewall_opens_reality_tcp_443_v4_and_v6" {
  command = plan

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if startswith(r.comment, "TCP/443 VLESS+REALITY")
    ]) == 2
    error_message = "REALITY must accept TCP/443 on both IPv4 and IPv6 by default"
  }
}

# ---------------------------------------------------------------------------
# Hysteria UDP/443 is conditional on the toggle.
# ---------------------------------------------------------------------------
run "firewall_opens_hysteria_udp_443_when_enabled" {
  command = plan

  variables {
    enable_hysteria             = true
    public_listeners            = []
    use_legacy_public_listeners = true
  }

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if r.comment == "UDP/443 Hysteria2"
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
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if r.comment == "UDP/443 Hysteria2"
    ]) == 0
    error_message = "enable_hysteria=false must NOT open UDP/443 — silent leak surface"
  }
}

# ---------------------------------------------------------------------------
# SSH must be CIDR-scoped, never world-readable.
# ---------------------------------------------------------------------------
run "firewall_ssh_count_matches_allowed_cidrs" {
  command = plan

  variables {
    allowed_ssh_cidrs = [
      "198.51.100.42/32",
      "198.51.100.50/32",
      "203.0.113.0/24",
    ]
  }

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if startswith(r.comment, "SSH allow ")
    ]) == length(var.allowed_ssh_cidrs)
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
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r.destination_port_start == "2222" && r.destination_port_end == "2222"
      if startswith(r.comment, "SSH allow ")
    ])
    error_message = "SSH rules must use ssh_port instead of hard-coded TCP/22"
  }
}

run "firewall_ssh_never_world_readable" {
  command = plan

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if r.comment == "SSH allow 0.0.0.0/0"
    ]) == 0
    error_message = "SSH must never be reachable from 0.0.0.0 — fail closed"
  }
}

# ---------------------------------------------------------------------------
# Public XHTTP port is conditional and never collides with REALITY:443.
# ---------------------------------------------------------------------------
run "firewall_emits_xhttp_port_when_distinct_from_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 8443
  }

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if r.comment == "TCP/8443 nginx-xhttp"
    ]) == 2
    error_message = "Distinct XHTTP port must be opened on v4+v6"
  }
}

run "firewall_skips_xhttp_port_when_equal_to_443" {
  command = plan

  variables {
    nginx_xhttp_public_port = 443
  }

  # REALITY already opens 443; the dynamic block must NOT duplicate it
  # (would cause UpCloud to reject the rule set at apply time).
  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if startswith(r.comment, "TCP/443 VLESS+REALITY")
      ]) == 2 && length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if r.comment == "TCP/443 nginx-xhttp"
    ]) == 0
    error_message = "When XHTTP shares :443, no duplicate :443 TCP rule is added"
  }
}

# ---------------------------------------------------------------------------
# Default-deny terminates both chains. If a refactor drops it the host
# becomes accept-any on inbound — silent regression.
# ---------------------------------------------------------------------------
run "firewall_default_deny_terminates_both_chains" {
  command = plan

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r if startswith(r.comment, "default deny inbound")
    ]) == 2
    error_message = "Default-deny must close both IPv4 and IPv6 inbound chains"
  }
}

# ---------------------------------------------------------------------------
# UpCloud Public & Utility firewall is stateless. Server-initiated flows need
# their inbound return half before the terminal drops; the guest stateful
# firewall remains responsible for rejecting unsolicited packets.
# ---------------------------------------------------------------------------
run "firewall_allows_dual_stack_tcp_udp_return_path" {
  command = plan

  assert {
    condition = alltrue([
      for family in ["IPv4", "IPv6"] : alltrue([
        for protocol in ["tcp", "udp"] : length([
          for r in upcloud_firewall_rules.vpn.firewall_rule : r
          if r.comment == "${upper(protocol)} return ${family}"
          && r.family == family
          && r.protocol == protocol
          && r.destination_port_start == "32768"
          && r.destination_port_end == "60999"
          && r.action == "accept"
          && r.direction == "in"
        ]) == 1
      ])
    ])
    error_message = "stateless return rules must accept TCP/UDP to 32768-60999 on IPv4 and IPv6"
  }
}

run "firewall_uses_configured_return_port_range" {
  command = plan

  variables {
    provider_return_ephemeral_ports = {
      start = 40000
      end   = 45000
    }
  }

  assert {
    condition = alltrue([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r.destination_port_start == "40000" && r.destination_port_end == "45000"
      if strcontains(r.comment, " return ")
    ])
    error_message = "every generic return rule must use provider_return_ephemeral_ports"
  }
}

run "firewall_allows_exact_dhcp_bootstrap_replies" {
  command = plan

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule : r
      if r.comment == "DHCPv4 reply"
      && r.family == "IPv4"
      && r.protocol == "udp"
      && r.source_port_start == "67"
      && r.source_port_end == "67"
      && r.destination_port_start == "68"
      && r.destination_port_end == "68"
      ]) == 1 && length([
      for r in upcloud_firewall_rules.vpn.firewall_rule : r
      if r.comment == "DHCPv6 reply"
      && r.family == "IPv6"
      && r.protocol == "udp"
      && r.source_port_start == "547"
      && r.source_port_end == "547"
      && r.destination_port_start == "546"
      && r.destination_port_end == "546"
    ]) == 1
    error_message = "DHCPv4 and DHCPv6 server-to-client replies must remain available during bootstrap"
  }
}

run "firewall_explicitly_allows_outbound_traffic" {
  command = plan

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule : r
      if r.comment == "default allow outbound"
      && r.action == "accept"
      && r.direction == "out"
    ]) == 1
    error_message = "stateless provider filtering must explicitly preserve the outbound half of server-initiated flows"
  }
}

run "firewall_return_rules_precede_terminal_drops" {
  command = plan

  assert {
    condition = alltrue([
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "TCP return IPv4") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound"),
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "UDP return IPv4") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound"),
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "TCP return IPv6") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound v6"),
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "UDP return IPv6") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound v6"),
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "DHCPv4 reply") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound"),
      index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "DHCPv6 reply") < index([for r in upcloud_firewall_rules.vpn.firewall_rule : r.comment], "default deny inbound v6"),
    ])
    error_message = "every stateless return/bootstrap allow must appear before its family terminal drop"
  }
}

run "rejects_privileged_return_port_range" {
  command = plan

  variables {
    provider_return_ephemeral_ports = {
      start = 1023
      end   = 60999
    }
  }

  expect_failures = [var.provider_return_ephemeral_ports]
}

run "rejects_reversed_return_port_range" {
  command = plan

  variables {
    provider_return_ephemeral_ports = {
      start = 60999
      end   = 32768
    }
  }

  expect_failures = [var.provider_return_ephemeral_ports]
}

run "rejects_return_port_above_65535" {
  command = plan

  variables {
    provider_return_ephemeral_ports = {
      start = 32768
      end   = 65536
    }
  }

  expect_failures = [var.provider_return_ephemeral_ports]
}

# ---------------------------------------------------------------------------
# Validation contract: nginx_xhttp_public_port must be a real port.
# ---------------------------------------------------------------------------
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

run "rejects_empty_ssh_allowlist" {
  command = plan

  variables {
    allowed_ssh_cidrs = []
  }

  expect_failures = [var.allowed_ssh_cidrs]
}

run "rejects_invalid_ssh_cidr" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["203.0.113.42/32", "not-a-cidr"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}
