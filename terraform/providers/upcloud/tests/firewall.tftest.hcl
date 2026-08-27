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

mock_provider "upcloud" {
  mock_resource "upcloud_server" {
    defaults = {
      network_interface = { ip_address = "203.0.113.10" }
    }
  }
}

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
    condition = [
      for i, r in upcloud_firewall_rules.vpn.firewall_rule : i
      if r.action == "drop" && r.direction == "in"
      ] == [
      length(upcloud_firewall_rules.vpn.firewall_rule) - 2,
      length(upcloud_firewall_rules.vpn.firewall_rule) - 1,
      ] && toset([
        for r in upcloud_firewall_rules.vpn.firewall_rule : r.family if r.action == "drop"
    ]) == toset(["IPv4", "IPv6"])
    error_message = "Default-deny must close both IPv4 and IPv6 inbound chains"
  }
}

run "firewall_dns_replies_are_narrow_and_precede_denies" {
  command = apply

  assert {
    condition = toset([
      for r in upcloud_firewall_rules.vpn.firewall_rule : "${r.source_address_start}/${r.protocol}"
      if r.comment == "DNS resolver reply"
    ]) == toset(["94.237.127.9/tcp", "94.237.127.9/udp", "94.237.40.9/tcp", "94.237.40.9/udp"])
    error_message = "Default policy must emit TCP and UDP replies from exactly the two approved resolvers"
  }

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule : r if r.comment == "DNS resolver reply"
      ]) == 4 && alltrue([
      for i, r in upcloud_firewall_rules.vpn.firewall_rule :
      r.action == "accept" && r.direction == "in" && r.family == "IPv4" &&
      r.source_address_start == r.source_address_end &&
      r.source_port_start == "53" && r.source_port_end == "53" &&
      r.destination_address_start == output.server_ipv4 && r.destination_address_end == output.server_ipv4 &&
      r.destination_port_start == "32768" && r.destination_port_end == "60999" &&
      i < length(upcloud_firewall_rules.vpn.firewall_rule) - 2
      if r.comment == "DNS resolver reply"
    ])
    error_message = "Every DNS reply must constrain both addresses and ports before either inbound deny"
  }

  assert {
    condition = length(upcloud_firewall_rules.vpn.firewall_rule) == 19 && alltrue([
      for r in upcloud_firewall_rules.vpn.firewall_rule :
      r.protocol == "tcp" && r.source_address_start == "203.0.113.42" &&
      r.source_address_end == "203.0.113.42" &&
      r.destination_port_start == "22" && r.destination_port_end == "22"
      if startswith(r.comment, "SSH allow ")
    ]) && output.public_listeners == var.public_listeners
    error_message = "DNS replies must not widen the SSH or public listener contracts"
  }
}

run "firewall_dns_custom_policy_with_secondary_interface" {
  command = apply

  variables {
    additional_public_ip = true
    dns_resolver_ipv4s   = ["192.0.2.53", "198.51.100.53"]
    dns_reply_port_range = { start = 40000, end = 50000 }
  }

  # Native mocks share computed values across repeated NIC blocks. This checks
  # the full rule shape with a secondary NIC, not distinct-address selection.
  assert {
    condition = length([
      for ni in upcloud_server.vpn.network_interface : ni
      if ni.type == "public" && ni.ip_address_family == "IPv4"
      ]) == 2 && toset([
      for r in upcloud_firewall_rules.vpn.firewall_rule : "${r.source_address_start}/${r.protocol}"
      if r.comment == "DNS resolver reply"
    ]) == toset(["192.0.2.53/tcp", "192.0.2.53/udp", "198.51.100.53/tcp", "198.51.100.53/udp"])
    error_message = "Custom DNS resolvers must replace the defaults, with two replies per resolver"
  }

  assert {
    condition = length([
      for r in upcloud_firewall_rules.vpn.firewall_rule : r if r.comment == "DNS resolver reply"
      ]) == 4 && alltrue([
      for i, r in upcloud_firewall_rules.vpn.firewall_rule :
      r.action == "accept" && r.direction == "in" && r.family == "IPv4" &&
      r.source_address_start == r.source_address_end &&
      r.source_port_start == "53" && r.source_port_end == "53" &&
      r.destination_address_start == "203.0.113.10" && r.destination_address_end == "203.0.113.10" &&
      r.destination_port_start == "40000" && r.destination_port_end == "50000" &&
      i < length(upcloud_firewall_rules.vpn.firewall_rule) - 2
      if r.comment == "DNS resolver reply"
    ])
    error_message = "Custom DNS policy must keep the complete address, port, protocol and ordering constraints"
  }
}

run "rejects_empty_dns_resolvers" {
  command = plan
  variables { dns_resolver_ipv4s = [] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_duplicate_dns_resolvers" {
  command = plan
  variables { dns_resolver_ipv4s = ["192.0.2.53", "192.0.2.53"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_ipv6_dns_resolver" {
  command = plan
  variables { dns_resolver_ipv4s = ["2001:db8::53"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_dns_resolver_cidr" {
  command = plan
  variables { dns_resolver_ipv4s = ["192.0.2.53/32"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_dns_resolver_hostname" {
  command = plan
  variables { dns_resolver_ipv4s = ["resolver.example.invalid"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_empty_dns_resolver_address" {
  command = plan
  variables { dns_resolver_ipv4s = [""] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_dns_resolver_whitespace" {
  command = plan
  variables { dns_resolver_ipv4s = [" 192.0.2.53"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_noncanonical_dns_resolver" {
  command = plan
  variables { dns_resolver_ipv4s = ["192.000.2.53"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_invalid_dns_resolver_octet" {
  command = plan
  variables { dns_resolver_ipv4s = ["192.0.2.256"] }
  expect_failures = [var.dns_resolver_ipv4s]
}

run "rejects_zero_dns_reply_port" {
  command = plan
  variables { dns_reply_port_range = { start = 0, end = 60999 } }
  expect_failures = [var.dns_reply_port_range]
}

run "rejects_overflow_dns_reply_port" {
  command = plan
  variables { dns_reply_port_range = { start = 32768, end = 65536 } }
  expect_failures = [var.dns_reply_port_range]
}

run "rejects_reversed_dns_reply_ports" {
  command = plan
  variables { dns_reply_port_range = { start = 60999, end = 32768 } }
  expect_failures = [var.dns_reply_port_range]
}

run "rejects_fractional_dns_reply_start" {
  command = plan
  variables { dns_reply_port_range = { start = 32768.5, end = 60999 } }
  expect_failures = [var.dns_reply_port_range]
}

run "rejects_fractional_dns_reply_end" {
  command = plan
  variables { dns_reply_port_range = { start = 32768, end = 60999.5 } }
  expect_failures = [var.dns_reply_port_range]
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
