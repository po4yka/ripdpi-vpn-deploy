variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
}

variable "zone" {
  type        = string
  description = "UpCloud zone, e.g. fi-hel1, de-fra1, us-nyc1."

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]{3}[0-9]$", var.zone))
    error_message = "zone must match the UpCloud zone format, e.g. fi-hel1, de-fra1, nl-ams1."
  }
}

variable "plan" {
  type        = string
  description = "UpCloud plan slug, e.g. 1xCPU-2GB or DEV-2xCPU-4GB."

  validation {
    condition     = contains(["1xCPU-1GB", "1xCPU-2GB", "2xCPU-4GB", "DEV-2xCPU-4GB"], var.plan)
    error_message = "plan must be one of: 1xCPU-1GB, 1xCPU-2GB, 2xCPU-4GB, DEV-2xCPU-4GB."
  }
}

variable "storage_template" {
  type        = string
  description = "Storage template UUID to clone from. Pin to a specific Debian 13 / Ubuntu 24.04 template."

  validation {
    condition = can(regex(
      "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
      var.storage_template,
    ))
    error_message = "storage_template must be a UUID-shaped UpCloud template, not a placeholder."
  }
}

variable "storage_size_gb" {
  type        = number
  default     = 25
  description = "Root disk size in GB."
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
