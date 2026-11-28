output "server_ipv4" {
  value       = scaleway_instance_ip.ipv4[0].address
  description = "Public IPv4 address (primary)."
}

output "server_ipv6" {
  value = var.enable_ipv6 ? try(one([
    for ip in scaleway_instance_server.vpn.public_ips : ip.address if ip.family == "inet6"
  ]), null) : null
  description = "Public IPv6 address (may be null if disabled)."
}

output "honeypot_ipv4" {
  value       = try(scaleway_instance_ip.honeypot_ipv4[0].address, null)
  description = "Secondary routed public IPv4 used by the honeypot when additional_public_ip = true."
}

output "service_ipv4_addresses" {
  value       = [for name in var.service_ipv4_generations : scaleway_instance_ip.service_ipv4[name].address]
  description = "Movable client-traffic IPv4 addresses attached to the server, in generation order. Empty when the primary IPv4 carries client traffic."
}

output "service_ipv4" {
  value       = length(var.service_ipv4_generations) > 0 ? scaleway_instance_ip.service_ipv4[var.service_ipv4_generations[length(var.service_ipv4_generations) - 1]].address : scaleway_instance_ip.ipv4[0].address
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
  value = scaleway_instance_server.vpn.name
}

output "zone" {
  value       = var.zone
  description = "Scaleway Availability Zone."
}

output "public_listeners" {
  value       = local.effective_public_listeners
  description = "Canonical public listener contract enforced by the provider security group."
}

output "nat_source_port_range" {
  value       = ""
  description = "No provider-edge source-port translation constraint."
}
