# The inert exception root keeps its local backend (versions.tf) and has no
# state; its state and plans are still encrypted like every other root's.
terraform {
  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }

    state {
      method   = method.aes_gcm.state
      enforced = true
    }
    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

variable "state_passphrase" {
  description = "State and plan encryption passphrase, from TF_VAR_state_passphrase only."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(var.state_passphrase) >= 16
    error_message = "state_passphrase must have at least 16 characters."
  }
}
