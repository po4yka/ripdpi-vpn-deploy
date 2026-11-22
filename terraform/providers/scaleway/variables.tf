variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
}

variable "zone" {
  type        = string
  description = "Scaleway Availability Zone."

  validation {
    condition = contains([
      "fr-par-1", "fr-par-2", "fr-par-3",
      "nl-ams-1", "nl-ams-2", "nl-ams-3",
      "pl-waw-1", "pl-waw-2", "pl-waw-3",
      "it-mil-1",
    ], var.zone)
    error_message = "zone must be an approved Scaleway European Availability Zone."
  }
}

variable "server_type" {
  type        = string
  description = "Scaleway Instance commercial type."

  validation {
    condition     = contains(["DEV1-S", "DEV1-M", "DEV1-L", "PLAY2-PICO", "PLAY2-MICRO"], var.server_type)
    error_message = "server_type must be one of: DEV1-S, DEV1-M, DEV1-L, PLAY2-PICO, PLAY2-MICRO."
  }
}

variable "image" {
  type        = string
  default     = "ubuntu_noble"
  description = "Scaleway Marketplace image label."

  validation {
    condition     = contains(["ubuntu_noble"], var.image)
    error_message = "image must be ubuntu_noble; Debian 12 nftables lacks destroy."
  }
}

variable "root_size_gb" {
  type        = number
  default     = 20
  description = "Root Block Storage 5K size in decimal GB, fixed in the reviewed cost plan."

  validation {
    condition     = var.root_size_gb == floor(var.root_size_gb) && var.root_size_gb >= 20 && var.root_size_gb <= 100
    error_message = "root_size_gb must be an integer from 20 to 100."
  }
}

variable "admin_user" {
  type        = string
  default     = "deploy"
  description = "Non-root user created by cloud-init for SSH and Ansible access."
}

variable "admin_ssh_public_keys" {
  type        = list(string)
  sensitive   = true
  description = "Public SSH keys only; the matching private keys stay outside this repo. cloud-init and baseline write all of them to the admin account. The first entry is the operator key and the only one registered with the provider: changing it replaces the node, while adding, removing or reordering later entries does not."

  validation {
    condition     = length(var.admin_ssh_public_keys) > 0
    error_message = "admin_ssh_public_keys must contain at least one key to preserve SSH management access."
  }

  validation {
    condition     = alltrue([for key in var.admin_ssh_public_keys : can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\\.com) [A-Za-z0-9+/]+=* ?[^\r\n]*$", trimspace(key)))])
    error_message = "admin_ssh_public_keys entries must be single-line OpenSSH public keys."
  }

  validation {
    condition     = length(distinct([for key in var.admin_ssh_public_keys : try(join(" ", slice(split(" ", trimspace(key)), 0, 2)), key)])) == length(var.admin_ssh_public_keys)
    error_message = "admin_ssh_public_keys must not contain duplicate keys."
  }
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

  validation {
    condition     = alltrue([for cidr in var.allowed_ssh_cidrs : try(tonumber(split("/", cidr)[1]) >= (strcontains(cidr, ":") ? 48 : 24), true)])
    error_message = "allowed_ssh_cidrs entries must be no broader than /24 (IPv4) or /48 (IPv6); this also rejects world networks with host bits."
  }
}

variable "ssh_port" {
  type        = number
  default     = 22
  description = "Effective SSH listener port configured by cloud-init and opened at the provider edge."

  validation {
    condition     = floor(var.ssh_port) == var.ssh_port && var.ssh_port >= 1 && var.ssh_port <= 65535
    error_message = "ssh_port must be an integer TCP port within 1..65535."
  }

  validation {
    condition = alltrue([
      for listener in local.effective_public_listeners :
      listener.protocol != "tcp" || try(
        listener.port != null ? listener.port != var.ssh_port : !(
          tonumber(split("-", listener.port_range)[0]) <= var.ssh_port &&
          var.ssh_port <= tonumber(split("-", listener.port_range)[1])
        ),
        true
      )
    ])
    error_message = "ssh_port must not overlap any effective public TCP singleton or inclusive port range, including legacy listeners."
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
    condition     = floor(var.nginx_xhttp_public_port) == var.nginx_xhttp_public_port && var.nginx_xhttp_public_port >= 1 && var.nginx_xhttp_public_port <= 65535
    error_message = "nginx_xhttp_public_port must be an integer TCP port between 1 and 65535."
  }
}

variable "public_listeners" {
  type = list(object({
    name       = string
    protocol   = string
    port       = optional(number)
    port_range = optional(string)
    family     = optional(string)
  }))
  default     = []
  description = "Public TCP/UDP listeners allowed at the provider edge. Specify exactly one of port or port_range for each entry. Optional family (ipv4, ipv6 or dual; absent means dual) limits the entry to one address family at every layer."

  validation {
    condition = alltrue([
      for listener in var.public_listeners :
      trimspace(listener.name) != "" &&
      contains(["tcp", "udp"], listener.protocol) &&
      ((try(listener.port, null) != null) != (try(listener.port_range, null) != null)) &&
      (try(listener.port, null) == null ? true : (floor(listener.port) == listener.port && listener.port >= 1 && listener.port <= 65535)) &&
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

  validation {
    condition = alltrue([
      for listener in var.public_listeners :
      listener.family == null ? true : contains(["ipv4", "ipv6", "dual"], listener.family)
    ])
    error_message = "public_listeners family must be ipv4, ipv6 or dual; an absent family means dual."
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
  description = "Allocate and expose a reserved routed public IPv6 address."
}

variable "additional_public_ip" {
  type        = bool
  default     = false
  description = "Allocate a second routed public IPv4 for the honeypot role."
}
