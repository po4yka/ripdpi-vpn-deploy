# Credential-free singleton and legacy listener integer boundaries.
mock_provider "upcloud" {}

variables {
  server_name          = "vpn-test"
  zone                 = "fi-hel1"
  plan                 = "1xCPU-2GB"
  storage_template     = "01000000-0000-4000-8000-000020030200"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32", "2001:db8::42/128"]
  public_listeners     = [{ name = "xray", protocol = "tcp", port = 443 }]
}


run "reject_fractional_tcp_listener" {
  command = plan

  variables {
    public_listeners = [{ name = "fractional-tcp", protocol = "tcp", port = 443.5 }]
  }

  expect_failures = [var.public_listeners]
}

run "reject_fractional_udp_listener" {
  command = plan

  variables {
    public_listeners = [{ name = "fractional-udp", protocol = "udp", port = 443.5 }]
  }

  expect_failures = [var.public_listeners]
}

run "reject_fractional_legacy_xhttp_port" {
  command = plan

  variables {
    public_listeners            = []
    use_legacy_public_listeners = true
    nginx_xhttp_public_port     = 8443.5
  }

  expect_failures = [var.nginx_xhttp_public_port]
}

run "accept_integer_listener_boundaries" {
  command = plan

  variables {
    nginx_xhttp_public_port     = 65535
    use_legacy_public_listeners = true
    public_listeners = [
      { name = "tcp-low", protocol = "tcp", port = 1 },
      { name = "tcp-high", protocol = "tcp", port = 65535 },
      { name = "udp-low", protocol = "udp", port = 1 },
      { name = "udp-high", protocol = "udp", port = 65535 },
    ]
  }

  assert {
    condition = length(output.public_listeners) == 4 && alltrue([
      for listener in output.public_listeners : contains([1, 65535], listener.port)
    ])
    error_message = "Integer boundary ports must retain their canonical values and explicit-listener precedence."
  }
}
