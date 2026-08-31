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
}

variable "admin_ssh_public_key" {
  type        = string
  sensitive   = true
  description = "Public SSH key only. The matching private key stays outside this repo."
}

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "Source CIDRs allowed to reach ssh_port/tcp."

  validation {
    condition     = length(var.allowed_ssh_cidrs) > 0
    error_message = "allowed_ssh_cidrs must contain at least one CIDR to preserve SSH management access."
  }

  validation {
    condition     = alltrue([for cidr in var.allowed_ssh_cidrs : can(cidrhost(cidr, 0))])
    error_message = "allowed_ssh_cidrs entries must be valid IPv4 or IPv6 CIDRs in prefix notation, e.g. 203.0.113.42/32."
  }
}

variable "ssh_port" {
  type        = number
  default     = 22
  description = "Effective SSH listener port configured by cloud-init and opened at the provider edge."

  validation {
    condition     = var.ssh_port >= 1 && var.ssh_port <= 65535
    error_message = "ssh_port must be a valid TCP port."
  }
}

variable "enable_hysteria" {
  type        = bool
  default     = true
  description = "Include the Hysteria2 UDP/443 listener in the legacy default set. Explicit public_listeners ignore this toggle; add hysteria there directly."
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

  validation {
    condition = length(var.public_listeners) == length({
      for listener in var.public_listeners :
      "${listener.protocol}-${coalesce(try(tostring(listener.port), null), try(listener.port_range, null))}" => true
    })
    error_message = "public_listeners entries must not repeat the same protocol and port or port_range."
  }
}

variable "use_legacy_public_listeners" {
  type        = bool
  default     = false
  description = "Opt-in to the historical implicit listener set when public_listeners is empty. New environments must define public_listeners explicitly; an empty effective contract fails the plan."
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

variable "enable_provider_firewall" {
  type        = bool
  default     = false
  description = "Activate the UpCloud stateless Public & Utility firewall after the exact node has passed guest-firewall and strict-SSH verification."
}

variable "provider_return_ephemeral_ports" {
  type = object({
    start = number
    end   = number
  })
  default = {
    start = 32768
    end   = 60999
  }
  description = "Linux client ephemeral port range accepted for inbound TCP/UDP return traffic by the stateless provider firewall."

  validation {
    condition = (
      floor(var.provider_return_ephemeral_ports.start) == var.provider_return_ephemeral_ports.start &&
      floor(var.provider_return_ephemeral_ports.end) == var.provider_return_ephemeral_ports.end &&
      var.provider_return_ephemeral_ports.start >= 1024 &&
      var.provider_return_ephemeral_ports.end <= 65535 &&
      var.provider_return_ephemeral_ports.start <= var.provider_return_ephemeral_ports.end
    )
    error_message = "provider_return_ephemeral_ports must be an ordered integer range within 1024..65535."
  }
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
