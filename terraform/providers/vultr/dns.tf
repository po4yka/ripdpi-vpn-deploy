# Move legacy state bindings before adoption; see docs/reference/provider-notes.md.
resource "vultr_dns_record" "managed" {
  for_each = var.managed_dns_records

  domain   = var.dns_zone
  name     = each.value.name
  data     = each.value.data
  type     = each.value.type
  ttl      = each.value.ttl
  priority = each.value.priority

  lifecycle {
    precondition {
      condition     = var.dns_zone != ""
      error_message = "dns_zone is required when managed_dns_records is not empty."
    }
  }
}
