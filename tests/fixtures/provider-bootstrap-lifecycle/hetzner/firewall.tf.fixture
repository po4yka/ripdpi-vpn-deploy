locals {
  public_source_ips = ["0.0.0.0/0", "::/0"]
}

# hcloud_firewall is an allowlist-only model: any inbound traffic that does
# not match an explicit rule is implicitly dropped by Hetzner's edge. There
# is no need for an explicit default-deny rule — the safety net is built in.
resource "hcloud_firewall" "vpn" {
  name   = "${var.server_name}-vpn"
  labels = local.base_labels

  rule {
    direction   = "in"
    protocol    = "icmp"
    source_ips  = local.public_source_ips
    description = "ICMP"
  }

  dynamic "rule" {
    for_each = var.allowed_ssh_cidrs
    content {
      direction   = "in"
      protocol    = "tcp"
      port        = tostring(var.ssh_port)
      source_ips  = [rule.value]
      description = "SSH allow ${rule.value}"
    }
  }

  # Typed listener contract shared with Ansible through rendered inventory.
  dynamic "rule" {
    for_each = local.public_listener_rules
    content {
      direction   = "in"
      protocol    = rule.value.protocol
      port        = coalesce(try(tostring(rule.value.port), null), try(rule.value.port_range, null))
      source_ips  = local.public_source_ips
      description = rule.value.name == "xray" && rule.value.protocol == "tcp" && rule.value.port == 443 ? "TCP/443 VLESS+REALITY" : rule.value.name == "hysteria" && rule.value.protocol == "udp" && rule.value.port == 443 ? "UDP/443 Hysteria2" : "${upper(rule.value.protocol)}/${coalesce(try(tostring(rule.value.port), null), rule.value.port_range)} ${rule.value.name}"
    }
  }

  lifecycle {
    precondition {
      condition     = length(local.effective_public_listeners) > 0
      error_message = "public_listeners resolves to an empty set; set public_listeners explicitly or opt into the historical defaults with use_legacy_public_listeners = true."
    }
  }
}

resource "hcloud_firewall_attachment" "vpn" {
  firewall_id = hcloud_firewall.vpn.id
  server_ids  = [hcloud_server.vpn.id]
}
