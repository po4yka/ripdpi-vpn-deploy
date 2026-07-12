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
    condition     = contains(["debian_bookworm", "ubuntu_noble"], var.image)
    error_message = "image must be one of: debian_bookworm, ubuntu_noble."
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
  description = "Allocate and expose a reserved routed public IPv6 address."
}

variable "additional_public_ip" {
  type        = bool
  default     = false
  description = "Allocate a second routed public IPv4 for the honeypot role."
}
