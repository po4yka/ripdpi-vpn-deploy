variable "vultr_api_key" {
  type        = string
  sensitive   = true
  description = "Vultr API key. Prefer TF_VAR_vultr_api_key in the operator environment."
}

variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
}

variable "region" {
  type        = string
  description = "Vultr region, e.g. ams, fra, lhr, ewr."

  validation {
    condition     = contains(["ams", "fra", "lhr"], var.region)
    error_message = "region must be one of the approved low-latency RU-path locations: ams, fra, lhr."
  }
}

variable "plan" {
  type        = string
  description = "Vultr plan slug, e.g. vc2-1c-1gb or vhf-1c-1gb."

  validation {
    condition     = contains(["vc2-1c-1gb", "vhf-1c-1gb"], var.plan)
    error_message = "plan must be one of: vc2-1c-1gb, vhf-1c-1gb."
  }
}

variable "os_id" {
  type        = number
  description = "Vultr OS id, e.g. Debian or Ubuntu image id from `vultr-cli os list`."

  validation {
    # Known Vultr OS IDs for approved base images (Debian 12, Debian 11, Ubuntu 24.04, Ubuntu 22.04).
    # Run `vultr-cli os list` to obtain IDs for new releases; add here and update error_message.
    condition     = contains([1743, 2136, 2284, 1869], var.os_id)
    error_message = "os_id must be an approved Vultr OS ID: 1743 (Debian 11), 2136 (Debian 12), 2284 (Debian 13), 1869 (Ubuntu 24.04)."
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

variable "manage_public_ipv6_endpoint" {
  type        = bool
  default     = false
  description = "Manage the shared public IPv6 endpoint as a Vultr DNS AAAA record."
}

variable "public_ipv6_endpoint_domain" {
  type        = string
  default     = ""
  description = "Existing Vultr DNS zone that owns the public IPv6 endpoint."

  validation {
    condition = (
      var.public_ipv6_endpoint_domain == ""
      || can(regex("^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$", var.public_ipv6_endpoint_domain))
    )
    error_message = "public_ipv6_endpoint_domain must be empty or a DNS domain name."
  }
}

variable "public_ipv6_endpoint_name" {
  type        = string
  default     = ""
  description = "Relative Vultr DNS record name; empty means the zone apex."

  validation {
    condition = (
      var.public_ipv6_endpoint_name == ""
      || can(regex("^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$", var.public_ipv6_endpoint_name))
    )
    error_message = "public_ipv6_endpoint_name must be empty or a relative DNS name."
  }
}

variable "public_ipv6_endpoint_address" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Public IPv6 address published by the managed AAAA record."

  validation {
    condition = (
      var.public_ipv6_endpoint_address == ""
      || can(cidrhost("${var.public_ipv6_endpoint_address}/128", 0))
    )
    error_message = "public_ipv6_endpoint_address must be empty or a valid IPv6 address."
  }
}

variable "public_ipv6_endpoint_ttl" {
  type        = number
  default     = 300
  description = "TTL in seconds for the managed public IPv6 endpoint."

  validation {
    condition     = var.public_ipv6_endpoint_ttl >= 60 && var.public_ipv6_endpoint_ttl <= 86400
    error_message = "public_ipv6_endpoint_ttl must be between 60 and 86400 seconds."
  }
}

variable "enable_backups" {
  type    = bool
  default = false
  # Vultr snapshots are unencrypted; backups owned by the restic+age backup role.
  description = "Enable provider-side server backups. Off by default: Vultr snapshots are unencrypted and bypass the restic+age backup chain."
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
