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
