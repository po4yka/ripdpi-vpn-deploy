variable "server_name" {
  type        = string
  description = "Hostname / Terraform name of the VPS."
  nullable    = false

  validation {
    condition     = length(var.server_name) <= 253 && can(regex("^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$", var.server_name))
    error_message = "server_name must be a DNS hostname of at most 253 characters."
  }
}

variable "region" {
  type        = string
  description = "Vultr region, e.g. ams, fra, lhr."

  validation {
    condition     = contains(["ams", "fra", "lhr"], var.region)
    error_message = "region must be one of the approved low-latency filtered-path locations: ams, fra, lhr."
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
    # Approved x64 images: 2284 Ubuntu 24.04, 2625 Debian 13. Older releases
    # (1743 Ubuntu 22.04, 2136 Debian 12) lack `nft destroy`; 1869 is Rocky Linux 9.
    # Run `vultr-cli os list` to obtain IDs for new releases; add here and update error_message.
    condition     = contains([2284, 2625], var.os_id)
    error_message = "os_id must be an approved Vultr OS ID: 2284 (Ubuntu 24.04), 2625 (Debian 13)."
  }
}

variable "admin_user" {
  type        = string
  default     = "deploy"
  description = "Non-root user created by cloud-init for SSH and Ansible access."
  nullable    = false

  validation {
    condition     = var.admin_user != "root" && can(regex("^[a-z_][a-z0-9_-]{0,31}$", var.admin_user))
    error_message = "admin_user must be a non-root login name of at most 32 characters."
  }
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
    condition     = alltrue([for key in var.admin_ssh_public_keys : can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\\.com) [A-Za-z0-9+/]+=*( [^\r\n']*)?$", trimspace(key)))])
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
  description = "Allocate and expose a public IPv6 address."
}

variable "dns_zone" {
  type        = string
  default     = ""
  description = "Existing Vultr DNS zone for the explicitly managed records."

  validation {
    condition = var.dns_zone == "" || (
      length(var.dns_zone) <= 253 && can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", var.dns_zone))
    )
    error_message = "dns_zone must be empty or a lowercase DNS domain name."
  }
}

variable "managed_dns_records" {
  type = map(object({
    name     = string
    type     = string
    data     = string
    ttl      = number
    priority = optional(number)
  }))
  default     = {}
  description = "A, AAAA, CNAME, TXT and CAA records in dns_zone, keyed by stable operator IDs. Import existing records before applying."

  validation {
    condition = alltrue([for record in values(var.managed_dns_records) :
      (record.name == "" || record.name == "*" || (length(record.name) <= 253 && can(regex("^_?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\._?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$", record.name))))
      && (record.priority == null ? true : record.priority == floor(record.priority) && record.priority >= -1 && record.priority <= 65535)
      && record.ttl == floor(record.ttl) && record.ttl >= 60 && record.ttl <= 86400
      && (
        (record.type == "A" && can(cidrnetmask("${record.data}/32")))
        || (record.type == "AAAA" && strcontains(record.data, ":") && can(cidrhost("${record.data}/128", 0)))
        || (record.type == "CNAME" && record.name != "" && length(record.data) <= 254 && can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\\.?$", record.data)))
        || (record.type == "TXT" && can(regex("^\"[ !#-~]{1,253}\"$", record.data)))
        || (record.type == "CAA" && can(regex("^(0|128) (issue|issuewild|iodef) \"[ !#-~]{1,253}\"$", record.data)))
      )
    ])
    error_message = "Records require valid relative names, A/AAAA addresses, a non-apex CNAME target, a quoted printable TXT value or a CAA flag, tag and quoted value, and an integer TTL from 60 to 86400."
  }

  validation {
    condition = length(distinct([for record in values(var.managed_dns_records) : contains(["TXT", "CAA"], record.type) ? "${record.name}:${record.type}:${record.data}" : "${record.name}:${record.type}"])) == length(var.managed_dns_records) && alltrue([
      for record in values(var.managed_dns_records) : record.type != "CNAME" || length([for other in values(var.managed_dns_records) : other if other.name == record.name]) == 1
    ])
    error_message = "Managed A, AAAA and CNAME names and types must be unique, TXT and CAA records must not repeat, and CNAME names cannot have another managed record."
  }
}

variable "enable_backups" {
  type    = bool
  default = false
  # Vultr snapshots are unencrypted; backups owned by the restic+age backup role.
  description = "Enable provider-side server backups with a daily 03:00 UTC schedule. Off by default: Vultr snapshots are unencrypted and bypass the restic+age backup chain."
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

variable "service_ipv4_generations" {
  type        = list(string)
  default     = []
  description = "Ordered names of movable public IPv4 addresses (reserved IPs attached to the instance) that carry client traffic on this server. The last name is the client endpoint; an earlier name stays attached while devices move to the new address. Empty keeps the main IPv4 as the client endpoint."

  validation {
    condition = (
      length(var.service_ipv4_generations) <= 2
      && length(distinct(var.service_ipv4_generations)) == length(var.service_ipv4_generations)
      && alltrue([for name in var.service_ipv4_generations : can(regex("^[a-z0-9][a-z0-9-]{0,30}$", name))])
    )
    error_message = "service_ipv4_generations holds at most two unique names of 1-31 lowercase letters, digits or hyphens, not starting with a hyphen."
  }
}
