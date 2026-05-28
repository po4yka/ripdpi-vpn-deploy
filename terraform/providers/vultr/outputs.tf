output "server_ipv4" {
  value       = vultr_instance.vpn.main_ip
  description = "Public IPv4 address (primary)."
}

output "server_ipv6" {
  value       = var.enable_ipv6 && vultr_instance.vpn.v6_main_ip != "" ? vultr_instance.vpn.v6_main_ip : null
  description = "Public IPv6 address (may be null if disabled)."
}

output "honeypot_ipv4" {
  value       = try(vultr_instance_ipv4.honeypot[0].ip, null)
  description = "Secondary public IPv4 used by the honeypot when additional_public_ip = true. Null when not allocated."
}

output "admin_user" {
  value = var.admin_user
}

output "server_hostname" {
  value = vultr_instance.vpn.hostname
}

output "zone" {
  value       = vultr_instance.vpn.region
  description = "Provider-specific zone/region/location identifier."
}
