# Credential-free management boundary tests.
mock_provider "vultr" {}

variables {
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32", "2001:db8::42/128"]
  public_listeners     = [{ name = "xray", protocol = "tcp", port = 443 }]
}

run "restricted_dual_stack_management" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["203.0.113.0/24", "2001:db8::/64"]
  }

  assert {
    condition     = output.ssh_port == 22
    error_message = "The safe management contract must remain usable."
  }
}

run "reject_ipv4_world" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}

run "reject_ipv4_host_bits_world" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["203.0.113.42/0"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}

run "reject_ipv6_world" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["::/0"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}

run "reject_ipv6_host_bits_world" {
  command = plan

  variables {
    allowed_ssh_cidrs = ["2001:db8::42/0"]
  }

  expect_failures = [var.allowed_ssh_cidrs]
}

run "reject_fractional_ssh_port" {
  command = plan

  variables {
    ssh_port         = 22.5
    public_listeners = [{ name = "unsafe-default-ssh", protocol = "tcp", port = 22 }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_tcp_singleton" {
  command = plan

  variables {
    public_listeners = [{ name = "unsafe", protocol = "tcp", port = 22 }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_tcp_range_start" {
  command = plan

  variables {
    public_listeners = [{ name = "unsafe", protocol = "tcp", port_range = "22-30" }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_tcp_range_end" {
  command = plan

  variables {
    public_listeners = [{ name = "unsafe", protocol = "tcp", port_range = "10-22" }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_tcp_range_interior" {
  command = plan

  variables {
    public_listeners = [{ name = "unsafe", protocol = "tcp", port_range = "10-30" }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_custom_ssh_overlap" {
  command = plan

  variables {
    ssh_port         = 2222
    public_listeners = [{ name = "unsafe", protocol = "tcp", port_range = "2220-2230" }]
  }

  expect_failures = [var.ssh_port]
}

run "reject_legacy_reality_overlap" {
  command = plan

  variables {
    public_listeners            = []
    use_legacy_public_listeners = true
    ssh_port                    = 443
    nginx_xhttp_public_port     = 8443
  }

  expect_failures = [var.ssh_port]
}

run "reject_legacy_xhttp_overlap" {
  command = plan

  variables {
    public_listeners            = []
    use_legacy_public_listeners = true
    ssh_port                    = 2222
    nginx_xhttp_public_port     = 2222
  }

  expect_failures = [var.ssh_port]
}

run "udp_same_number_and_adjacent_tcp_ranges" {
  command = plan

  variables {
    public_listeners = [
      { name = "adjacent-low", protocol = "tcp", port_range = "10-21" },
      { name = "adjacent-high", protocol = "tcp", port_range = "23-30" },
      { name = "udp-management-number", protocol = "udp", port = 22 },
    ]
  }

  assert {
    condition     = length(output.public_listeners) == 3 && output.ssh_port == 22
    error_message = "The safe management contract must remain usable."
  }
}

run "legacy_ignored_with_explicit_contract" {
  command = plan

  variables {
    use_legacy_public_listeners = true
    nginx_xhttp_public_port     = 22
  }

  assert {
    condition     = length(output.public_listeners) == 1 && output.ssh_port == 22
    error_message = "The safe management contract must remain usable."
  }
}
