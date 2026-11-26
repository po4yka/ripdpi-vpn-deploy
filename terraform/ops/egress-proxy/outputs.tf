output "server_ipv4" {
  value       = hcloud_primary_ip.egress.ip_address
  description = "Retained egress address that provider API allowlists name."
}

output "server_hostname" {
  value = hcloud_server.egress.name
}

output "admin_user" {
  value = var.admin_user
}

output "ssh_port" {
  value       = var.ssh_port
  description = "Effective SSH listener port."
}

output "zone" {
  value       = hcloud_server.egress.location
  description = "Hetzner location."
}
