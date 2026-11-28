output "server_ipv4" {
  value       = [for ni in upcloud_server.vpn.network_interface : ni.ip_address if ni.type == "public" && ni.ip_address_family == "IPv4"][0]
  description = "Public IPv4 address (primary)."
}

output "server_ipv6" {
  value       = try([for ni in upcloud_server.vpn.network_interface : ni.ip_address if ni.type == "public" && ni.ip_address_family == "IPv6"][0], null)
  description = "Public IPv6 address (may be null if disabled)."
}

output "honeypot_ipv4" {
  value       = try([for ni in upcloud_server.vpn.network_interface : ni.ip_address if ni.type == "public" && ni.ip_address_family == "IPv4"][1], null)
  description = "Secondary public IPv4 used by the honeypot when additional_public_ip = true. Null when not allocated."
}

output "service_ipv4_addresses" {
  value       = [for name in var.service_ipv4_generations : upcloud_floating_ip_address.service_ipv4[name].ip_address]
  description = "Movable client-traffic IPv4 addresses attached to the server, in generation order. Empty when the primary IPv4 carries client traffic."
}

output "service_ipv4" {
  value       = length(var.service_ipv4_generations) > 0 ? upcloud_floating_ip_address.service_ipv4[var.service_ipv4_generations[length(var.service_ipv4_generations) - 1]].ip_address : [for ni in upcloud_server.vpn.network_interface : ni.ip_address if ni.type == "public" && ni.ip_address_family == "IPv4"][0]
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
  value = upcloud_server.vpn.hostname
}

output "zone" {
  value       = upcloud_server.vpn.zone
  description = "Provider-specific zone/region/location identifier."
}

output "public_listeners" {
  value       = local.effective_public_listeners
  description = "Canonical public listener contract enforced by the provider firewall."
}

output "nat_source_port_range" {
  value       = var.enable_provider_firewall ? "${var.provider_return_ephemeral_ports.start}-${var.provider_return_ephemeral_ports.end}" : ""
  description = "Required forwarded TCP/UDP source-port translation range while the stateless provider firewall is enabled."
}

# Do NOT output:
#   - REALITY private keys
#   - VLESS UUIDs / shortIds
#   - Hysteria passwords
#   - subscription tokens
# These never leave the SOPS-encrypted secrets file.
