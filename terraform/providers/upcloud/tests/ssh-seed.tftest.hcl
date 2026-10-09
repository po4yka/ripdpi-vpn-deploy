mock_provider "upcloud" {}

variables {
  server_name          = "vpn-ci-staging-unit"
  build_env            = "ci-staging-unit"
  enable_backups       = false
  zone                 = "fi-hel1"
  plan                 = "1xCPU-2GB"
  storage_template     = "01000000-0000-4000-8000-000020030200"
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  public_listeners     = [{ name = "reality", protocol = "tcp", port = 443 }]
  ci_ssh_seed = {
    image_path             = "/private/unit/seed.img"
    image_sha256           = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    filesystem_uuid        = "11223344-5566-4788-99aa-bbccddeeff00"
    host_public_key_sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}

run "seed_import_and_guest_bootstrap_are_bound" {
  command = plan
  assert {
    condition     = upcloud_storage.ci_ssh_seed[0].encrypt && upcloud_server.vpn.template[0].encrypt
    error_message = "Seed and root storage must be encrypted at rest."
  }
  assert {
    condition     = one(upcloud_storage.ci_ssh_seed[0].import).source == "direct_upload" && one(upcloud_storage.ci_ssh_seed[0].import).source_hash == var.ci_ssh_seed.image_sha256
    error_message = "Import must use the local private image and bind its digest."
  }
  assert {
    condition     = length(upcloud_server.vpn.storage_devices) == 1
    error_message = "The server must attach exactly one host-key seed."
  }
  assert {
    condition     = startswith(yamldecode(upcloud_server.vpn.user_data).runcmd[0][2], "/usr/bin/python3 -I -B /usr/local/libexec/vpn-bootstrap-ssh-seed.py --filesystem-uuid ${var.ci_ssh_seed.filesystem_uuid} --public-key-sha256 ${var.ci_ssh_seed.host_public_key_sha256} && { ")
    error_message = "Seed verification must succeed before SSH ownership and the bootstrap marker."
  }
}

run "seed_rejects_permanent_environment" {
  command = plan
  variables { build_env = "prod" }
  expect_failures = [var.ci_ssh_seed]
}

run "seed_rejects_backups" {
  command = plan
  variables { enable_backups = true }
  expect_failures = [var.ci_ssh_seed]
}

run "ordinary_nodes_preserve_cloud_init" {
  command = plan
  variables { ci_ssh_seed = null }
  assert {
    condition     = length(upcloud_storage.ci_ssh_seed) == 0 && length(upcloud_server.vpn.storage_devices) == 0 && local.user_data == local.base_user_data
    error_message = "Nodes without the CI seed must preserve the original bootstrap."
  }
}
