# Manage only explicit public endpoint records in an existing zone.

mock_provider "vultr" {}

variables {
  server_name          = "vpn-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2625
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
  public_listeners = [
    { name = "xray", protocol = "tcp", port = 443 },
    { name = "xray-fallback", protocol = "tcp", port = 2053 },
    { name = "nginx-xhttp", protocol = "tcp", port = 8443 },
    { name = "hysteria", protocol = "udp", port = 443 },
    { name = "amneziawg", protocol = "udp", port = 51820 },
  ]
}

run "dns_is_disabled_by_default" {
  command = plan

  assert {
    condition     = length(vultr_dns_record.managed) == 0
    error_message = "DNS ownership must be explicit."
  }
}

run "manage_public_endpoints_in_existing_zone" {
  command = plan

  variables {
    dns_zone = "example.com"
    managed_dns_records = {
      apex-a    = { name = "", type = "A", data = "203.0.113.10", ttl = 300 }
      apex-aaaa = { name = "", type = "AAAA", data = "2001:db8::10", ttl = 300 }
      www-cname = { name = "www", type = "CNAME", data = "example.com.", ttl = 3600 }
      h2-a      = { name = "h2", type = "A", data = "203.0.113.11", ttl = 300 }
      h2-aaaa   = { name = "h2", type = "AAAA", data = "2001:db8::11", ttl = 300 }
    }
  }

  assert {
    condition = {
      for key, record in vultr_dns_record.managed : key => {
        domain = record.domain
        name   = record.name
        type   = record.type
        data   = record.data
        ttl    = record.ttl
      }
      } == {
      apex-a    = { domain = "example.com", name = "", type = "A", data = "203.0.113.10", ttl = 300 }
      apex-aaaa = { domain = "example.com", name = "", type = "AAAA", data = "2001:db8::10", ttl = 300 }
      www-cname = { domain = "example.com", name = "www", type = "CNAME", data = "example.com.", ttl = 3600 }
      h2-a      = { domain = "example.com", name = "h2", type = "A", data = "203.0.113.11", ttl = 300 }
      h2-aaaa   = { domain = "example.com", name = "h2", type = "AAAA", data = "2001:db8::11", ttl = 300 }
    }
    error_message = "Every endpoint must preserve its exact name, type, data and TTL in the existing zone."
  }
}

run "reject_invalid_address_family" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "AAAA", data = "203.0.113.10", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "retain_existing_wildcard_cname" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { wildcard = { name = "*", type = "CNAME", data = "example.com", ttl = 300 } }
  }
  assert {
    condition     = vultr_dns_record.managed["wildcard"].name == "*" && vultr_dns_record.managed["wildcard"].data == "example.com"
    error_message = "An imported wildcard alias must retain its existing name and target."
  }
}

run "reject_invalid_ipv4" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "A", data = "2001:db8::10", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_unsupported_type" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "TXT", data = "value", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_fractional_ttl" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "A", data = "203.0.113.10", ttl = 300.5 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_low_ttl" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "A", data = "203.0.113.10", ttl = 59 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_duplicate_record" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "A", data = "203.0.113.10", ttl = 300 }, two = { name = "h2", type = "A", data = "203.0.113.11", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_cname_conflict" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "h2", type = "CNAME", data = "example.com.", ttl = 300 }, two = { name = "h2", type = "A", data = "203.0.113.11", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_apex_cname" {
  command = plan
  variables {
    dns_zone            = "example.com"
    managed_dns_records = { one = { name = "", type = "CNAME", data = "example.com.", ttl = 300 } }
  }
  expect_failures = [var.managed_dns_records]
}

run "reject_missing_zone" {
  command = plan
  variables {
    managed_dns_records = { one = { name = "h2", type = "A", data = "203.0.113.10", ttl = 300 } }
  }
  expect_failures = [vultr_dns_record.managed]
}

run "retain_imported_priority_metadata" {
  command = plan
  variables {
    dns_zone = "example.com"
    managed_dns_records = {
      apex-a    = { name = "", type = "A", data = "203.0.113.10", ttl = 300, priority = -1 }
      apex-aaaa = { name = "", type = "AAAA", data = "2001:db8::10", ttl = 300 }
    }
  }
  assert {
    condition     = vultr_dns_record.managed["apex-a"].priority == -1 && vultr_dns_record.managed["apex-aaaa"].priority == null
    error_message = "Imported provider priority metadata must not create a DNS write during adoption."
  }
}
