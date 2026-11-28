output "server_ipv4" {
  value       = hcloud_server.vpn.ipv4_address
  description = "Public IPv4 address (primary)."
}

output "server_ipv6" {
  value       = var.enable_ipv6 ? hcloud_server.vpn.ipv6_address : null
  description = "Public IPv6 address (may be null if disabled)."
}

output "honeypot_ipv4" {
  value       = try(hcloud_floating_ip.honeypot_ipv4[0].ip_address, null)
  description = "Secondary public IPv4 used by the honeypot when additional_public_ip = true. Null when not allocated."
}

output "service_ipv4_addresses" {
  value       = [for name in var.service_ipv4_generations : hcloud_floating_ip.service_ipv4[name].ip_address]
  description = "Movable client-traffic IPv4 addresses attached to the server, in generation order. Empty when the primary IPv4 carries client traffic."
}

output "service_ipv4" {
  value       = length(var.service_ipv4_generations) > 0 ? hcloud_floating_ip.service_ipv4[var.service_ipv4_generations[length(var.service_ipv4_generations) - 1]].ip_address : hcloud_server.vpn.ipv4_address
  description = "Client endpoint IPv4: the newest service address, or the primary IPv4 when none is attached."
}

output "admin_user" {
  value = var.admin_user
}

output "ssh_port" {
  value       = var.ssh_port
  description = "Effective SSH listener port."
}

output "server_hostname" {
  value = hcloud_server.vpn.name
}

output "zone" {
  value       = hcloud_server.vpn.location
  description = "Provider-specific zone/region/location identifier."
}

output "public_listeners" {
  value       = local.effective_public_listeners
  description = "Canonical public listener contract enforced by the provider firewall."
}

output "nat_source_port_range" {
  value       = ""
  description = "No provider-edge source-port translation constraint."
}
