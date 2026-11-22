# Remote state lives in the operator's object storage bucket; the per-root
# backend file comes from TF_BACKEND_ROOT (scripts/terraform-env.sh).
# State and saved plans are encrypted on the client before they leave it.
# The unencrypted fallback only reads existing local state during migration.
terraform {
  backend "s3" {}

  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }
    method "unencrypted" "migrate" {}

    state {
      method = method.aes_gcm.state
      fallback {
        method = method.unencrypted.migrate
      }
    }
    plan {
      method = method.aes_gcm.state
      fallback {
        method = method.unencrypted.migrate
      }
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
