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
    enable_hysteria = true
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
    enable_hysteria = false
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
