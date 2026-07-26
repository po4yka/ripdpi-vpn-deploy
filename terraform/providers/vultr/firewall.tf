locals {
  public_networks = {
    v4 = {
      ip_type     = "v4"
      subnet      = "0.0.0.0"
      subnet_size = 0
    }
    v6 = {
      ip_type     = "v6"
      subnet      = "::"
      subnet_size = 0
    }
  }

  ssh_cidr_rules = {
    for cidr in var.allowed_ssh_cidrs : cidr => {
      ip_type     = strcontains(cidr, ":") ? "v6" : "v4"
      subnet      = cidrhost(cidr, 0)
      subnet_size = tonumber(split("/", cidr)[1])
    }
  }

  provider_public_listener_rules = {
    for item in setproduct(keys(local.public_networks), values(local.public_listener_rules)) :
    "${item[0]}-${item[1].protocol}-${coalesce(try(tostring(item[1].port), null), try(item[1].port_range, null))}" => merge(local.public_networks[item[0]], {
      protocol = item[1].protocol
      port     = coalesce(try(tostring(item[1].port), null), try(item[1].port_range, null))
      name     = item[1].name
    })
  }
}

resource "vultr_firewall_rule" "icmp" {
  for_each = local.public_networks

  firewall_group_id = vultr_firewall_group.vpn.id
  protocol          = "icmp"
  ip_type           = each.value.ip_type
  subnet            = each.value.subnet
  subnet_size       = each.value.subnet_size
  notes             = "ICMP"
}

resource "vultr_firewall_rule" "ssh" {
  for_each = local.ssh_cidr_rules

  firewall_group_id = vultr_firewall_group.vpn.id
  protocol          = "tcp"
  ip_type           = each.value.ip_type
  subnet            = each.value.subnet
  subnet_size       = each.value.subnet_size
  port              = tostring(var.ssh_port)
  notes             = "SSH allow ${each.key}"
}

resource "vultr_firewall_rule" "tcp_public" {
  for_each = local.provider_public_listener_rules

  firewall_group_id = vultr_firewall_group.vpn.id
  protocol          = each.value.protocol
  ip_type           = each.value.ip_type
  subnet            = each.value.subnet
  subnet_size       = each.value.subnet_size
  port              = each.value.port
  notes             = each.value.name == "xray" && each.value.protocol == "tcp" && each.value.port == "443" ? "TCP/443 VLESS+REALITY" : each.value.name == "hysteria" && each.value.protocol == "udp" && each.value.port == "443" ? "UDP/443 Hysteria2" : "${upper(each.value.protocol)}/${each.value.port} ${each.value.name}"
}
