output "server_ipv4" {
  value       = ""
  description = "Always empty while the candidate root is inert."
}

output "server_ipv6" {
  value       = ""
  description = "Always empty; the cascade entry contract is IPv4-only."
}

output "honeypot_ipv4" {
  value       = ""
  description = "Always empty; the inert exception root allocates no address."
}

output "admin_user" {
  value = var.admin_user
}

output "ssh_port" {
  value       = 22
  description = "Provider-neutral SSH port placeholder for the inert inventory contract."
}

output "server_hostname" {
  value = var.server_name
}

output "zone" {
  value       = "isolated-inert"
  description = "Provider-neutral marker; no hosting zone is selected."
}

output "public_listeners" {
  value       = []
  description = "No provider-edge listeners exist while the root is inert."
}
