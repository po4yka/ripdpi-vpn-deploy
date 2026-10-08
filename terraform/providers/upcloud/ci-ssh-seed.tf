# The provider reads the private image locally; only its path and digests enter state.
variable "ci_ssh_seed" {
  type = object({
    image_path             = string
    image_sha256           = string
    filesystem_uuid        = string
    host_public_key_sha256 = string
  })
  default = null
  validation {
    condition = var.ci_ssh_seed == null ? true : (
      can(regex("^ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}$", var.build_env)) &&
      startswith(var.ci_ssh_seed.image_path, "/") &&
      can(regex("^[a-f0-9]{64}$", var.ci_ssh_seed.image_sha256)) &&
      can(regex("^[a-f0-9]{64}$", var.ci_ssh_seed.host_public_key_sha256)) &&
      can(regex("^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", var.ci_ssh_seed.filesystem_uuid)) &&
      !var.enable_backups
    )
    error_message = "SSH seed requires a disposable ci-staging scope, absolute private image path, digests and no backups."
  }
}

resource "upcloud_storage" "ci_ssh_seed" {
  count   = var.ci_ssh_seed == null ? 0 : 1
  size    = 10
  title   = "${var.server_name}-ssh-seed"
  zone    = var.zone
  tier    = "maxiops"
  encrypt = true
  labels  = merge(local.base_labels, { seed_id = var.ci_ssh_seed.filesystem_uuid })
  import {
    source          = "direct_upload"
    source_location = var.ci_ssh_seed.image_path
    source_hash     = var.ci_ssh_seed.image_sha256
  }
}
