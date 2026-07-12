locals {
  legacy_public_listeners = concat([
    { name = "xray", protocol = "tcp", port = 443, port_range = null },
    { name = "xray-fallback", protocol = "tcp", port = 2053, port_range = null },
    { name = "nginx-xhttp", protocol = "tcp", port = var.nginx_xhttp_public_port, port_range = null },
    { name = "amneziawg", protocol = "udp", port = 51820, port_range = null },
    ], var.enable_hysteria ? [
    { name = "hysteria", protocol = "udp", port = 443, port_range = null },
  ] : [])

  effective_public_listeners = length(var.public_listeners) > 0 ? var.public_listeners : local.legacy_public_listeners
  public_listener_rule_groups = {
    for listener in local.effective_public_listeners :
    "${listener.protocol}-${coalesce(try(tostring(listener.port), null), try(listener.port_range, null))}" => listener...
  }
  public_listener_rules = {
    for key, listeners in local.public_listener_rule_groups : key => listeners[0]
  }
}
