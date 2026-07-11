variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
}

variable "zone" {
  type        = string
  description = "UpCloud zone. Allowed: fi-hel1 (Helsinki), de-fra1 (Frankfurt), nl-ams1 (Amsterdam), sg-sin1 (Singapore)."

  validation {
    condition     = contains(["fi-hel1", "de-fra1", "nl-ams1", "sg-sin1"], var.zone)
    error_message = "zone must be one of: fi-hel1, de-fra1, nl-ams1, sg-sin1."
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

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]{0,31}$", var.admin_user))
    error_message = "admin_user must be 1-32 characters, start with a lowercase ASCII letter or underscore, and contain only lowercase ASCII letters, digits, underscores, or hyphens."
  }
}

variable "admin_ssh_public_key" {
  type        = string
  sensitive   = true
  description = "Public SSH key only. The matching private key stays outside this repo."

  validation {
    condition = (
      var.admin_ssh_public_key != ""
      && var.admin_ssh_public_key == trimspace(var.admin_ssh_public_key)
      && !strcontains(var.admin_ssh_public_key, "\r")
      && !strcontains(var.admin_ssh_public_key, "\n")
      && can(regex("^[^[:space:]]+[[:space:]]+[^[:space:]]+([[:space:]]+.*)?$", var.admin_ssh_public_key))
    )
    error_message = "admin_ssh_public_key must be one trimmed, single-line OpenSSH public key with a key type, encoded body, and optional comment."
  }
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

# Canonical provider-edge listener contract. Keep it aligned with the
# effective Ansible listener manifest; render-inventory passes the resolved
# value to Ansible, which fails before deployment if the two diverge.
variable "public_listeners" {
  type = list(object({
    name       = string
    protocol   = string
    port       = optional(number)
    port_range = optional(string)
  }))
  default     = []
  description = "Public TCP/UDP listeners allowed at the provider edge. Specify exactly one of port or port_range for each entry."

  validation {
    condition = alltrue([
      for listener in var.public_listeners :
      trimspace(listener.name) != "" &&
      contains(["tcp", "udp"], listener.protocol) &&
      ((try(listener.port, null) != null) != (try(listener.port_range, null) != null)) &&
      (try(listener.port, null) == null || (listener.port >= 1 && listener.port <= 65535)) &&
      (try(listener.port_range, null) == null || (can(regex("^[1-9][0-9]*-[1-9][0-9]*$", listener.port_range)) ? (tonumber(split("-", listener.port_range)[0]) <= tonumber(split("-", listener.port_range)[1]) && tonumber(split("-", listener.port_range)[1]) <= 65535) : false))
    ])
    error_message = "Each public listener must use tcp or udp and exactly one valid port or port_range."
  }
}

variable "build_env" {
  type        = string
  default     = "prod"
  description = "Technical environment label baked into /etc/vpn-build-id by cloud-init."

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", var.build_env))
    error_message = "build_env must be 1-64 ASCII letters, digits, underscores, or hyphens and start with an ASCII letter or digit."
  }
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
  description = "Enable provider-side server backups (daily, 7-day retention)."
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
