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
