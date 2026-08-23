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
  default     = "debian-12"
  description = "Hetzner image slug. Allowed: debian-12, ubuntu-24.04."

  validation {
    condition     = contains(["debian-12", "ubuntu-24.04"], var.image)
    error_message = "image must be one of: debian-12, ubuntu-24.04."
  }
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
