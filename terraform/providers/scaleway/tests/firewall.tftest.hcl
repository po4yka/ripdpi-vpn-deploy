# Native Terraform tests for the Scaleway provider-edge security group.

mock_provider "scaleway" {}

variables {
  server_name          = "vpn-test"
  zone                 = "pl-waw-1"
  server_type          = "DEV1-S"
  image                = "ubuntu_noble"
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

  expect_failures = [scaleway_instance_security_group.vpn]
}

run "firewall_is_stateful_default_deny" {
  command = plan

  assert {
    condition = (
      scaleway_instance_security_group.vpn.stateful == true
      && scaleway_instance_security_group.vpn.inbound_default_policy == "drop"
      && scaleway_instance_security_group.vpn.outbound_default_policy == "accept"
    )
    error_message = "Scaleway security group must default-drop inbound traffic and preserve outbound connectivity"
  }
}

run "firewall_opens_reality_tcp_443_dual_stack" {
  command = plan

  assert {
    condition = length([
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "TCP"
      && rule.port == 443
      && contains(["0.0.0.0/0", "::/0"], rule.ip_range)
    ]) == 2
    error_message = "REALITY must accept TCP/443 from both IPv4 and IPv6 public sources"
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "UDP"
      && rule.port == 443
      && contains(["0.0.0.0/0", "::/0"], rule.ip_range)
    ]) == 2
    error_message = "enable_hysteria=true must open UDP/443 to v4+v6"
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "UDP" && rule.port == 443
    ]) == 0
    error_message = "enable_hysteria=false must not open UDP/443"
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "TCP" && rule.port == 22
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule.port == 2222
      if rule.protocol == "TCP" && contains(var.allowed_ssh_cidrs, rule.ip_range)
    ])
    error_message = "SSH rules must use ssh_port instead of hard-coded TCP/22"
  }
}

run "firewall_ssh_never_world_readable" {
  command = plan

  assert {
    condition = length([
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "TCP"
      && rule.port == 22
      && contains(["0.0.0.0/0", "::/0"], rule.ip_range)
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "TCP"
      && rule.port == 8443
      && contains(["0.0.0.0/0", "::/0"], rule.ip_range)
    ]) == 2
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
      for rule in scaleway_instance_security_group.vpn.inbound_rule : rule
      if rule.protocol == "TCP" && rule.port == 443
    ]) == 2
    error_message = "When XHTTP shares TCP/443, the provider edge must emit only one dual-stack rule pair"
  }
}

run "rejects_invalid_xhttp_port" {
  command = plan

  variables {
    nginx_xhttp_public_port = 70000
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
