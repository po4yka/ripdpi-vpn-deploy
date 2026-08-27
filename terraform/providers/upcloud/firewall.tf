locals {
  primary_public_ipv4 = [for ni in upcloud_server.vpn.network_interface : ni.ip_address if ni.type == "public" && ni.ip_address_family == "IPv4"][0]
}

resource "upcloud_firewall_rules" "vpn" {
  server_id = upcloud_server.vpn.id

  # ICMP reachability; this provider firewall is stateless.
  firewall_rule {
    action    = "accept"
    direction = "in"
    family    = "IPv4"
    protocol  = "icmp"
    comment   = "ICMPv4"
  }

  firewall_rule {
    action    = "accept"
    direction = "in"
    family    = "IPv6"
    protocol  = "icmp"
    comment   = "ICMPv6"
  }

  # SSH from allowed CIDRs only
  dynamic "firewall_rule" {
    for_each = var.allowed_ssh_cidrs
    content {
      action                 = "accept"
      direction              = "in"
      family                 = strcontains(firewall_rule.value, ":") ? "IPv6" : "IPv4"
      protocol               = "tcp"
      destination_port_start = tostring(var.ssh_port)
      destination_port_end   = tostring(var.ssh_port)
      source_address_start   = cidrhost(firewall_rule.value, 0)
      source_address_end     = cidrhost(firewall_rule.value, -1)
      comment                = "SSH allow ${firewall_rule.value}"
    }
  }

  # Typed listener contract: every public runtime listener is opened here for
  # both address families. The same resolved contract is exported to Ansible.
  dynamic "firewall_rule" {
    for_each = {
      for pair in setproduct(["IPv4", "IPv6"], values(local.public_listener_rules)) :
      "${pair[0]}-${pair[1].protocol}-${coalesce(try(tostring(pair[1].port), null), try(pair[1].port_range, null))}" => {
        family   = pair[0]
        listener = pair[1]
      }
    }
    content {
      action                 = "accept"
      direction              = "in"
      family                 = firewall_rule.value.family
      protocol               = firewall_rule.value.listener.protocol
      destination_port_start = tostring(firewall_rule.value.listener.port != null ? firewall_rule.value.listener.port : tonumber(split("-", firewall_rule.value.listener.port_range)[0]))
      destination_port_end   = tostring(firewall_rule.value.listener.port != null ? firewall_rule.value.listener.port : tonumber(split("-", firewall_rule.value.listener.port_range)[1]))
      comment                = firewall_rule.value.listener.name == "xray" && firewall_rule.value.listener.protocol == "tcp" && firewall_rule.value.listener.port == 443 ? "TCP/443 VLESS+REALITY${firewall_rule.value.family == "IPv6" ? " IPv6" : ""}" : firewall_rule.value.listener.name == "hysteria" && firewall_rule.value.listener.protocol == "udp" && firewall_rule.value.listener.port == 443 ? "UDP/443 Hysteria2" : "${upper(firewall_rule.value.listener.protocol)}/${coalesce(try(tostring(firewall_rule.value.listener.port), null), firewall_rule.value.listener.port_range)} ${firewall_rule.value.listener.name}"
    }
  }

  # DNS replies are not public listeners. Keep both endpoints and the guest's
  # ephemeral destination ports constrained, before either terminal deny.
  dynamic "firewall_rule" {
    for_each = {
      for pair in setproduct(toset(var.dns_resolver_ipv4s), ["tcp", "udp"]) :
      "${pair[0]}-${pair[1]}" => { resolver = pair[0], protocol = pair[1] }
    }
    content {
      action                    = "accept"
      direction                 = "in"
      family                    = "IPv4"
      protocol                  = firewall_rule.value.protocol
      source_address_start      = firewall_rule.value.resolver
      source_address_end        = firewall_rule.value.resolver
      source_port_start         = "53"
      source_port_end           = "53"
      destination_address_start = local.primary_public_ipv4
      destination_address_end   = local.primary_public_ipv4
      destination_port_start    = tostring(var.dns_reply_port_range.start)
      destination_port_end      = tostring(var.dns_reply_port_range.end)
      comment                   = "DNS resolver reply"
    }
  }

  # Default deny inbound
  firewall_rule {
    action    = "drop"
    direction = "in"
    family    = "IPv4"
    comment   = "default deny inbound"
  }

  firewall_rule {
    action    = "drop"
    direction = "in"
    family    = "IPv6"
    comment   = "default deny inbound v6"
  }

  lifecycle {
    precondition {
      condition     = length(local.effective_public_listeners) > 0
      error_message = "public_listeners resolves to an empty set; set public_listeners explicitly or opt into the historical defaults with use_legacy_public_listeners = true."
    }
  }
}
