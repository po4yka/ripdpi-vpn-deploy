variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
}

variable "location" {
  type        = string
  description = "Hetzner Cloud location. Allowed: nbg1 (Nuremberg), fsn1 (Falkenstein), hel1 (Helsinki)."

  validation {
    condition     = contains(["nbg1", "fsn1", "hel1"], var.location)
    error_message = "location must be one of: nbg1, fsn1, hel1 (EU-only; US/Singapore DCs excluded by threat model)."
  }
}

variable "server_type" {
  type        = string
  description = "Hetzner server type, e.g. cpx21, cpx31, cx22, cx32."

  validation {
    condition     = contains(["cx22", "cx32", "cpx21", "cpx31"], var.server_type)
    error_message = "server_type must be one of: cx22, cx32, cpx21, cpx31."
  }
}

variable "image" {
  type        = string
  description = "Hetzner image slug, e.g. debian-12 or ubuntu-24.04."
}

variable "admin_user" {
  type        = string
  default     = "deploy"
  description = "Non-root user created by cloud-init for SSH and Ansible access."
}

variable "admin_ssh_public_key" {
  type        = string
  sensitive   = true
  description = "Public SSH key only. The matching private key stays outside this repo."
}

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "Source CIDRs allowed to reach 22/tcp."
}

variable "enable_hysteria" {
  type    = bool
  default = true
}

variable "nginx_xhttp_public_port" {
  type        = number
  default     = 8443
  description = "Public TCP port for nginx-xhttp. Keep this in sync with Ansible nginx_xhttp_public_port."

  validation {
    condition     = var.nginx_xhttp_public_port >= 1 && var.nginx_xhttp_public_port <= 65535
    error_message = "nginx_xhttp_public_port must be a valid TCP port."
  }
}

variable "build_env" {
  type        = string
  default     = "prod"
  description = "Free-form label baked into /etc/vpn-build-id by cloud-init."
}

variable "labels" {
  type        = map(string)
  default     = {}
  description = "Provider-specific resource tags/labels."
}

variable "enable_ipv6" {
  type        = bool
  default     = true
  description = "Allocate and expose a public IPv6 address."
}

variable "enable_backups" {
  type        = bool
  default     = true
  description = "Enable provider-side server backups."
}

variable "additional_public_ip" {
  type        = bool
  default     = false
  description = <<EOT
Allocate a second public IPv4 to this server. Used by the honeypot
role (vpn.enable_honeypot) so the canary listener can bind to an IP
that has no other service on it, separating its probe traffic from
the real REALITY listener at the IP-reputation level. Off by default.
EOT
}
