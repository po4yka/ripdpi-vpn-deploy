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
  description = "Hetzner server type, e.g. cpx22, cpx32, cx23, cx33."

  validation {
    condition     = contains(["cx23", "cx33", "cpx22", "cpx32"], var.server_type)
    error_message = "server_type must be one of: cx23, cx33, cpx22, cpx32."
  }
}

variable "image" {
  type        = string
  default     = "debian-13"
  description = "Hetzner image slug. Allowed: debian-13, ubuntu-24.04."

  validation {
    condition     = contains(["debian-13", "ubuntu-24.04"], var.image)
    error_message = "image must be one of: debian-13, ubuntu-24.04."
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
