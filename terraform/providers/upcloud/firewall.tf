resource "upcloud_firewall_rules" "vpn" {
  server_id = upcloud_server.vpn.id

  # Loopback / established
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

  # Public & Utility firewall rules are stateless: replies to connections
  # initiated by this server arrive as ordinary inbound packets. Restrict the
  # provider allow to the configured Linux client range; the guest nftables
  # state machine still rejects unsolicited traffic to these ports.
  dynamic "firewall_rule" {
    for_each = {
      "00-ipv4-tcp" = { family = "IPv4", protocol = "tcp" }
      "01-ipv4-udp" = { family = "IPv4", protocol = "udp" }
      "02-ipv6-tcp" = { family = "IPv6", protocol = "tcp" }
      "03-ipv6-udp" = { family = "IPv6", protocol = "udp" }
    }
    content {
      action                 = "accept"
      direction              = "in"
      family                 = firewall_rule.value.family
      protocol               = firewall_rule.value.protocol
      destination_port_start = tostring(var.provider_return_ephemeral_ports.start)
      destination_port_end   = tostring(var.provider_return_ephemeral_ports.end)
      comment                = "${upper(firewall_rule.value.protocol)} return ${firewall_rule.value.family}"
    }
  }

  # DHCP replies use fixed client ports outside the Linux ephemeral range and
  # are required before cloud-init can rely on public/utility networking.
  firewall_rule {
    action                 = "accept"
    direction              = "in"
    family                 = "IPv4"
    protocol               = "udp"
    source_port_start      = "67"
    source_port_end        = "67"
    destination_port_start = "68"
    destination_port_end   = "68"
    comment                = "DHCPv4 reply"
  }

  firewall_rule {
    action                 = "accept"
    direction              = "in"
    family                 = "IPv6"
    protocol               = "udp"
    source_port_start      = "547"
    source_port_end        = "547"
    destination_port_start = "546"
    destination_port_end   = "546"
    comment                = "DHCPv6 reply"
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

  # Keep outbound permissive at the provider edge. Guest nftables owns egress
  # policy; spelling this default out avoids depending on an account/UI default
  # when the stateless ruleset is activated.
  firewall_rule {
    action    = "accept"
    direction = "out"
    comment   = "default allow outbound"
  }

  lifecycle {
    precondition {
      condition     = length(local.effective_public_listeners) > 0
      error_message = "public_listeners resolves to an empty set; set public_listeners explicitly or opt into the historical defaults with use_legacy_public_listeners = true."
    }
  }
}
