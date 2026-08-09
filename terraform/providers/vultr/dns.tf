resource "vultr_dns_record" "public_ipv6_endpoint" {
  count = var.manage_public_ipv6_endpoint ? 1 : 0

  domain = var.public_ipv6_endpoint_domain
  name   = var.public_ipv6_endpoint_name
  data   = var.public_ipv6_endpoint_address
  type   = "AAAA"
  ttl    = var.public_ipv6_endpoint_ttl

  lifecycle {
    precondition {
      condition     = trimspace(var.public_ipv6_endpoint_domain) != ""
      error_message = "public_ipv6_endpoint_domain is required when manage_public_ipv6_endpoint is enabled."
    }

    precondition {
      condition     = trimspace(var.public_ipv6_endpoint_address) != ""
      error_message = "public_ipv6_endpoint_address is required when manage_public_ipv6_endpoint is enabled."
    }
  }
}
