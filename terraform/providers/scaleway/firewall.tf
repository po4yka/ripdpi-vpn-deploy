locals {
  public_networks = {
    v4 = "0.0.0.0/0"
    v6 = "::/0"
  }

  provider_public_listener_rules = {
    for item in setproduct(keys(local.public_networks), values(local.public_listener_rules)) :
    "${item[0]}-${item[1].protocol}-${coalesce(try(tostring(item[1].port), null), try(item[1].port_range, null))}" => {
      protocol   = upper(item[1].protocol)
      port       = try(item[1].port, null)
      port_range = try(item[1].port_range, null)
      ip_range   = local.public_networks[item[0]]
    }
  }
}

resource "scaleway_instance_security_group" "vpn" {
  name                    = "${var.server_name}-ingress"
  description             = "Provider-edge allowlist for ${var.server_name}"
  zone                    = var.zone
  stateful                = true
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"
  enable_default_security = true
  tags                    = local.base_tags

  dynamic "inbound_rule" {
    for_each = toset(var.allowed_ssh_cidrs)
    content {
      action   = "accept"
      protocol = "TCP"
      port     = 22
      ip_range = inbound_rule.value
    }
  }

  dynamic "inbound_rule" {
    for_each = local.provider_public_listener_rules
    content {
      action     = "accept"
      protocol   = inbound_rule.value.protocol
      port       = inbound_rule.value.port
      port_range = inbound_rule.value.port_range
      ip_range   = inbound_rule.value.ip_range
    }
  }

  dynamic "inbound_rule" {
    for_each = local.public_networks
    content {
      action   = "accept"
      protocol = "ICMP"
      ip_range = inbound_rule.value
    }
  }
}
