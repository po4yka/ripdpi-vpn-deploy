# Asserts that the optional public IPv6 endpoint is an explicit Vultr DNS AAAA record.

mock_provider "vultr" {}

variables {
  vultr_api_key        = "test-vultr-api-key"
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
}

run "public_ipv6_endpoint_is_disabled_by_default" {
  command = plan

  assert {
    condition     = length(vultr_dns_record.public_ipv6_endpoint) == 0
    error_message = "The shared DNS endpoint must stay opt-in for non-production workspaces"
  }
}

run "public_ipv6_endpoint_creates_one_aaaa_record" {
  command = plan

  variables {
    manage_public_ipv6_endpoint  = true
    public_ipv6_endpoint_domain  = "example.com"
    public_ipv6_endpoint_name    = ""
    public_ipv6_endpoint_address = "2001:db8::10"
  }

  assert {
    condition = (
      length(vultr_dns_record.public_ipv6_endpoint) == 1
      && vultr_dns_record.public_ipv6_endpoint[0].domain == "example.com"
      && vultr_dns_record.public_ipv6_endpoint[0].name == ""
      && vultr_dns_record.public_ipv6_endpoint[0].type == "AAAA"
      && vultr_dns_record.public_ipv6_endpoint[0].ttl == 300
    )
    error_message = "The enabled public IPv6 endpoint must create one apex AAAA record with the safe TTL"
  }
}
